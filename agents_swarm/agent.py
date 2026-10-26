"""DeepAgents worker for one claimed project subtask."""

from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_anthropic import ChatAnthropic
from quicksand import NetworkMode, UbuntuSandbox

from agents_swarm.coordination import make_board_tools, make_task_tools
from agents_swarm.execution import create_workspace_mount, make_execution_tool
from agents_swarm.storage import TeamStore


def _model_name() -> str:
    return os.getenv("TEAM_MODEL", "claude-sonnet-4-5")


def _read_instructions(path: Path, agent_name: str) -> str:
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not content.strip():
        content = "You are a cooperative software agent. Inspect your task and workspace, coordinate, verify, and report honestly."
    return content.replace("${AGENT_NAME}", agent_name)


async def run_agent(
    store: TeamStore,
    agent_name: str,
    workspace: Path,
    instructions_path: Path,
    project_id: int | None = None,
) -> bool:
    task = store.claim_next_task(agent_name, project_id)
    if task is None:
        return False

    store.post_message(agent_name, "team", f"Claimed task #{task['id']}: {task['title']}")
    try:
        model = ChatAnthropic(model=_model_name(), temperature=0)
        task_id = int(task["id"])
        async with UbuntuSandbox(
            mounts=[create_workspace_mount(workspace)],
            network_mode=NetworkMode.MOUNTS_ONLY,
        ) as sandbox:
            tools = make_board_tools(store, agent_name, task_id)
            tools.extend(make_task_tools(store, agent_name, task_id))
            tools.append(make_execution_tool(sandbox))
            agent = create_deep_agent(
                model=model,
                tools=tools,
                system_prompt=_read_instructions(instructions_path, agent_name),
                backend=FilesystemBackend(root_dir=str(workspace), virtual_mode=True),
            )
            prompt = (
                f"Overall project: {task['project_title'] or 'Standalone task'}\n"
                f"Overall project brief:\n{task['project_brief'] or '(not provided)'}\n\n"
                f"Your assigned subtask: #{task['id']} {task['title']}\n"
                f"Detailed scope and acceptance guidance:\n{task['description']}\n"
                "Start by checking the board for peer claims and useful context. Make a focused contribution. "
                "Use run_in_sandbox to execute generated code and tests. Publish findings and complete or release the task."
            )
            result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    except Exception as exc:
        store.fail_task(int(task["id"]), agent_name, f"Agent run failed: {exc}")
        raise

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None
    final_text = str(getattr(last_message, "content", "Agent turn ended without a final response"))
    if final_text.strip():
        store.post_board(agent_name, "RUN_SUMMARY", final_text[:300], int(task["id"]))
    if store.task_status(int(task["id"])) == "claimed":
        store.fail_task(
            int(task["id"]),
            agent_name,
            "Agent turn ended without calling complete_current_task or release_current_task.",
        )
    return True
