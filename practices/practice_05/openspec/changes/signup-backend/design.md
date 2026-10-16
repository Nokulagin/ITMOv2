# Design

## Context

- The page is static: `index.html`, `styles.css`, `script.js`. `script.js` validates the form, prices it with
  `data-price` + `DISCOUNTS`, cancels submit and shows a summary. Nothing is sent.
- Pricing already exists in Python: `mcp/olympiad_pricing/server.py` has `load_contract()` (parses programs,
  grades, prices and discounts from `docs/requirements.md`) and `quote()` (price + grade/program check).
  It is stdlib-only, builds its paths from `__file__` and guards `main()` behind `if __name__ == "__main__"`,
  so it can be imported.
- The runner (`scripts/check_page.py:207`) enforces «form has no action» and (`:273-274`) «script.js sends no
  network requests». A `PostToolUse` hook runs `scripts/check.sh` after every edit with a 50 s timeout and blocks
  on FAIL, so task order must keep the runner green after each edit.
- In the form the duration radios are named `duration` and have no error element; the API field is `months`.
- The submit button sits inside `.signup-price`, which is `aria-live="polite"`.
- See proposal.md for motivation and scope; specs/signup-submission/spec.md for the exact behavior and texts.

## Goals / Non-Goals

**Goals:**
- One command starts page + API locally: `python3 server/app.py` → `http://127.0.0.1:8000`.
- One source of truth for prices: the server reuses the MCP pricing code, which reads `docs/requirements.md`.
- Backend behavior covered by an automated test in `scripts/check.sh` that fits the hook's time budget.

**Non-Goals:**
- Concurrency or load beyond one local user; schema migrations; backups.
- Deduplicating repeated requests (a retry after a lost response can store a second row).
- Retention policy: stored requests are deleted by hand by removing `server/data/`.
- Changing the MCP server or its self-test.
- Moving the live calculator to the server.

## Decisions

1. **Python stdlib `http.server.ThreadingHTTPServer` + `sqlite3`.**
   Matches the MCP server and the «no dependencies» rule. Alternatives: Flask/FastAPI (need pip, violate rules),
   Node `http` (second backend language next to existing Python tooling), JSON-lines file (no atomic writes,
   harder to query later). SQLite is in stdlib and gives atomic inserts.

2. **Own request handler with a whitelist, not `SimpleHTTPRequestHandler`.**
   `SimpleHTTPRequestHandler` serves the whole directory, including `server/data/*.sqlite3` and `.git`.
   The handler strips the query, compares the raw path to exactly `/`, `/index.html`, `/styles.css`, `/script.js`
   and maps them to fixed files and content types; it never joins a request path onto the filesystem, so
   traversal (`/../`, `%2e%2e`) cannot reach anything. Binds to `127.0.0.1`.

3. **Same-origin guard against cross-site posts and DNS rebinding.**
   Binding to loopback does not stop another site in the same browser from posting to `127.0.0.1:8000`.
   A cross-site «simple» request cannot send `Content-Type: application/json` without a CORS preflight, which
   the server never approves, so requiring JSON (`415` otherwise) blocks it. `Host` must be `127.0.0.1:<port>`
   or `localhost:<port>` (blocks DNS rebinding) and `Origin`, when present, must be `http://` + an allowed host
   (`403`). The page's own `fetch` sends a matching `Origin`, so it passes. Alternative: CSRF token — needs
   server-rendered HTML, which this static page does not have.

4. **Reuse pricing by importing the MCP module by file path** (`importlib.util.spec_from_file_location`).
   No change to `mcp/`, so its self-test stays as is. Only `scripts/test_backend.py` exercises this import path;
   the MCP self-test runs `server.py` as a subprocess and does not. Alternative: extract a shared `pricing.py` —
   cleaner, but touches the MCP server for no behavior gain; can be done later. `quote()` is called only after
   the server's own validation passed, so its `ToolError` texts are never shown to users.

5. **Server validation: field order, strict types, fixed texts.**
   Order `program`, `grade`, `months`, `parent_name`, `email`, `consent`; all invalid fields are reported.
   Messages: the page's six existing texts plus four new ones that Feature C adds to `docs/requirements.md`
   («Выберите срок обучения.», «Имя — не длиннее 100 символов.», «Email — не длиннее 254 символов.» and the
   page-level «Не удалось отправить заявку. Попробуйте ещё раз.»). Types are checked before values; Python's
   `bool` is a subclass of `int`, so `grade`/`months` reject `bool` explicitly; `consent` must be `is True`.
   The email pattern spells whitespace as `[ \t\r\n\f\v]` so JS and Python agree. The mismatch check runs only
   when `program` and `grade` are both valid; its message and `suggested_program` come from the contract.
   The page adds `maxlength="100"` / `maxlength="254"` to the name and email inputs so the new length texts are
   reachable only by non-page clients.

