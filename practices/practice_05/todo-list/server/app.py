"""HTTP entry point: JSON API under /api/todos and the page on the same origin.

Run: python3 -m server.app [--port 8000] [--db data/todos.db]
The server listens on 127.0.0.1 and handles one request at a time (HTTPServer).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from . import static, storage, validation

logger = logging.getLogger("todo_server")

HOST = "127.0.0.1"
MAX_BODY_BYTES = 4096
MAX_SQLITE_INTEGER = 2**63 - 1

# Russian texts are copied from specs/001-todo-list/contract.md, section 4.
MSG_BAD_CONTENT_LENGTH = "Некорректный заголовок Content-Length."
MSG_BODY_NOT_OBJECT = "Тело запроса должно быть JSON-объектом."
MSG_TODO_NOT_FOUND = "Задача не найдена."
MSG_ROUTE_NOT_FOUND = "Маршрут не найден."
MSG_METHOD_NOT_ALLOWED = "Метод не поддерживается."
MSG_LENGTH_REQUIRED = "Требуется заголовок Content-Length."
MSG_BODY_TOO_LARGE = "Тело запроса слишком большое."
MSG_INTERNAL = "Внутренняя ошибка сервера."

API_TODOS = "/api/todos"
API_TODO_PREFIX = "/api/todos/"


class ApiError(Exception):
    """An error answered as {"error": message} with the given HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def parse_todo_id(text: str) -> Optional[int]:
    """Return the id as a positive integer, or None when the path segment is not a valid id."""
    if not re.fullmatch(r"[0-9]+", text):
        return None
    value = int(text)
    if value <= 0 or value > MAX_SQLITE_INTEGER:
        return None
    return value


class TodoRequestHandler(BaseHTTPRequestHandler):
    # Set by make_server() on a subclass.
    db_path: Path = storage.DEFAULT_DB_PATH
    static_dir: Path = static.STATIC_DIR

    server_version = "TodoList/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base class name
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
        try:
            if path == API_TODOS:
                if method == "GET":
                    self._list_todos()
                elif method == "POST":
                    self._create_todo()
                else:
                    raise ApiError(405, MSG_METHOD_NOT_ALLOWED)
            elif path.startswith(API_TODO_PREFIX):
                id_text = path[len(API_TODO_PREFIX):]
                if "/" in id_text:
                    raise ApiError(404, MSG_ROUTE_NOT_FOUND)
                if method == "PATCH":
                    self._set_done(id_text)
                elif method == "DELETE":
                    self._delete_todo(id_text)
                else:
                    raise ApiError(405, MSG_METHOD_NOT_ALLOWED)
            elif path == "/" or path.startswith(static.STATIC_PREFIX):
                if method != "GET":
                    raise ApiError(405, MSG_METHOD_NOT_ALLOWED)
                self._serve_static(path)
            else:
                raise ApiError(404, MSG_ROUTE_NOT_FOUND)
        except ApiError as error:
            self._send_json(error.status, {"error": error.message})
        except validation.ValidationError as error:
            self._send_json(400, {"error": error.message})
        except sqlite3.Error:
            logger.exception("Database error while handling %s %s", method, path)
            self._send_json(500, {"error": MSG_INTERNAL})
        except Exception:
            logger.exception("Unexpected error while handling %s %s", method, path)
            self._send_json(500, {"error": MSG_INTERNAL})

    # ----- body -----

    def _read_json_object(self) -> Dict[str, Any]:
        """Check Content-Length and size, then read the body as a JSON object.

        Checks run before JSON parsing (contract, section 3). Errors that leave the body
        unread close the connection, so the next request does not start inside it.
        """
        if self.headers.get("Transfer-Encoding") is not None:
            self.close_connection = True
            raise ApiError(411, MSG_LENGTH_REQUIRED)

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self.close_connection = True
            raise ApiError(411, MSG_LENGTH_REQUIRED)

        raw_length = raw_length.strip()
        if not re.fullmatch(r"[0-9]+", raw_length):
            self.close_connection = True
            raise ApiError(400, MSG_BAD_CONTENT_LENGTH)

        length = int(raw_length)
        if length > MAX_BODY_BYTES:
            # Body is not read: a single-threaded server must not wait for a large upload.
            self.close_connection = True
            raise ApiError(413, MSG_BODY_TOO_LARGE)

        raw_body = self.rfile.read(length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (ValueError, RecursionError):
            raise ApiError(400, MSG_BODY_NOT_OBJECT)
        if not isinstance(body, dict):
            raise ApiError(400, MSG_BODY_NOT_OBJECT)
        return body

    # ----- operations -----

    def _list_todos(self) -> None:
        with storage.connect(self.db_path) as conn:
            todos = storage.list_todos(conn)
        self._send_json(200, todos)

    def _create_todo(self) -> None:
        body = self._read_json_object()
        title = validation.normalize_title(body.get("title"))
        with storage.connect(self.db_path) as conn:
            todo_id = storage.insert_todo(conn, title)
        self._send_json(201, {"id": todo_id, "title": title, "done": False})

    def _set_done(self, id_text: str) -> None:
        body = self._read_json_object()
        done = validation.validate_done(body.get("done"))
        todo_id = parse_todo_id(id_text)
        with storage.connect(self.db_path) as conn:
            if todo_id is None or storage.set_done(conn, todo_id, done) == 0:
                raise ApiError(404, MSG_TODO_NOT_FOUND)
            todo = storage.get_todo(conn, todo_id)
        if todo is None:
            raise ApiError(404, MSG_TODO_NOT_FOUND)
        self._send_json(200, todo)

    def _delete_todo(self, id_text: str) -> None:
        todo_id = parse_todo_id(id_text)
        if todo_id is None:
            raise ApiError(404, MSG_TODO_NOT_FOUND)
        with storage.connect(self.db_path) as conn:
            deleted = storage.delete_todo(conn, todo_id)
        if deleted == 0:
            raise ApiError(404, MSG_TODO_NOT_FOUND)
        self._send_empty(204)

    def _serve_static(self, path: str) -> None:
        result = static.read_static(path, self.static_dir)
        if result is None:
            raise ApiError(404, MSG_ROUTE_NOT_FOUND)
        body, content_type = result
        self._send_bytes(200, body, content_type)

    # ----- responses -----

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":  # HEAD gets the headers only, as HTTP requires
            self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def make_server(
    port: int,
    db_path: Path,
    static_dir: Path = static.STATIC_DIR,
    host: str = HOST,
) -> HTTPServer:
    """Create the database if needed and return a bound (not yet serving) server.

    Port 0 picks a free port; tests read it from server.server_address.
    """
    storage.init_db(db_path)
    handler = type(
        "BoundTodoRequestHandler",
        (TodoRequestHandler,),
        {"db_path": Path(db_path), "static_dir": Path(static_dir)},
    )
    return HTTPServer((host, port), handler)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Todo-list server (API and page).")
    parser.add_argument("--port", type=int, default=8000, help="port, default 8000")
    parser.add_argument(
        "--db",
        type=Path,
        default=storage.DEFAULT_DB_PATH,
        help="SQLite file, default data/todos.db from the project root",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = make_server(args.port, args.db)
    logger.info("Serving on http://%s:%d, database %s", HOST, args.port, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
