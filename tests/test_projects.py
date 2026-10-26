from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents_swarm.projects import ProjectPlan, PlannedTask, run_project_from_file
from agents_swarm.storage import TeamStore


class ProjectWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_brief_is_planned_run_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            brief_file = root / "goal.md"
            brief_file.write_text("Build a small service and tests.", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            store = TeamStore(root / "state" / "team.sqlite3")
            plan = ProjectPlan(
                title="Sample service",
                tasks=[
                    PlannedTask(title="Implement service", description="Create the service."),
                    PlannedTask(title="Add tests", description="Test the service."),
                ],
            )

            async def fake_worker(store, name, workspace, instructions, project_id=None):
                task = store.claim_next_task(name, project_id)
                if task is None:
                    return False
                store.complete_task(task["id"], name, f"Completed by {name}; checks passed.")
                return True

            with (
                patch("agents_swarm.projects._plan", new=AsyncMock(return_value=plan)),
                patch("agents_swarm.projects.run_agent", new=fake_worker),
                patch(
                    "agents_swarm.projects._make_report",
                    new=AsyncMock(return_value="# Sample service\\n\\nAll tasks completed.\\n"),
                ),
            ):
                project_id, report_path, report = await run_project_from_file(
                    store,
                    brief_file,
                    workspace,
                    root / "agent.txt",
                    ["agent-a", "agent-b"],
                )

            snapshot = store.project_snapshot(project_id)
            self.assertEqual([task["status"] for task in snapshot["tasks"]], ["done", "done"])
            self.assertTrue(report_path.is_file())
            self.assertIn("All tasks completed", report)
            self.assertEqual(report_path.parent, workspace / "reports")


if __name__ == "__main__":
    unittest.main()
