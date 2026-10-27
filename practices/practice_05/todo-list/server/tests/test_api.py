"""HTTP tests on a real server with a temporary database and static folder.

Covers spec tests 12, 13-15, 16-17, 18-19, 20-26, 28-31 and the contract error texts.
"""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from server import app, validation


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.db = base / "data" / "todos.db"
        self.static_dir = base / "static"
        self.static_dir.mkdir()
        (self.static_dir / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
        (self.static_dir / "styles.css").write_text("body{}", encoding="utf-8")
        (self.static_dir / "app.js").write_text("// js", encoding="utf-8")
        (base / "secret.txt").write_text("secret", encoding="utf-8")

        self.server = app.make_server(0, self.db, self.static_dir)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    # ----- helpers -----

    def request(self, method, path, body=None, headers=None):
        """Send a request; return (status, headers, raw body bytes)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def json_request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        status, _, raw = self.request(method, path, body=body, headers=headers)
        return status, (json.loads(raw) if raw else None)

    def raw_request(self, method, path, head_headers, chunks=()):
        """Send headers exactly as given (no automatic Content-Length), then raw body chunks."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest(method, path, skip_accept_encoding=True)
            for name, value in head_headers.items():
                conn.putheader(name, value)
            conn.endheaders()
            for chunk in chunks:
                conn.send(chunk)
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b"null")
        finally:
            conn.close()

    def add(self, title):
        status, body = self.json_request("POST", "/api/todos", {"title": title})
        self.assertEqual(status, 201)
        return body["id"]

    def all_todos(self):
        status, body = self.json_request("GET", "/api/todos")
        self.assertEqual(status, 200)
        return body

    def assert_error(self, result, status, message):
        code, body = result
        self.assertEqual(code, status)
        self.assertEqual(body, {"error": message})


