"""LangChain tools for reading and writing shared team context and messages."""

from __future__ import annotations

from langchain.tools import tool

from agents_swarm.storage import TeamStore


def make_board_tools(store: TeamStore, agent_name: str, task_id: int) -> list:
    @tool
    def board_read() -> str:
        """Read current tasks, recent board notes, and team messages."""
        snapshot = store.snapshot()
        lines = ["TASKS"]
        lines.extend(
            f"#{task['id']} [{task['status']}] owner={task['owner'] or '-'} {task['title']}"
            for task in snapshot["tasks"]
        )
        lines.append("\nBOARD")
        lines.extend(
            f"[{entry['kind']}] {entry['author']} (task={entry['task_id']}): {entry['content']}"
            for entry in snapshot["board"]
        )
        lines.append("\nMESSAGES")
        lines.extend(
            f"{message['sender']} -> {message['recipient']}: {message['content']}"
            for message in snapshot["messages"]
        )
        return "\n".join(lines)

    @tool
    def board_write(kind: str, content: str) -> str:
        """Publish a FACT, OBSERVED, FAIL, CLAIM, or progress note for peers."""
        entry_id = store.post_board(agent_name, kind, content, task_id)
        return f"Published board entry #{entry_id}."

    @tool
    def message_agent(recipient: str, content: str) -> str:
        """Send a persistent message to a peer by agent name, or 'team' for everyone."""
        message_id = store.post_message(agent_name, recipient, content)
        return f"Sent message #{message_id} to {recipient}."

    return [board_read, board_write, message_agent]
