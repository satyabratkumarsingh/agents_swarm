"""LangChain tools for completing or releasing the current task."""

from __future__ import annotations

from langchain.tools import tool

from agents_swarm.storage import TeamStore


def make_task_tools(store: TeamStore, agent_name: str, task_id: int) -> list:
    @tool
    def complete_current_task(summary: str) -> str:
        """Mark your claimed task complete and publish its summary."""
        if store.complete_task(task_id, agent_name, summary):
            return f"Task #{task_id} marked done."
        return "Could not complete task: it may no longer be owned by this agent."

    @tool
    def release_current_task(reason: str) -> str:
        """Mark your task blocked and record why it cannot proceed, for human/peer follow-up."""
        if store.release_task(task_id, agent_name, reason):
            return f"Task #{task_id} marked blocked."
        return "Could not release task: it may no longer be owned by this agent."

    return [complete_current_task, release_current_task]
