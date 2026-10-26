"""Plan a large brief into subtasks, run the worker swarm, and report results."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from agents_swarm.agent import run_agent
from agents_swarm.storage import TeamStore


class PlannedTask(BaseModel):
    title: str = Field(description="Short, actionable subtask title")
    description: str = Field(
        description="Specific scope, expected contribution, and how the worker can verify it"
    )


class ProjectPlan(BaseModel):
    title: str = Field(description="Short project title")
    tasks: list[PlannedTask] = Field(
        min_length=1,
        max_length=20,
        description="Parallelizable, non-duplicative tasks that together cover the full brief",
    )


class ProjectReport(BaseModel):
    markdown: str = Field(
        description="Final markdown report: outcome, completed work, verification, incomplete work, and limitations"
    )


def _model() -> ChatAnthropic:
    return ChatAnthropic(model=_model_name(), temperature=0)


async def _plan(brief: str) -> ProjectPlan:
    planner = _model().with_structured_output(ProjectPlan)
    result = await planner.ainvoke(
        [
            (
                "system",
                "You are a technical project planner. Break the user's complete goal into "
                "small actionable subtasks for independent coding agents. Avoid overlapping file "
                "ownership, expose dependencies in descriptions, cover validation/integration, "
                "and do not invent requirements. Return between 1 and 20 tasks.",
            ),
            ("human", f"Decompose this project brief into a practical plan:\n\n{brief}"),
        ]
    )
    return result


def _project_context(snapshot: dict[str, Any]) -> str:
    project = snapshot["project"]
    task_lines = []
    for task in snapshot["tasks"]:
        task_lines.append(
            f"- #{task['id']} [{task['status']}] {task['title']}\n"
            f"  Detail: {task['description']}\n"
            f"  Owner: {task['owner'] or 'none'}\n"
            f"  Result: {task['summary'] or 'No summary recorded'}"
        )
    board_lines = [
        f"- [{entry['kind']}] {entry['author']}: {entry['content']}"
        for entry in snapshot["board"]
    ]
    return (
        f"Project: {project['title']}\n"
        f"Original brief:\n{project['brief']}\n\n"
        f"Subtask outcomes:\n" + "\n".join(task_lines)
        + "\n\nTeam findings:\n" + ("\n".join(board_lines) or "(none)")
    )


def _fallback_report(snapshot: dict[str, Any]) -> str:
    project = snapshot["project"]
    lines = [f"# {project['title']}", "", "## Task outcomes"]
    for task in snapshot["tasks"]:
        lines.extend(
            [
                f"### {task['title']} — {task['status']}",
                task["summary"] or "No result summary recorded.",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


async def _make_report(snapshot: dict[str, Any]) -> str:
    synthesizer = _model().with_structured_output(ProjectReport)
    try:
        result = await synthesizer.ainvoke(
            [
                (
                    "system",
                    "Write a concise final project report grounded only in the supplied brief, "
                    "task statuses, summaries, and notes. Clearly distinguish completed, blocked, "
                    "and failed work. Never claim tests passed unless a task summary says so.",
                ),
                ("human", _project_context(snapshot)),
            ]
        )
        return result.markdown.strip() + "\n"
    except Exception as exc:
        return _fallback_report(snapshot) + f"\n_Report synthesis unavailable: {exc}_\n"


async def run_project_from_file(
    store: TeamStore,
    task_file: Path,
    workspace: Path,
    instructions_path: Path,
    agent_names: list[str],
) -> tuple[int, Path, str]:
    """Read a project brief, plan it, run workers, and write/return its report."""
    brief = task_file.read_text(encoding="utf-8").strip()
    if not brief:
        raise ValueError(f"Task brief is empty: {task_file}")

    plan = await _plan(brief)
    project_id, task_ids = store.create_project(
        plan.title,
        brief,
        [task.model_dump() for task in plan.tasks],
    )
    print(f"Planned project #{project_id}: {plan.title}")
    for task_id, task in zip(task_ids, plan.tasks):
        print(f"  Queued #{task_id}: {task.title}")

    async def worker(agent_name: str) -> None:
        while True:
            try:
                did_work = await run_agent(
                    store,
                    agent_name,
                    workspace,
                    instructions_path,
                    project_id=project_id,
                )
            except Exception as exc:
                print(f"[{agent_name}] stopped after failure: {exc}")
                return
            if not did_work:
                return

    await asyncio.gather(*(worker(name) for name in agent_names))

    snapshot = store.project_snapshot(project_id)
    if snapshot is None:
        raise RuntimeError(f"Project #{project_id} disappeared from the coordination store")
    statuses = {task["status"] for task in snapshot["tasks"]}
    project_status = "completed" if statuses <= {"done"} else "incomplete"
    store.set_project_status(project_id, project_status)
    snapshot["project"]["status"] = project_status

    report = await _make_report(snapshot)
    reports_dir = workspace / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"project-{project_id}-final.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Project {project_status}. Final report: {report_path}")
    return project_id, report_path, report
