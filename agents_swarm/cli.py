"""Command-line entry point for the local team-agent prototype."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from agents_swarm.agent import run_agent
from agents_swarm.projects import run_project_from_file
from agents_swarm.storage import TeamStore


def _root() -> Path:
    return Path(os.getenv("TEAM_HOME", ".team")).expanduser().resolve()


def _workspace() -> Path:
    workspace = Path(os.getenv("TEAM_WORKSPACE", "workspace")).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _store() -> TeamStore:
    return TeamStore(_root() / "team.sqlite3")


def _load_env_file() -> None:
    """Load simple KEY=VALUE entries from .env without an extra dependency."""
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


async def _worker(agent_name: str, once: bool, watch: bool, poll_seconds: float) -> None:
    store = _store()
    instructions = Path(os.getenv("TEAM_INSTRUCTIONS", "agent.txt")).expanduser().resolve()
    workspace = _workspace()
    while True:
        try:
            did_work = await run_agent(store, agent_name, workspace, instructions)
        except Exception as exc:
            store.post_board(agent_name, "ERROR", f"Agent run failed: {exc}")
            print(f"[{agent_name}] run failed: {exc}", file=sys.stderr)
            if once:
                return
            did_work = False
        if once or (not did_work and not watch):
            return
        if not did_work:
            await asyncio.sleep(poll_seconds)


async def _run_workers(agents: list[str], once: bool, watch: bool, poll_seconds: float) -> None:
    await asyncio.gather(
        *(_worker(name, once, watch, poll_seconds) for name in agents),
        return_exceptions=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agents-swarm", description="Plan projects and run a collaborative DeepAgents swarm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_task = subparsers.add_parser("add-task", help="Add one or more task titles to the shared queue")
    add_task.add_argument("titles", nargs="+", help="Task title(s)")

    run = subparsers.add_parser("work", help="Start one or more agents concurrently")
    run.add_argument("--agents", required=True, help="Comma-separated unique agent names")
    run.add_argument("--once", action="store_true", help="Each agent claims at most one task, then exits")
    run.add_argument("--watch", action="store_true", help="Poll for newly added tasks when the queue is empty")
    run.add_argument("--poll-seconds", type=float, default=10.0, help="Delay between empty-queue polls")

    run_file = subparsers.add_parser(
        "run-file", help="Decompose a brief file, run a swarm on its subtasks, and write a final report"
    )
    run_file.add_argument("brief_file", type=Path, help="Text/Markdown file containing the complete goal")
    run_file.add_argument("--agents", required=True, help="Comma-separated unique agent names")

    subparsers.add_parser("status", help="Show tasks, board entries, and messages")

    note = subparsers.add_parser("note", help="Post a shared board entry")
    note.add_argument("kind", help="For example FACT, OBSERVED, FAIL, or CLAIM")
    note.add_argument("content", help="Short note")
    note.add_argument("--agent", default="human", help="Author name")
    note.add_argument("--task-id", type=int)

    message = subparsers.add_parser("message", help="Post a message for an agent or the whole team")
    message.add_argument("recipient", help="Agent name or 'team'")
    message.add_argument("content", help="Message text")
    message.add_argument("--from-agent", default="human", help="Sender name")
    return parser


def main() -> None:
    _load_env_file()
    args = build_parser().parse_args()
    store = _store()

    if args.command == "add-task":
        ids = store.add_tasks(args.titles)
        for task_id, title in zip(ids, args.titles):
            print(f"Added task #{task_id}: {title}")
        return

    if args.command == "status":
        snapshot = store.snapshot()
        print("TASKS")
        for task in snapshot["tasks"]:
            print(f"#{task['id']} [{task['status']}] owner={task['owner'] or '-'} {task['title']}")
        print("\nBOARD")
        for entry in snapshot["board"]:
            print(f"[{entry['kind']}] {entry['author']} (task={entry['task_id']}): {entry['content']}")
        print("\nMESSAGES")
        for message in snapshot["messages"]:
            print(f"{message['sender']} -> {message['recipient']}: {message['content']}")
        return

    if args.command == "note":
        entry_id = store.post_board(args.agent, args.kind, args.content, args.task_id)
        print(f"Posted board entry #{entry_id}.")
        return

    if args.command == "message":
        message_id = store.post_message(args.from_agent, args.recipient, args.content)
        print(f"Posted message #{message_id}.")
        return

    if args.command == "work":
        agents = [name.strip() for name in args.agents.split(",") if name.strip()]
        if not agents or len(set(agents)) != len(agents):
            raise SystemExit("--agents must contain one or more unique names")
        if args.poll_seconds <= 0:
            raise SystemExit("--poll-seconds must be positive")
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is required (copy .env.example to .env and set it)")
        try:
            asyncio.run(_run_workers(agents, args.once, args.watch, args.poll_seconds))
        except KeyboardInterrupt:
            print("Stopping after current agent turns complete.", file=sys.stderr)
        return

    if args.command == "run-file":
        if not args.brief_file.is_file():
            raise SystemExit(f"Brief file not found: {args.brief_file}")
        agents = [name.strip() for name in args.agents.split(",") if name.strip()]
        if not agents or len(set(agents)) != len(agents):
            raise SystemExit("--agents must contain one or more unique names")
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is required (set it in .env or the shell)")
        try:
            _, _, report = asyncio.run(
                run_project_from_file(
                    store,
                    args.brief_file.expanduser().resolve(),
                    _workspace(),
                    Path(os.getenv("TEAM_INSTRUCTIONS", "agent.txt")).expanduser().resolve(),
                    agents,
                )
            )
            print("\n" + report)
        except KeyboardInterrupt:
            print("Stopped by user; partial tasks and notes remain in the team database.", file=sys.stderr)
        return


if __name__ == "__main__":
    main()
