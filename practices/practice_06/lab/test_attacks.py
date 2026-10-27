"""Регрессионные тесты против найденных атак (REPORT_01 / THREAT_MODEL).

Каждый тест кодирует защищённое поведение: он проходит на исправленном сервисе
и падал бы на исходной уязвимой версии. Данные синтетические.
"""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from service import Shop, make_handler


class AttackTest(unittest.TestCase):
    def setUp(self):
        self.shop = Shop()
        self.addCleanup(self.shop.close)

    def request(self, method, path, body=None, headers=None):
        with self.shop.lock:
            return self.shop.dispatch(method, path, body or {}, headers or {})

    def auth(self, username="alice", password="learn-alice"):
        status, result = self.request("POST", "/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        return {"X-Token": result["token"]}

    # T-01/02/03 — SQL-инъекция
    def test_sqli_in_search_is_not_executed(self):
        staff = self.auth("staff", "learn-staff")
        status, result = self.request(
            "GET", "/search?q=%' UNION SELECT id,name,email,address FROM profiles --", headers=staff)
        self.assertEqual(status, 200)
        # Инъекция трактуется как литерал поиска: совпадений нет, дамп не происходит.
        self.assertEqual(result, [])

    def test_sqli_in_profile_id_rejected(self):
        auth = self.auth()
        status, _ = self.request("GET", "/profile?id=1 OR 1=1", headers=auth)
        self.assertEqual(status, 400)

    # T-04 — IDOR на /profile
    def test_customer_cannot_read_other_profile(self):
        auth = self.auth()  # alice (id 1)
        self.assertEqual(self.request("GET", "/profile?id=2", headers=auth)[0], 403)

    def test_profile_requires_session(self):
        self.assertEqual(self.request("GET", "/profile?id=1")[0], 401)

    # T-05 — IDOR на /files
    def test_customer_cannot_read_other_receipt(self):
        auth = self.auth()  # alice
        status, result = self.request("GET", "/files?user=bob&path=receipt.txt", headers=auth)
        # user из query игнорируется: клиент получает только свой чек.
        self.assertEqual(status, 200)
        self.assertIn("TEST_ALICE", result["content"])

    def test_files_requires_session(self):
        self.assertEqual(self.request("GET", "/files?user=bob&path=receipt.txt")[0], 401)

    # T-07 — /orders без аутентификации / фильтр владельца
    def test_orders_requires_session(self):
        self.assertEqual(self.request("GET", "/orders")[0], 401)

    def test_customer_orders_scoped_to_owner(self):
        auth = self.auth()  # alice (id 1)
        status, orders = self.request("GET", "/orders", headers=auth)
        self.assertEqual(status, 200)
        self.assertTrue(orders and all(o["owner"] == 1 for o in orders))

    # T-08 — подделка цены
    def test_price_from_catalog_not_from_body(self):
        status, order = self.request("POST", "/orders", {"product": "chair", "price": 1}, self.auth())
        self.assertEqual(status, 201)
        self.assertEqual(order["price"], 5000)

    # T-09 — повышение привилегий через X-Role
    def test_x_role_header_grants_nothing(self):
        auth = {**self.auth(), "X-Role": "staff"}  # alice с поддельной ролью в заголовке
        self.assertEqual(self.request("GET", "/admin/export", headers=auth)[0], 403)

    def test_export_without_session_forbidden(self):
        self.assertEqual(self.request("GET", "/admin/export", headers={"X-Role": "staff"})[0], 403)

    # T-10 — /debug/logs и утечка секретов
    def test_debug_logs_requires_staff(self):
        self.assertEqual(self.request("GET", "/debug/logs")[0], 403)
        self.assertEqual(self.request("GET", "/debug/logs", headers=self.auth())[0], 403)

    def test_logs_do_not_store_password_or_token(self):
        auth = self.auth()
        self.request("GET", "/orders", headers=auth)
        staff = self.auth("staff", "learn-staff")
        status, logs = self.request("GET", "/debug/logs", headers=staff)
        self.assertEqual(status, 200)
        blob = str(logs)
        self.assertNotIn("learn-alice", blob)
        self.assertNotIn(auth["X-Token"], blob)

    # T-11 — отзывы без аутентификации
    def test_review_requires_session(self):
        self.assertEqual(self.request("POST", "/reviews", {"product": "chair", "text": "x"})[0], 401)

    # T-12 — хранимый XSS
    def test_review_html_is_escaped(self):
        auth = self.auth()
        self.request("POST", "/reviews", {"product": "chair", "text": "<script>alert(1)</script>"}, auth)
        html = self.request("GET", "/reviews/view", headers=auth)[1]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    # T-15 — исполнитель без сессии
    def test_execute_requires_session(self):
        decision = {"decision": {"tool": "read_file", "arguments": {"path": "files/bob/receipt.txt"}}}
        self.assertEqual(self.request("POST", "/assistant/execute", decision)[0], 401)

    # T-16 — read_file чужого чека / служебной заметки
    def test_execute_read_file_scoped_to_owner(self):
        auth = self.auth()  # alice
        for path in ("files/bob/receipt.txt", "private/operator-note.txt"):
            with self.subTest(path=path):
                status, _ = self.request(
                    "POST", "/assistant/execute",
                    {"decision": {"tool": "read_file", "arguments": {"path": path}}}, auth)
                self.assertEqual(status, 403)

    def test_execute_read_own_receipt_still_works(self):
        auth = self.auth()
        status, result = self.request(
            "POST", "/assistant/execute",
            {"decision": {"tool": "read_file", "arguments": {"path": "files/alice/receipt.txt"}}}, auth)
        self.assertEqual(status, 200)
        self.assertIn("TEST_ALICE", result["content"])

    # T-17 — export_profiles только для staff
    def test_execute_export_profiles_customer_forbidden(self):
        auth = self.auth()
        status, _ = self.request(
            "POST", "/assistant/execute", {"decision": {"tool": "export_profiles", "arguments": {}}}, auth)
        self.assertEqual(status, 403)

    # T-18 — delete_tree недоступен через исполнитель (защита независима от LLM)
    def test_execute_delete_tree_forbidden_even_for_staff(self):
        for who in (self.auth(), self.auth("staff", "learn-staff")):
            status, _ = self.request(
                "POST", "/assistant/execute",
                {"decision": {"tool": "delete_tree", "arguments": {"path": "."}}}, who)
            self.assertEqual(status, 403)
        # Файлы на месте: удаления не было.
        self.assertTrue((self.shop.sandbox.root / "files" / "alice" / "receipt.txt").exists())


# T-19 — ответ 500 не раскрывает детали исключения (свойство HTTP-обработчика)
class ErrorLeakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shop = Shop()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.shop))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.shop.close()

    def call(self, method, path, body=None, headers=None):
        request = Request(self.base + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Content-Type": "application/json", **(headers or {})}, method=method)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read().decode()

    def test_internal_error_is_generic(self):
        token = json.loads(self.call("POST", "/login",
                                     {"username": "alice", "password": "learn-alice"})[1])["token"]
        status, body = self.call("POST", "/orders", {}, {"X-Token": token})  # missing product -> KeyError
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body), {"error": "internal error"})


if __name__ == "__main__":
    unittest.main()