6. **Request parsing order and error responses.**
   Host/Origin (`403`) → method and path (`404`/`405`) → `Content-Type` (`415`) → `Content-Length` missing (`411`)
   or > 10240 (`413`, body not read) → read exactly that many bytes, UTF-8 JSON object (`400`) → fields (`400`) →
   price → insert → `201`. Every non-`2xx` goes through one JSON helper (never `send_error`, which writes HTML);
   unexpected exceptions become `500 {"error": "Internal error"}` without a traceback. `HEAD` on a page file
   returns headers only.

7. **Storage schema** (`server/data/signups.sqlite3`, git-ignored, folder `0700`, file `0600`, created on start):
   `signups(id INTEGER PRIMARY KEY, created_at TEXT UTC ISO, program TEXT, grade INTEGER, months INTEGER,
   parent_name TEXT, email TEXT, monthly_rub INTEGER, discount_percent INTEGER, discount_rub INTEGER,
   total_rub INTEGER)`. Consent is not a column: a row exists only if consent was `true`; `created_at` is the
   consent time. Values are stored trimmed. One connection per request, parameterized queries only.

8. **Logging.** Override `log_message` to print `METHOD path-without-query STATUS` only.

9. **Page flow** in `script.js`:
   ```
   submit -> pending? --yes--> ignore
                | no
                v
          client validate --fail--> field errors (unchanged), no request
                | ok
                v
          pending, aria-disabled, clear general error,
          fetch POST /api/signup (JSON, AbortController 10 s)
                |
     +----------+------------------+-------------------------------+
     | 201                         | 400 with errors               | network error / timeout / other
     v                             v                               v
   summary from response       known keys -> field errors,       general error in
   (program_name, months,      first in form order focused;      .signup-form__status,
   display.total), focus       suggested_program ->              focus stays on button
   on heading                  showMismatch(grade);
                               other keys -> general error
                |                  |                               |
                +------------------+------- pending off, aria-disabled removed
   ```
   - The general error is `<p class="signup-form__status" id="signup-status" role="alert">`, placed after
     `.signup-price` inside the form, so it is not nested in the price live region.
   - `aria-disabled` instead of `disabled`: `disabled` drops focus from the focused button to `body`.
   - Field errors from the server reuse `setError()` and `showMismatch()`; `attempted` stays true, so the next
     change re-runs client validation as today.
   - The summary is built from the response, not from the form, so edits during the request cannot change it.
   - The comment at `script.js:2` («No network requests») is updated.

10. **Runner changes, not weakening.** Keep «form has no action». Replace «script.js sends no network requests»
    with «script.js calls only `/api/signup`»: exactly one `fetch(` and its first argument is the literal
    `'/api/signup'`; `XMLHttpRequest`, `sendBeacon`, `WebSocket`, `EventSource`, `new Request(`, `import(` and
    `.submit(` stay forbidden. This lands before the `fetch` is added to `script.js`, so the hook stays green.

11. **Backend test.** `scripts/test_backend.py` starts `server/app.py --port 0 --db <tmp>`; the server prints
    `Serving on http://127.0.0.1:<port>` and the test reads the real port (no free-port race). Socket timeouts
    5 s, server killed in `finally`, whole run under 10 s so `check.sh` stays inside the hook's 50 s. It covers
    every server-side scenario in the spec; page scenarios are checked in Playwright. `check.sh` runs it only if
    `server/app.py` exists, like the MCP self-test.

## Risks / Trade-offs

- [Server and page price formulas can drift (JS `Math.round` vs Python `//`)] → today every price × discount is
  a whole number; the backend test compares the server against `quote()` for all 9 combinations, and the
  summary shows the server's total.
- [Personal data on disk] → only in `server/data/` (`0700`/`0600`), git-ignored, never logged, never served.
- [Page opened via `file://` can no longer complete a sign-up] → explicit general error instead of a fake
  success; `AGENTS.md` «Run locally» points to `python3 server/app.py`.
- [The 400 path cannot be reached from a valid page form] → Playwright stubs `/api/signup` with `page.route`.
- [Port 8000 is also used by `python3 -m http.server` in docs] → port configurable via `--port`; docs updated.
- [Importing the MCP file by path couples the two] → covered by `test_backend.py`; if it breaks, extract
  `pricing.py`.
- [Duplicate rows on retry after a lost response] → accepted (Non-Goal); visible to the owner in the DB.

## Migration Plan

Local only. Start: `python3 server/app.py`. Rollback: revert the commit; deleting `server/data/` removes stored
requests. No existing data to migrate.