class ListTests(ApiTestCase):
    def test_empty_list_is_200_and_empty_array(self):
        status, body = self.json_request("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertEqual(body, [])

    def test_list_is_newest_first(self):
        self.add("A")
        self.add("B")
        self.add("C")
        self.assertEqual([t["title"] for t in self.all_todos()], ["C", "B", "A"])

    def test_list_shows_new_done_value_after_patch(self):
        todo_id = self.add("A")
        self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": True})
        self.assertIs(self.all_todos()[0]["done"], True)


class CreateTests(ApiTestCase):
    def test_create_returns_201_with_task(self):
        status, body = self.json_request("POST", "/api/todos", {"title": "Купить молоко"})
        self.assertEqual(status, 201)
        self.assertEqual(body["title"], "Купить молоко")
        self.assertIs(body["done"], False)
        self.assertIsInstance(body["id"], int)
        self.assertGreater(body["id"], 0)
        self.assertEqual(self.all_todos()[0]["id"], body["id"])

    def test_title_is_trimmed(self):
        status, body = self.json_request("POST", "/api/todos", {"title": "  Купить молоко \n"})
        self.assertEqual(status, 201)
        self.assertEqual(body["title"], "Купить молоко")

    def test_length_limits(self):
        self.assertEqual(self.json_request("POST", "/api/todos", {"title": "a"})[0], 201)
        self.assertEqual(self.json_request("POST", "/api/todos", {"title": "a" * 200})[0], 201)
        self.assert_error(
            self.json_request("POST", "/api/todos", {"title": "a" * 201}),
            400,
            validation.ERROR_TITLE_TOO_LONG,
        )
        self.assertEqual(self.json_request("POST", "/api/todos", {"title": "я" * 200})[0], 201)
        self.assert_error(
            self.json_request("POST", "/api/todos", {"title": "я" * 201}),
            400,
            validation.ERROR_TITLE_TOO_LONG,
        )

    def test_empty_title_is_400(self):
        for title in ("", "   "):
            with self.subTest(title=title):
                self.assert_error(
                    self.json_request("POST", "/api/todos", {"title": title}),
                    400,
                    validation.ERROR_TITLE_EMPTY,
                )
        self.assertEqual(self.all_todos(), [])

    def test_non_string_title_is_400(self):
        self.assert_error(
            self.json_request("POST", "/api/todos", {"title": 5}),
            400,
            validation.ERROR_TITLE_NOT_STRING,
        )

    def test_missing_title_is_400(self):
        self.assert_error(
            self.json_request("POST", "/api/todos", {"other": "x"}),
            400,
            validation.ERROR_TITLE_NOT_STRING,
        )

    def test_body_not_json_is_400(self):
        status, headers, raw = self.request(
            "POST", "/api/todos", body=b"{not json", headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw), {"error": "Тело запроса должно быть JSON-объектом."})

    def test_body_not_object_is_400(self):
        self.assert_error(
            self.json_request("POST", "/api/todos", ["Купить"]),
            400,
            "Тело запроса должно быть JSON-объектом.",
        )

    def test_invalid_utf8_body_is_400(self):
        status, _, raw = self.request("POST", "/api/todos", body=b"\xff\xfe\xfd")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"], "Тело запроса должно быть JSON-объектом.")

    def test_content_length_missing_is_411_and_db_unchanged(self):
        status, body = self.raw_request(
            "POST", "/api/todos", {"Host": "127.0.0.1", "Content-Type": "application/json"}
        )
        self.assertEqual(status, 411)
        self.assertEqual(body, {"error": "Требуется заголовок Content-Length."})
        self.assertEqual(self.all_todos(), [])

    def test_transfer_encoding_chunked_is_411(self):
        payload = json.dumps({"title": "Купить молоко"}).encode("utf-8")
        chunk = b"%x\r\n%s\r\n0\r\n\r\n" % (len(payload), payload)
        status, body = self.raw_request(
            "POST",
            "/api/todos",
            {
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                "Transfer-Encoding": "chunked",
            },
            chunks=(chunk,),
        )
        self.assertEqual(status, 411)
        self.assertEqual(body, {"error": "Требуется заголовок Content-Length."})
        self.assertEqual(self.all_todos(), [])

    def test_invalid_content_length_is_400(self):
        for value in ("abc", "-5", "1.5"):
            with self.subTest(value=value):
                status, body = self.raw_request(
                    "POST",
                    "/api/todos",
                    {"Host": "127.0.0.1", "Content-Length": value},
                )
                self.assertEqual(status, 400)
                self.assertEqual(body, {"error": "Некорректный заголовок Content-Length."})
        self.assertEqual(self.all_todos(), [])

    def test_oversized_body_is_413_and_next_request_works(self):
        big = json.dumps({"title": "a" * 5000}).encode("utf-8")
        status, _, raw = self.request(
            "POST", "/api/todos", body=big, headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(raw), {"error": "Тело запроса слишком большое."})
        self.assertEqual(self.all_todos(), [])

        status, body = self.json_request("POST", "/api/todos", {"title": "После большого"})
        self.assertEqual(status, 201)
        self.assertEqual(body["title"], "После большого")


class PatchTests(ApiTestCase):
    def test_mark_and_unmark(self):
        todo_id = self.add("Задача")
        status, body = self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": True})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"id": todo_id, "title": "Задача", "done": True})

        status, body = self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": False})
        self.assertEqual(status, 200)
        self.assertIs(body["done"], False)

    def test_repeated_mark_is_200(self):
        todo_id = self.add("Задача")
        self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": True})
        status, body = self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": True})
        self.assertEqual(status, 200)
        self.assertIs(body["done"], True)

    def test_done_as_string_is_400(self):
        todo_id = self.add("Задача")
        self.assert_error(
            self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": "true"}),
            400,
            validation.ERROR_DONE_NOT_BOOL,
        )

    def test_missing_done_is_400(self):
        todo_id = self.add("Задача")
        self.assert_error(
            self.json_request("PATCH", f"/api/todos/{todo_id}", {}),
            400,
            validation.ERROR_DONE_NOT_BOOL,
        )

    def test_unknown_id_is_404_and_db_unchanged(self):
        todo_id = self.add("Задача")
        self.assert_error(
            self.json_request("PATCH", f"/api/todos/{todo_id + 100}", {"done": True}),
            404,
            "Задача не найдена.",
        )
        self.assertIs(self.all_todos()[0]["done"], False)

    def test_non_numeric_id_is_404(self):
        self.assert_error(
            self.json_request("PATCH", "/api/todos/abc", {"done": True}),
            404,
            "Задача не найдена.",
        )

    def test_zero_and_huge_id_are_404(self):
        for todo_id in ("0", "99999999999999999999999"):
            with self.subTest(todo_id=todo_id):
                self.assert_error(
                    self.json_request("PATCH", f"/api/todos/{todo_id}", {"done": True}),
                    404,
                    "Задача не найдена.",
                )

    def test_bad_body_on_missing_id_is_400_not_404(self):
        self.assert_error(
            self.json_request("PATCH", "/api/todos/999", {"done": "yes"}),
            400,
            validation.ERROR_DONE_NOT_BOOL,
        )

    def test_patch_without_content_length_is_411(self):
        todo_id = self.add("Задача")
        status, body = self.raw_request(
            "PATCH", f"/api/todos/{todo_id}", {"Host": "127.0.0.1"}
        )
        self.assertEqual(status, 411)
        self.assertEqual(body, {"error": "Требуется заголовок Content-Length."})
        self.assertIs(self.all_todos()[0]["done"], False)


