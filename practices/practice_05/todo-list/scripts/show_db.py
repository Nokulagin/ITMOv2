"""Print the tasks stored in the SQLite database, newest first.

Read-only: the database is opened with mode=ro, so the script never changes it.

Run from the project root:
    python3 scripts/show_db.py
    python3 scripts/show_db.py --db /path/to/other.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "todos.db"


def read_todos(db_path: Path) -> list:
    """Return (id, title, done) rows, newest first. Raises sqlite3.Error on problems."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return conn.execute("SELECT id, title, done FROM todos ORDER BY id DESC").fetchall()
    finally:
        conn.close()


def format_table(rows: list) -> str:
    """Build a plain-text table with a header and a row count."""
    header = ("id", "done", "title")
    body = [(str(todo_id), "yes" if done else "no", title) for todo_id, title, done in rows]
    widths = [max(len(value) for value in column) for column in zip(header, *body)]

    def line(values: tuple) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(values, widths)).rstrip()

    lines = [line(header), line(tuple("-" * width for width in widths))]
    lines += [line(values) for values in body]
    lines.append(f"\nTotal: {len(rows)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Show tasks stored in the todo-list database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite file, default data/todos.db")
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        print("Start the server once (python3 -m server.app) to create it.", file=sys.stderr)
        return 1

    try:
        rows = read_todos(args.db)
    except sqlite3.Error as error:
        print(f"Cannot read {args.db}: {error}", file=sys.stderr)
        return 1

    print(f"Database: {args.db}\n")
    print(format_table(rows) if rows else "No tasks yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
