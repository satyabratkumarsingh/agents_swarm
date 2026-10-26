"""SQLite persistence for tasks, shared board entries, and agent messages."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TeamStore:
    """Small persistent coordination store used by all local agents."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._init_lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    project_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    owner TEXT,
                    claimed_at TEXT,
                    completed_at TEXT,
                    summary TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    brief TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned'
                );
                CREATE TABLE IF NOT EXISTS board (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    author TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL DEFAULT 'team',
                    content TEXT NOT NULL
                );
                """
            )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
            }
            if "description" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''"
                )
            if "project_id" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN project_id INTEGER")

    def add_tasks(self, titles: list[str]) -> list[int]:
        ids: list[int] = []
        with self._connect() as connection:
            for title in titles:
                cursor = connection.execute(
                    "INSERT INTO tasks (title) VALUES (?)", (title.strip(),)
                )
                ids.append(int(cursor.lastrowid))
        return ids

    def create_project(self, title: str, brief: str, tasks: list[dict[str, str]]) -> tuple[int, list[int]]:
        """Persist a source brief and its decomposed tasks as one transaction."""
        if not tasks:
            raise ValueError("A project plan must contain at least one task")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_cursor = connection.execute(
                "INSERT INTO projects (title, brief, created_at) VALUES (?, ?, ?)",
                (title.strip(), brief.strip(), _now()),
            )
            project_id = int(project_cursor.lastrowid)
            task_ids: list[int] = []
            for task in tasks:
                cursor = connection.execute(
                    "INSERT INTO tasks (title, description, project_id) VALUES (?, ?, ?)",
                    (task["title"].strip(), task["description"].strip(), project_id),
                )
                task_ids.append(int(cursor.lastrowid))
            connection.commit()
        return project_id, task_ids

    def claim_next_task(self, agent: str, project_id: int | None = None) -> dict[str, Any] | None:
        """Atomically claim the next pending task and publish a CLAIM entry."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if project_id is None:
                row = connection.execute(
                    "SELECT tasks.id, tasks.title, tasks.description, projects.title AS project_title, "
                    "projects.brief AS project_brief FROM tasks "
                    "LEFT JOIN projects ON projects.id=tasks.project_id "
                    "WHERE tasks.status = 'pending' ORDER BY tasks.id LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT tasks.id, tasks.title, tasks.description, projects.title AS project_title, "
                    "projects.brief AS project_brief FROM tasks "
                    "LEFT JOIN projects ON projects.id=tasks.project_id "
                    "WHERE tasks.status = 'pending' AND tasks.project_id=? ORDER BY tasks.id LIMIT 1",
                    (project_id,),
                ).fetchone()
            if row is None:
                connection.commit()
                return None
            task_id = int(row["id"])
            claimed_at = _now()
            connection.execute(
                "UPDATE tasks SET status='claimed', owner=?, claimed_at=? WHERE id=?",
                (agent, claimed_at, task_id),
            )
            connection.execute(
                "INSERT INTO board (created_at, author, kind, content, task_id) VALUES (?, ?, ?, ?, ?)",
                (claimed_at, agent, "CLAIM", f"task={task_id} | {row['title']}", task_id),
            )
            connection.commit()
            return {
                "id": task_id,
                "title": str(row["title"]),
                "description": str(row["description"]),
                "project_id": project_id,
                "project_title": str(row["project_title"] or ""),
                "project_brief": str(row["project_brief"] or ""),
            }

    def fail_task(self, task_id: int, agent: str, reason: str) -> bool:
        """Mark an execution failure terminal to avoid automatic API-costly retries."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE tasks SET status='failed', completed_at=?, summary=? "
                "WHERE id=? AND owner=? AND status='claimed'",
                (_now(), reason.strip(), task_id, agent),
            )
            if cursor.rowcount:
                connection.execute(
                    "INSERT INTO board (created_at, author, kind, content, task_id) VALUES (?, ?, ?, ?, ?)",
                    (_now(), agent, "FAIL", reason.strip(), task_id),
                )
            connection.commit()
            return cursor.rowcount == 1

    def task_status(self, task_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        return str(row["status"]) if row else None

    def project_snapshot(self, project_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            project = connection.execute(
                "SELECT id, title, brief, created_at, status FROM projects WHERE id=?",
                (project_id,),
            ).fetchone()
            if project is None:
                return None
            tasks = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, title, description, status, owner, summary FROM tasks "
                    "WHERE project_id=? ORDER BY id",
                    (project_id,),
                )
            ]
            board = [
                dict(row)
                for row in connection.execute(
                    "SELECT created_at, author, kind, content, task_id FROM board "
                    "WHERE task_id IN (SELECT id FROM tasks WHERE project_id=?) ORDER BY id",
                    (project_id,),
                )
            ]
        return {"project": dict(project), "tasks": tasks, "board": board}

    def set_project_status(self, project_id: int, status: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE projects SET status=? WHERE id=?", (status, project_id))

    def complete_task(self, task_id: int, agent: str, summary: str) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE tasks SET status='done', completed_at=?, summary=? "
                "WHERE id=? AND owner=? AND status='claimed'",
                (_now(), summary.strip(), task_id, agent),
            )
            if cursor.rowcount:
                connection.execute(
                    "INSERT INTO board (created_at, author, kind, content, task_id) VALUES (?, ?, ?, ?, ?)",
                    (_now(), agent, "PATCH_SUMMARY", summary.strip(), task_id),
                )
            connection.commit()
            return cursor.rowcount == 1

    def release_task(self, task_id: int, agent: str, reason: str) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE tasks SET status='blocked', owner=NULL, claimed_at=NULL, summary=? "
                "WHERE id=? AND owner=? AND status='claimed'",
                (reason.strip(), task_id, agent),
            )
            if cursor.rowcount:
                connection.execute(
                    "INSERT INTO board (created_at, author, kind, content, task_id) VALUES (?, ?, ?, ?, ?)",
                    (_now(), agent, "BLOCKED", reason.strip(), task_id),
                )
            connection.commit()
            return cursor.rowcount == 1

    def post_board(self, author: str, kind: str, content: str, task_id: int | None = None) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO board (created_at, author, kind, content, task_id) VALUES (?, ?, ?, ?, ?)",
                (_now(), author, kind.upper(), content.strip(), task_id),
            )
            return int(cursor.lastrowid)

    def post_message(self, sender: str, recipient: str, content: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (created_at, sender, recipient, content) VALUES (?, ?, ?, ?)",
                (_now(), sender, recipient.strip() or "team", content.strip()),
            )
            return int(cursor.lastrowid)

    def snapshot(self, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as connection:
            tasks = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, title, status, owner, summary FROM tasks ORDER BY id"
                )
            ]
            board = [
                dict(row)
                for row in connection.execute(
                    "SELECT created_at, author, kind, content, task_id FROM board ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            ]
            messages = [
                dict(row)
                for row in connection.execute(
                    "SELECT created_at, sender, recipient, content FROM messages ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            ]
        return {
            "tasks": tasks,
            "board": list(reversed(board)),
            "messages": list(reversed(messages)),
        }

    def status_json(self) -> str:
        return json.dumps(self.snapshot(), indent=2, ensure_ascii=False)