class DeleteTests(ApiTestCase):
    def test_delete_returns_204_without_body(self):
        todo_id = self.add("Задача")
        status, headers, raw = self.request("DELETE", f"/api/todos/{todo_id}")
        self.assertEqual(status, 204)
        self.assertEqual(raw, b"")
        self.assertEqual(self.all_todos(), [])

    def test_repeated_delete_is_404(self):
        todo_id = self.add("Задача")
        self.request("DELETE", f"/api/todos/{todo_id}")
        self.assert_error(
            self.json_request("DELETE", f"/api/todos/{todo_id}"), 404, "Задача не найдена."
        )

    def test_unknown_and_non_numeric_id_are_404(self):
        for path in ("/api/todos/999", "/api/todos/abc"):
            with self.subTest(path=path):
                self.assert_error(
                    self.json_request("DELETE", path), 404, "Задача не найдена."
                )

    def test_new_id_after_delete_is_greater(self):
        first = self.add("A")
        self.request("DELETE", f"/api/todos/{first}")
        second = self.add("B")
        self.assertGreater(second, first)


class RouteTests(ApiTestCase):
    def test_unknown_path_is_404(self):
        self.assert_error(self.json_request("GET", "/nope"), 404, "Маршрут не найден.")

    def test_wrong_method_is_405(self):
        cases = [
            ("PUT", "/api/todos"),
            ("DELETE", "/api/todos"),
            ("GET", "/api/todos/1"),
            ("POST", "/api/todos/1"),
            ("POST", "/"),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assert_error(
                    self.json_request(method, path), 405, "Метод не поддерживается."
                )


class UnsupportedMethodTests(ApiTestCase):
    def test_options_is_405_with_json_error(self):
        for path in ("/api/todos", "/api/todos/1", "/"):
            with self.subTest(path=path):
                status, headers, raw = self.request("OPTIONS", path)
                self.assertEqual(status, 405)
                self.assertEqual(json.loads(raw), {"error": "Метод не поддерживается."})

    def test_head_is_405_with_headers_and_no_body(self):
        for path in ("/api/todos", "/api/todos/1", "/"):
            with self.subTest(path=path):
                status, headers, raw = self.request("HEAD", path)
                self.assertEqual(status, 405)
                self.assertGreater(int(headers["Content-Length"]), 0)
                self.assertEqual(raw, b"")


class StaticRouteTests(ApiTestCase):
    def test_root_serves_html(self):
        status, headers, raw = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"<!doctype html>", raw)

    def test_css_and_js_types(self):
        status, headers, raw = self.request("GET", "/static/styles.css")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        status, headers, raw = self.request("GET", "/static/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/javascript; charset=utf-8")

    def test_missing_static_file_is_404_with_route_text(self):
        status, _, raw = self.request("GET", "/static/missing.js")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(raw), {"error": "Маршрут не найден."})

    def test_parent_reference_is_404(self):
        status, _, raw = self.request("GET", "/static/../secret.txt")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(raw), {"error": "Маршрут не найден."})


if __name__ == "__main__":
    unittest.main()
