"""Quicksand VM integration for executing agent-generated code and tests."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool
from quicksand import Mount

GUEST_WORKSPACE = "/workspace"
MAX_COMMAND_TIMEOUT = 600
MAX_OUTPUT_CHARS = 20_000


def create_workspace_mount(workspace: Path) -> Mount:
    """Map the persistent host workspace into the VM at ``/workspace``."""
    return Mount(host=str(workspace.resolve()), guest=GUEST_WORKSPACE)


def make_execution_tool(sandbox):
    """Create a LangChain tool that runs commands only inside the Quicksand VM."""

    @tool
    async def run_in_sandbox(command: str, timeout_seconds: int = 120) -> str:
        """Run a shell command in the isolated Quicksand VM, from /workspace.

        Use this to run the project's tests, linters, build commands, or generated code.
        Files in /workspace are shared with the host workspace and persist after the VM stops.
        Network access is restricted by the sandbox's MOUNTS_ONLY mode.
        """
        if not command.strip():
            return "Command cannot be empty."
        timeout = max(1, min(timeout_seconds, MAX_COMMAND_TIMEOUT))
        result = await sandbox.execute(
            command,
            cwd=GUEST_WORKSPACE,
            timeout=float(timeout),
        )
        stdout = result.stdout[-MAX_OUTPUT_CHARS:]
        stderr = result.stderr[-MAX_OUTPUT_CHARS:]
        return (
            f"exit_code={result.exit_code}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    return run_in_sandbox
