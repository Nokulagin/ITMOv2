"""SQLite storage: schema, connection handling and the table operations.

Every operation opens its own connection (contract, section 10 / decision 10)
and closes it when the block ends.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "todos.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0
)
"""


@contextlib.contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection; commit on success, roll back on error, always close.

    `with conn:` alone does not close the connection (sqlite3 docs), so close is explicit.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Create the folder and the table if they are missing. Existing rows are kept."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute(SCHEMA)


def _row_to_todo(row: Any) -> Dict[str, Any]:
    todo_id, title, done = row
    return {"id": todo_id, "title": title, "done": bool(done)}


def insert_todo(conn: sqlite3.Connection, title: str) -> int:
    """Insert a task with done = 0 and return its new id."""
    cursor = conn.execute("INSERT INTO todos (title, done) VALUES (?, 0)", (title,))
    return int(cursor.lastrowid)


def get_todo(conn: sqlite3.Connection, todo_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT id, title, done FROM todos WHERE id = ?", (todo_id,)).fetchone()
    return _row_to_todo(row) if row is not None else None


def set_done(conn: sqlite3.Connection, todo_id: int, done: bool) -> int:
    """Set done to 1 or 0. Return the number of rows matched (0 means no such id)."""
    cursor = conn.execute(
        "UPDATE todos SET done = ? WHERE id = ?", (1 if done else 0, todo_id)
    )
    return cursor.rowcount


def delete_todo(conn: sqlite3.Connection, todo_id: int) -> int:
    """Delete the row. Return the number of deleted rows."""
    cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return cursor.rowcount


def list_todos(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """All tasks, newest first (id descending)."""
    rows = conn.execute("SELECT id, title, done FROM todos ORDER BY id DESC").fetchall()
    return [_row_to_todo(row) for row in rows]
