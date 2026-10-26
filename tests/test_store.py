from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agents_swarm.storage import TeamStore


class TeamStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "team.sqlite3"
        self.store = TeamStore(self.store_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_concurrent_workers_only_claim_task_once(self) -> None:
        self.store.add_tasks(["first task"])
        agents = ["agent-a", "agent-b"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda name: TeamStore(self.store_path).claim_next_task(name), agents)
            )
        claims = [result for result in results if result is not None]
        self.assertEqual(len(claims), 1)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["tasks"][0]["status"], "claimed")
        self.assertEqual(snapshot["board"][0]["kind"], "CLAIM")

    def test_completion_records_summary(self) -> None:
        task_id = self.store.add_tasks(["document the API"])[0]
        self.store.claim_next_task("agent-a")
        self.assertTrue(self.store.complete_task(task_id, "agent-a", "docs updated; test passed"))
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["tasks"][0]["status"], "done")
        self.assertEqual(snapshot["tasks"][0]["summary"], "docs updated; test passed")
        self.assertEqual(snapshot["board"][-1]["kind"], "PATCH_SUMMARY")

    def test_messages_are_shared_and_persistent(self) -> None:
        self.store.post_message("agent-a", "agent-b", "I found the config entry point")
        snapshot = TeamStore(self.store_path).snapshot()
        self.assertEqual(snapshot["messages"][0]["recipient"], "agent-b")
        self.assertIn("config entry point", snapshot["messages"][0]["content"])

    def test_project_and_subtasks_are_persisted_together(self) -> None:
        project_id, task_ids = self.store.create_project(
            "Portfolio analyzer",
            "Build a portfolio exposure analysis tool.",
            [
                {"title": "Parse holdings", "description": "Load a CSV of holdings."},
                {"title": "Calculate sector exposure", "description": "Aggregate weights."},
            ],
        )
        snapshot = self.store.project_snapshot(project_id)
        self.assertEqual(len(task_ids), 2)
        self.assertEqual(snapshot["project"]["title"], "Portfolio analyzer")
        self.assertEqual([task["title"] for task in snapshot["tasks"]], [
            "Parse holdings",
            "Calculate sector exposure",
        ])

    def test_project_scoped_claim_does_not_take_other_projects_task(self) -> None:
        project_a, _ = self.store.create_project(
            "A", "Brief A", [{"title": "Task A", "description": "Only for A"}]
        )
        self.store.create_project(
            "B", "Brief B", [{"title": "Task B", "description": "Only for B"}]
        )
        task = self.store.claim_next_task("worker", project_a)
        self.assertEqual(task["title"], "Task A")
        self.assertEqual(task["project_id"], project_a)
        self.assertEqual(task["project_title"], "A")
        self.assertEqual(task["project_brief"], "Brief A")


if __name__ == "__main__":
    unittest.main()
