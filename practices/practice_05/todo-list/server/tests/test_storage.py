"""Storage operations on a temporary database (spec tests 1-2, 3, 15, 18, 20-27)."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from server import storage


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.db = self.base / "todos.db"
        storage.init_db(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, title):
        with storage.connect(self.db) as conn:
            return storage.insert_todo(conn, title)


class InitTests(StorageTestCase):
    def test_init_creates_missing_folder_and_table(self):
        db = self.base / "data" / "todos.db"
        self.assertFalse(db.parent.exists())
        storage.init_db(db)
        self.assertTrue(db.is_file())
        with storage.connect(db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'todos'"
            ).fetchall()
        self.assertEqual(tables, [("todos",)])

    def test_restart_keeps_existing_rows(self):
        self.add("Сохранить")
        storage.init_db(self.db)
        with storage.connect(self.db) as conn:
            self.assertEqual([t["title"] for t in storage.list_todos(conn)], ["Сохранить"])


class InsertTests(StorageTestCase):
    def test_insert_returns_id_and_sets_done_false(self):
        todo_id = self.add("Купить молоко")
        self.assertGreater(todo_id, 0)
        with storage.connect(self.db) as conn:
            todo = storage.get_todo(conn, todo_id)
        self.assertEqual(todo, {"id": todo_id, "title": "Купить молоко", "done": False})

    def test_parameterized_title_is_stored_as_is(self):
        title = "Ole'); DROP TABLE todos; --"
        self.add(title)
        with storage.connect(self.db) as conn:
            todos = storage.list_todos(conn)
        self.assertEqual([t["title"] for t in todos], [title])


class SetDoneTests(StorageTestCase):
    def test_mark_and_unmark(self):
        todo_id = self.add("Задача")
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.set_done(conn, todo_id, True), 1)
            self.assertIs(storage.get_todo(conn, todo_id)["done"], True)
            self.assertEqual(storage.set_done(conn, todo_id, False), 1)
            self.assertIs(storage.get_todo(conn, todo_id)["done"], False)

    def test_repeated_same_value_is_not_an_error(self):
        todo_id = self.add("Задача")
        with storage.connect(self.db) as conn:
            storage.set_done(conn, todo_id, True)
            self.assertEqual(storage.set_done(conn, todo_id, True), 1)

    def test_unknown_id_changes_nothing(self):
        todo_id = self.add("Задача")
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.set_done(conn, todo_id + 100, True), 0)
            self.assertIs(storage.get_todo(conn, todo_id)["done"], False)


class DeleteTests(StorageTestCase):
    def test_delete_removes_row(self):
        todo_id = self.add("Задача")
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.delete_todo(conn, todo_id), 1)
            self.assertIsNone(storage.get_todo(conn, todo_id))

    def test_delete_unknown_id_returns_zero(self):
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.delete_todo(conn, 999), 0)

    def test_new_id_after_delete_is_greater(self):
        first = self.add("A")
        second = self.add("B")
        with storage.connect(self.db) as conn:
            storage.delete_todo(conn, second)
        third = self.add("C")
        self.assertGreater(third, second)
        self.assertGreater(second, first)


class ListTests(StorageTestCase):
    def test_empty_database_gives_empty_list(self):
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.list_todos(conn), [])

    def test_newest_first(self):
        self.add("A")
        self.add("B")
        self.add("C")
        with storage.connect(self.db) as conn:
            titles = [t["title"] for t in storage.list_todos(conn)]
        self.assertEqual(titles, ["C", "B", "A"])

    def test_done_is_returned_as_bool(self):
        todo_id = self.add("A")
        with storage.connect(self.db) as conn:
            storage.set_done(conn, todo_id, True)
            todos = storage.list_todos(conn)
        self.assertIs(todos[0]["done"], True)


class ConnectTests(StorageTestCase):
    def test_failed_block_rolls_back(self):
        with self.assertRaises(RuntimeError):
            with storage.connect(self.db) as conn:
                storage.insert_todo(conn, "не должна сохраниться")
                raise RuntimeError("boom")
        with storage.connect(self.db) as conn:
            self.assertEqual(storage.list_todos(conn), [])

    def test_connection_is_closed_after_block(self):
        with storage.connect(self.db) as conn:
            pass
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
