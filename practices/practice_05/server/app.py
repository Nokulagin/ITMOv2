"""Olympiad Start local backend (Feature C): serves the page and accepts sign-ups (standard library only).

POST /api/signup validates a sign-up, prices it with the olympiad-pricing contract (docs/requirements.md)
and stores it in SQLite. Only the page files are served; everything else is 404.

Run: python3 server/app.py [--port 8000] [--db server/data/signups.sqlite3]
"""

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRICING_MODULE = ROOT / "mcp" / "olympiad_pricing" / "server.py"
DEFAULT_DB = ROOT / "server" / "data" / "signups.sqlite3"
HOST = "127.0.0.1"
MAX_BODY_BYTES = 10240

# Exact paths only: a request path is never joined onto the filesystem.
STATIC_FILES = {
  "/": ("index.html", "text/html; charset=utf-8"),
  "/index.html": ("index.html", "text/html; charset=utf-8"),
  "/styles.css": ("styles.css", "text/css; charset=utf-8"),
  "/script.js": ("script.js", "text/javascript; charset=utf-8"),
}

FIELDS = ("program", "grade", "months", "parent_name", "email", "consent")
MESSAGES = {
  "program": "Выберите программу.",
  "grade": "Выберите класс ребёнка.",
  "months": "Выберите срок обучения.",
  "parent_name": "Укажите имя родителя.",
  "parent_name_length": "Имя — не длиннее 100 символов.",
  "email": "Укажите email родителя.",
  "email_format": "Проверьте email: например, name@example.ru.",
  "email_length": "Email — не длиннее 254 символов.",
  "consent": "Нужно согласие на обработку данных.",
}
NAME_MAX = 100
EMAIL_MAX = 254
# Same pattern as script.js, with whitespace spelled out so Python and JS agree.
EMAIL_PATTERN = re.compile(r"^[^ \t\r\n\f\v@]+@[^ \t\r\n\f\v@]+\.[^ \t\r\n\f\v@]+$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS signups (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  program TEXT NOT NULL,
  grade INTEGER NOT NULL,
  months INTEGER NOT NULL,
  parent_name TEXT NOT NULL,
  email TEXT NOT NULL,
  monthly_rub INTEGER NOT NULL,
  discount_percent INTEGER NOT NULL,
  discount_rub INTEGER NOT NULL,
  total_rub INTEGER NOT NULL
)
"""


def load_pricing():
  """Import the MCP server module by path: one pricing implementation for the agent tool and the API."""
  spec = importlib.util.spec_from_file_location("olympiad_pricing_server", PRICING_MODULE)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module, module.load_contract()


def is_int(value):
  # bool is a subclass of int in Python; JSON true must not pass as 1.
  return isinstance(value, int) and not isinstance(value, bool)


def validate(data, programs, discounts):
  """Return (errors in field order, suggested program id or None, cleaned values)."""
  errors = {}
  grades = sorted({grade for program in programs.values() for grade in program["grades"]})

  program = data.get("program")
  if not isinstance(program, str) or program not in programs:
    errors["program"] = MESSAGES["program"]

  grade = data.get("grade")
  if not is_int(grade) or grade not in grades:
    errors["grade"] = MESSAGES["grade"]

  months = data.get("months")
  if not is_int(months) or months not in discounts:
    errors["months"] = MESSAGES["months"]

  name = data.get("parent_name")
  name = name.strip() if isinstance(name, str) else ""
  if not name or CONTROL_CHARS.search(name):
    errors["parent_name"] = MESSAGES["parent_name"]
  elif len(name) > NAME_MAX:
    errors["parent_name"] = MESSAGES["parent_name_length"]

  email = data.get("email")
  email = email.strip() if isinstance(email, str) else ""
  if not email:
    errors["email"] = MESSAGES["email"]
  elif len(email) > EMAIL_MAX:
    errors["email"] = MESSAGES["email_length"]
  elif not EMAIL_PATTERN.match(email):
    errors["email"] = MESSAGES["email_format"]

  if data.get("consent") is not True:
    errors["consent"] = MESSAGES["consent"]

  suggested = None
  if "program" not in errors and "grade" not in errors and grade not in programs[program]["grades"]:
    suggested = next(key for key, item in programs.items() if grade in item["grades"])
    errors["program"] = f"Для {grade} класса подходит «{programs[suggested]['name']}»."

  ordered = {field: errors[field] for field in FIELDS if field in errors}
  clean = {"program": program, "grade": grade, "months": months, "parent_name": name, "email": email}
  return ordered, suggested, clean


def init_db(path):
  if not path.parent.exists():
    path.parent.mkdir(mode=0o700, parents=True)
  if not path.exists():
    os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
  os.chmod(path, 0o600)
  with sqlite3.connect(path) as connection:
    connection.execute(SCHEMA)
  connection.close()


def store(path, clean, price):
  connection = sqlite3.connect(path)
  try:
    with connection:
      cursor = connection.execute(
        "INSERT INTO signups (created_at, program, grade, months, parent_name, email,"
        " monthly_rub, discount_percent, discount_rub, total_rub) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), clean["program"], clean["grade"],
         clean["months"], clean["parent_name"], clean["email"], price["monthly_rub"],
         price["discount_percent"], price["discount_rub"], price["total_rub"]))
    return cursor.lastrowid
  finally:
    connection.close()


class SignupServer(ThreadingHTTPServer):
  def handle_error(self, request, client_address):
    # Never print a traceback: it could carry request data.
    print(f"error: unhandled exception while serving {client_address[0]}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
  server_version = "OlympiadStart"
  sys_version = ""
  timeout = 10

  # Log only method, path without query, and status: no bodies, no query strings.
  def log_request(self, code="-", size="-"):
    path = urlsplit(getattr(self, "path", "") or "").path
    status = code.value if isinstance(code, HTTPStatus) else code
    print(f"{self.command or '-'} {path or '-'} {status}", file=sys.stderr, flush=True)

  def log_message(self, format, *args):
    pass

  def send_error(self, code, message=None, explain=None):
    # The base class writes HTML errors (e.g. malformed request line, unknown method): answer JSON instead.
    self.send_json(code, {"error": message or HTTPStatus(code).phrase})

  def send_json(self, status, body, headers=None):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(payload)))
    self.send_header("Cache-Control", "no-store")
    for name, value in (headers or {}).items():
      self.send_header(name, value)
    if status >= 400:
      # The request body may be unread (e.g. 413): do not reuse this connection.
      self.send_header("Connection", "close")
      self.close_connection = True
    self.end_headers()
    if self.command != "HEAD":
      self.wfile.write(payload)

  def send_static(self, path):
    name, content_type = STATIC_FILES[path]
    payload = (ROOT / name).read_bytes()
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(payload)))
    self.send_header("Cache-Control", "no-cache")
    self.end_headers()
    if self.command != "HEAD":
      self.wfile.write(payload)

  def same_origin(self):
    port = self.server.server_address[1]
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if self.headers.get("Host", "").lower() not in hosts:
      return False
    origin = self.headers.get("Origin")
    return origin is None or origin.lower() in {f"http://{host}" for host in hosts}

  def dispatch(self):
    try:
      if not self.same_origin():
        return self.send_json(403, {"error": "Forbidden"})
      path = urlsplit(self.path).path
      if path in STATIC_FILES:
        if self.command not in ("GET", "HEAD"):
          return self.send_json(405, {"error": "Method not allowed"}, {"Allow": "GET, HEAD"})
        return self.send_static(path)
      if path == "/api/signup":
        if self.command != "POST":
          return self.send_json(405, {"error": "Method not allowed"}, {"Allow": "POST"})
        return self.handle_signup()
      return self.send_json(404, {"error": "Not found"})
    except Exception as error:
      print(f"error: {type(error).__name__} on {self.command} {urlsplit(self.path).path}", file=sys.stderr, flush=True)
      try:
        self.send_json(500, {"error": "Internal error"})
      except OSError:
        pass

  do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = dispatch

  def handle_signup(self):
    content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
      return self.send_json(415, {"error": "Content-Type must be application/json"})
    length = self.headers.get("Content-Length")
    if length is None:
      return self.send_json(411, {"error": "Content-Length required"})
    if not length.isdigit():
      return self.send_json(400, {"error": "Invalid Content-Length"})
    if int(length) > MAX_BODY_BYTES:
      return self.send_json(413, {"error": f"Body larger than {MAX_BODY_BYTES} bytes"})
    try:
      data = json.loads(self.rfile.read(int(length)).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
      return self.send_json(400, {"error": "Body must be a JSON object"})
    if not isinstance(data, dict):
      return self.send_json(400, {"error": "Body must be a JSON object"})

    programs, discounts = self.server.contract
    errors, suggested, clean = validate(data, programs, discounts)
    if errors:
      body = {"errors": errors}
      if suggested:
        body["suggested_program"] = suggested
      return self.send_json(400, body)

    _, price = self.server.pricing.quote(
      {"program": clean["program"], "months": clean["months"], "grade": clean["grade"]}, self.server.contract)
    row_id = store(self.server.db_path, clean, price)
    self.send_json(201, {
      "id": row_id,
      "program": price["program"],
      "program_name": price["program_name"],
      "months": price["months"],
      "monthly_rub": price["monthly_rub"],
      "discount_percent": price["discount_percent"],
      "discount_rub": price["discount_rub"],
      "total_rub": price["total_rub"],
      "display": price["display"],
    })


def main(argv=None):
  parser = argparse.ArgumentParser(description="Olympiad Start local backend")
  parser.add_argument("--port", type=int, default=8000, help="port on 127.0.0.1 (0 = any free port)")
  parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file for stored sign-ups")
  args = parser.parse_args(argv)

  try:
    pricing, contract = load_pricing()
  except Exception as error:
    print(f"Cannot load prices from docs/requirements.md: {error}", file=sys.stderr)
    return 1

  db_path = args.db.resolve()
  init_db(db_path)
  server = SignupServer((HOST, args.port), Handler)
  server.pricing, server.contract, server.db_path = pricing, contract, db_path
  print(f"Serving on http://{HOST}:{server.server_address[1]}", flush=True)
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    pass
  finally:
    server.server_close()
  return 0


if __name__ == "__main__":
  sys.exit(main())
