"""Self-test for the sign-up backend (server/app.py) over real HTTP.

Usage: python3 scripts/test_backend.py [project_dir]
Starts the server on a free port with a temporary database, runs the server-side scenarios of
openspec/changes/signup-backend/specs/signup-submission/spec.md, and always stops the server.
"""

import http.client
import importlib.util
import json
import selectors
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

project_dir = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]).resolve()
app = project_dir / "server" / "app.py"
NBSP = " "

# program, months -> (monthly, discount %, discount ₽, total), written out by hand from docs/requirements.md
EXPECTED = {
  ("start", 1): (4900, 0, 0, 4900), ("start", 3): (4655, 5, 735, 13965), ("start", 6): (4410, 10, 2940, 26460),
  ("base", 1): (5900, 0, 0, 5900), ("base", 3): (5605, 5, 885, 16815), ("base", 6): (5310, 10, 3540, 31860),
  ("intensive", 1): (6900, 0, 0, 6900), ("intensive", 3): (6555, 5, 1035, 19665),
  ("intensive", 6): (6210, 10, 4140, 37260),
}
GRADE_FOR = {"start": 5, "base": 7, "intensive": 9}
VALID = {"program": "start", "grade": 5, "months": 6, "parent_name": "Анна", "email": "anna@example.ru",
         "consent": True}
RESPONSE_KEYS = {"id", "program", "program_name", "months", "monthly_rub", "discount_percent", "discount_rub",
                 "total_rub", "display"}

results = []


def expect(ok, label):
  results.append((bool(ok), label))


def load_quote():
  spec = importlib.util.spec_from_file_location("pricing_for_test", project_dir / "mcp" / "olympiad_pricing" / "server.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  contract = module.load_contract()
  return lambda program, months: module.quote({"program": program, "months": months}, contract)[1]


def start_server(db_path):
  proc = subprocess.Popen([sys.executable, str(app), "--port", "0", "--db", str(db_path)], cwd=project_dir,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
  selector = selectors.DefaultSelector()
  selector.register(proc.stdout, selectors.EVENT_READ)
  if not selector.select(timeout=5):
    raise RuntimeError("server did not start within 5 s")
  line = proc.stdout.readline().strip()
  if not line.startswith("Serving on http://127.0.0.1:"):
    raise RuntimeError(f"unexpected server output: {line!r}")
  return proc, int(line.rsplit(":", 1)[1])


class Client:
  def __init__(self, port):
    self.port = port

  def raw(self, method, path, body=None, headers=None, host=None, length=True):
    """Send one request; body is bytes or None. Returns (status, headers dict, body bytes)."""
    connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
    try:
      connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
      connection.putheader("Host", host or f"127.0.0.1:{self.port}")
      for name, value in (headers or {}).items():
        connection.putheader(name, value)
      if body is not None and length:
        connection.putheader("Content-Length", str(len(body)))
      connection.endheaders(body)
      response = connection.getresponse()
      return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
      connection.close()

  def post(self, data, content_type="application/json", **kwargs):
    body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
    return self.raw("POST", "/api/signup", body, {"Content-Type": content_type, **kwargs.pop("headers", {})}, **kwargs)


def as_json(body):
  try:
    return json.loads(body.decode("utf-8"))
  except ValueError:
    return None


def run(client, db_path, quote):
  def count():
    with sqlite3.connect(db_path) as connection:
      return connection.execute("SELECT COUNT(*) FROM signups").fetchone()[0]

  def last_row():
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
      return dict(connection.execute("SELECT * FROM signups ORDER BY id DESC LIMIT 1").fetchone())
    finally:
      connection.close()

  def rejected(label, status, response, expected_status, before):
    expect(status == expected_status, f"{label}: status {expected_status} (got {status})")
    expect(response[0].get("content-type") == "application/json; charset=utf-8", f"{label}: JSON content type")
    expect(count() == before, f"{label}: nothing stored")

  # Accept a valid sign-up
  before = count()
  status, headers, body = client.post(VALID)
  data = as_json(body) or {}
  expect(status == 201, "valid request: 201")
  expect(isinstance(data.get("id"), int) and not isinstance(data.get("id"), bool), "valid request: integer id")
  expect((data.get("program"), data.get("program_name"), data.get("months")) == ("start", "Старт", 6),
         "valid request: program start / Старт, months 6")
  expect((data.get("monthly_rub"), data.get("discount_percent"), data.get("discount_rub"), data.get("total_rub"))
         == (4410, 10, 2940, 26460), "valid request: 4410 / 10% / 2940 / 26460")
  expect((data.get("display") or {}).get("total") == f"26{NBSP}460{NBSP}₽", "valid request: display.total «26 460 ₽» (NBSP)")
  expect(set(data) == RESPONSE_KEYS, "valid request: response has exactly the documented keys")
  expect(count() == before + 1, "valid request: exactly one row stored")
  row = last_row()
  expect({k: row[k] for k in ("program", "grade", "months", "parent_name", "email", "monthly_rub",
                               "discount_percent", "discount_rub", "total_rub")}
         == {"program": "start", "grade": 5, "months": 6, "parent_name": "Анна", "email": "anna@example.ru",
             "monthly_rub": 4410, "discount_percent": 10, "discount_rub": 2940, "total_rub": 26460},
         "valid request: stored row has the listed values")

  # Every program and duration equals quote() and the hand-written table
  for (program, months), numbers in EXPECTED.items():
    status, _, body = client.post({**VALID, "program": program, "grade": GRADE_FOR[program], "months": months})
    data = as_json(body) or {}
    reference = quote(program, months)
    same = all(data.get(k) == reference[k] for k in ("monthly_rub", "discount_percent", "discount_rub", "total_rub",
                                                     "display"))
    expect(status == 201 and same and (data["monthly_rub"], data["discount_percent"], data["discount_rub"],
                                       data["total_rub"]) == numbers, f"price {program} × {months}: equals quote()")

  # Stored text is trimmed
  status, _, body = client.post({**VALID, "parent_name": "  Анна  ", "email": " anna@example.ru "})
  row = last_row()
  expect(status == 201 and (row["parent_name"], row["email"]) == ("Анна", "anna@example.ru"),
         "trimmed name and email are stored")

  # Client sends a fake price and unknown fields
  status, _, body = client.post({**VALID, "monthly_rub": 1, "discount_percent": 99, "discount_rub": 1, "total_rub": 1,
                                 "display": {"total": "1 ₽"}, "admin": True})
  data = as_json(body) or {}
  row = last_row()
  expect(status == 201 and data.get("total_rub") == 26460 and data.get("monthly_rub") == 4410
         and data.get("discount_percent") == 10 and data.get("discount_rub") == 2940
         and data["display"]["total"] != "1 ₽", "fake price fields are ignored in the response")
  expect(row["total_rub"] == 26460 and "admin" not in row and set(data) == RESPONSE_KEYS,
         "fake price and unknown fields are not stored or echoed")

  # Missing fields and no consent
  before = count()
  status, headers, body = client.post({"program": "base", "grade": 7, "months": 1, "parent_name": "", "email": "x",
                                       "consent": False})
  rejected("three errors", status, (headers,), 400, before)
  expect(as_json(body) == {"errors": {"parent_name": "Укажите имя родителя.",
                                      "email": "Проверьте email: например, name@example.ru.",
                                      "consent": "Нужно согласие на обработку данных."}},
         "three errors: exactly parent_name, email, consent with the page's messages")

  # Field-error table
  missing = object()
  table = [
    ("program", missing, "Выберите программу."), ("program", 1, "Выберите программу."),
    ("program", "olymp", "Выберите программу."),
    ("grade", missing, "Выберите класс ребёнка."), ("grade", "7", "Выберите класс ребёнка."),
    ("grade", 7.0, "Выберите класс ребёнка."), ("grade", True, "Выберите класс ребёнка."),
    ("grade", 4, "Выберите класс ребёнка."), ("grade", 10, "Выберите класс ребёнка."),
    ("months", missing, "Выберите срок обучения."), ("months", "6", "Выберите срок обучения."),
    ("months", 2, "Выберите срок обучения."), ("months", True, "Выберите срок обучения."),
    ("parent_name", missing, "Укажите имя родителя."), ("parent_name", 5, "Укажите имя родителя."),
    ("parent_name", "   ", "Укажите имя родителя."), ("parent_name", "Ан\nна", "Укажите имя родителя."),
    ("parent_name", "Ан\x07на", "Укажите имя родителя."),
    ("parent_name", "А" * 101, "Имя — не длиннее 100 символов."),
    ("email", missing, "Укажите email родителя."), ("email", None, "Укажите email родителя."),
    ("email", "  ", "Укажите email родителя."),
    ("email", "anna@example", "Проверьте email: например, name@example.ru."),
    ("email", "an na@example.ru", "Проверьте email: например, name@example.ru."),
    ("email", "a" * 250 + "@x.ru", "Email — не длиннее 254 символов."),
    ("consent", missing, "Нужно согласие на обработку данных."),
    ("consent", "true", "Нужно согласие на обработку данных."),
    ("consent", 1, "Нужно согласие на обработку данных."),
    ("consent", False, "Нужно согласие на обработку данных."),
  ]
  for field, value, message in table:
    payload = {k: v for k, v in VALID.items() if k != field}
    if value is not missing:
      payload[field] = value
    before = count()
    status, headers, body = client.post(payload)
    label = f"{field}={'missing' if value is missing else repr(value)[:24]}"
    rejected(label, status, (headers,), 400, before)
    expect(as_json(body) == {"errors": {field: message}}, f"{label}: only «{message}»")
  status, _, _ = client.post({**VALID, "parent_name": "А" * 100, "email": "a" * 249 + "@x.ru"})
  expect(status == 201, "name of 100 and email of 254 characters are accepted")

  # Grade does not match the program
  before = count()
  status, headers, body = client.post({**VALID, "program": "start", "grade": 7})
  rejected("grade mismatch", status, (headers,), 400, before)
  expect(as_json(body) == {"errors": {"program": "Для 7 класса подходит «Основа»."}, "suggested_program": "base"},
         "grade mismatch: exact body with suggested_program base")

  # Only same-origin JSON requests
  before = count()
  status, headers, _ = client.post(VALID, content_type="text/plain")
  rejected("text/plain", status, (headers,), 415, before)
  status, headers, _ = client.post(VALID, content_type="application/json; charset=utf-8")
  expect(status == 201, "application/json with charset is accepted")
  before = count()
  status, headers, _ = client.post(VALID, headers={"Origin": "http://evil.example"})
  rejected("foreign Origin", status, (headers,), 403, before)
  status, headers, _ = client.post(VALID, headers={"Origin": "null"})
  rejected("Origin null", status, (headers,), 403, before)
  status, headers, _ = client.post(VALID, host=f"evil.example:{client.port}")
  rejected("foreign Host", status, (headers,), 403, before)
  status, _, _ = client.post(VALID, headers={"Origin": f"http://localhost:{client.port}"},
                             host=f"localhost:{client.port}")
  expect(status == 201, "same-origin request via localhost is accepted")

  # Malformed requests
  before = count()
  status, headers, _ = client.raw("POST", "/api/signup", b"{}", {"Content-Type": "application/json"}, length=False)
  rejected("no Content-Length", status, (headers,), 411, before)
  status, headers, _ = client.raw("POST", "/api/signup", None,
                                  {"Content-Type": "application/json", "Content-Length": "10241"})
  rejected("Content-Length 10241", status, (headers,), 413, before)
  for label, raw in (("broken JSON", b"{not json"), ("JSON []", b"[]"), ("JSON null", b"null"), ("empty body", b""),
                     ("not UTF-8", b"\xff\xfe")):
    status, headers, body = client.post(raw)
    rejected(label, status, (headers,), 400, before)
    expect("error" in (as_json(body) or {}), f"{label}: JSON error body")
  status, _, _ = client.post(VALID)
  expect(status == 201, "after malformed requests the server still accepts a valid one")

  status, headers, _ = client.raw("GET", "/api/signup")
  rejected("GET /api/signup", status, (headers,), 405, count())
  expect(headers.get("allow") == "POST", "GET /api/signup: Allow: POST")
  status, headers, _ = client.raw("POST", "/api/unknown", b"{}", {"Content-Type": "application/json"})
  rejected("POST /api/unknown", status, (headers,), 404, count())

  # Serve only the page files
  for path, content_type in (("/", "text/html"), ("/index.html", "text/html"), ("/styles.css", "text/css"),
                             ("/script.js", "text/javascript"), ("/script.js?v=1", "text/javascript")):
    status, headers, body = client.raw("GET", path)
    expect(status == 200 and headers.get("content-type", "").startswith(content_type) and body,
           f"GET {path}: 200 {content_type}")
  status, headers, body = client.raw("HEAD", "/")
  expect(status == 200 and body == b"" and int(headers.get("content-length", 0)) > 0, "HEAD /: headers only")
  status, headers, _ = client.raw("POST", "/", b"{}", {"Content-Type": "application/json"})
  expect(status == 405 and headers.get("allow") == "GET, HEAD", "POST /: 405 with Allow: GET, HEAD")
  for path in ("/server/data/signups.sqlite3", "/docs/requirements.md", "/.git/config", "/../AGENTS.md",
               "/%2e%2e/AGENTS.md", "/server/app.py", "/index.html/"):
    status, headers, _ = client.raw("GET", path)
    expect(status == 404 and headers.get("content-type") == "application/json; charset=utf-8",
           f"GET {path}: JSON 404")


def main():
  if not app.exists():
    print(f"FAIL  {app} does not exist")
    return 1
  started = time.monotonic()
  quote = load_quote()
  with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "data" / "signups.sqlite3"
    proc = None
    log = ""
    try:
      proc, port = start_server(db_path)
      run(Client(port), db_path, quote)
    except Exception as error:
      expect(False, f"test run crashed: {type(error).__name__}: {error}")
    finally:
      if proc:
        proc.terminate()
        try:
          _, log = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
          proc.kill()
          _, log = proc.communicate()
    if db_path.exists():
      expect(stat.S_IMODE(db_path.parent.stat().st_mode) == 0o700, "data folder is created with mode 0700")
      expect(stat.S_IMODE(db_path.stat().st_mode) == 0o600, "database file has mode 0600")
    expect("POST /api/signup 201" in log, "log has «POST /api/signup 201»")
    expect("Анна" not in log and "anna@example.ru" not in log and "v=1" not in log,
           "log has no name, email or query string")
    expect("Traceback" not in log, "log has no traceback")
  elapsed = time.monotonic() - started
  expect(elapsed < 10, f"backend test finishes in under 10 s ({elapsed:.1f} s)")

  for ok, label in results:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
  passed = sum(ok for ok, _ in results)
  print(f"{passed}/{len(results)} backend checks passed")
  return 0 if passed == len(results) else 1


if __name__ == "__main__":
  sys.exit(main())
