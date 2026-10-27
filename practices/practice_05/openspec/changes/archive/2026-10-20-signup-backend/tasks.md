# Tasks

The `PostToolUse` hook runs `sh scripts/check.sh` after every edit and blocks on FAIL. Keep this order:
the runner must stay green after each task (in particular 3.1 lands before the `fetch` in 3.3).

## 1. Contract and project rules

- [x] 1.1 In `docs/requirements.md`: Product/Stack adds «local backend on the Python standard library (Feature C)»; Feature B «On valid submit: no network request» becomes «one request to `/api/signup` on the same origin»; add «Feature C — sign-up backend» (endpoint, server pricing, same-origin JSON only, storage, the general error text and the three API-only texts from the spec, out-of-scope list); verify `sh scripts/check.sh` PASS (MCP self-test still parses the contract)
- [x] 1.2 Update `AGENTS.md`: Files (`server/app.py`, `server/data/`, `scripts/test_backend.py`), allowed folders (`server/`), Stack rules (Python stdlib backend), «Run locally» and «Check» → `python3 server/app.py` at http://127.0.0.1:8000, «Before finishing» checklist; add `server/data/` to `.gitignore`; verify `git check-ignore server/data/x.sqlite3` succeeds

## 2. Backend

- [x] 2.1 Create `server/app.py`: `ThreadingHTTPServer` on `127.0.0.1`, `--port` (default 8000, `0` = any, prints `Serving on http://127.0.0.1:<port>`) and `--db` options, whitelist static handler for GET/HEAD with query ignored, JSON error helper for every non-2xx (no `send_error`), 500 without traceback, log line `METHOD path STATUS`; verify manually that `/` loads and `/docs/requirements.md`, `/.git/config`, `/%2e%2e/AGENTS.md` return JSON 404
- [x] 2.2 Load pricing by importing `mcp/olympiad_pricing/server.py` by path (`load_contract`, `quote`); verify the server prints a clear error and exits non-zero if the contract cannot be parsed (run with a temporarily unreadable path in a scratch copy, not the real file)
- [x] 2.3 Implement the request guard and parsing for `POST /api/signup` in the design's order: Host/Origin (403), method/path (405 with `Allow`, 404), Content-Type (415), Content-Length (411, 413 > 10240 without reading), JSON object (400); verify with `scripts/test_backend.py` cases for each status
- [x] 2.4 Implement field validation exactly per the spec's field-error table (strict types, `bool` rejected, `consent is True`, trim, control characters, lengths, email pattern) and the mismatch error with `suggested_program`; verify with `scripts/test_backend.py`: every table row, the three-error scenario and the mismatch body
- [x] 2.5 Implement SQLite storage (folder `0700`, file `0600`, create table on start, parameterized insert of trimmed values and server-computed price only) and the `201` response; verify with `scripts/test_backend.py`: valid request stored once with the listed values, all 9 combinations equal `quote()`, fake price and unknown fields ignored, invalid and rejected requests store nothing, log has no name/email, file modes
- [x] 2.6 Finish `scripts/test_backend.py` (server via `--port 0` and temp DB, socket timeouts 5 s, server killed in `finally`, total under 10 s) covering every server-side spec scenario, and run it from `scripts/check.sh` only if `server/app.py` exists, like the MCP self-test; verify `sh scripts/check.sh` prints `RESULT: PASS` and `time sh scripts/check.sh` stays well under 50 s

## 3. Page

- [x] 3.1 Tighten `scripts/check_page.py`: replace «script.js sends no network requests» with «script.js calls only `/api/signup`» (exactly one `fetch(` with literal `'/api/signup'`; a variable URL, other targets, `XMLHttpRequest`, `sendBeacon`, `WebSocket`, `EventSource`, `new Request(`, `import(`, `.submit(` fail); keep «form has no action»; verify it passes on the current `script.js` and fails on scratch copies with `fetch('https://example.com')`, `fetch(url)` and `new EventSource('/x')`
- [x] 3.2 In `index.html` add `<p class="signup-form__status" id="signup-status" role="alert"></p>` after `.signup-price` (outside the `aria-live` region) and `maxlength="100"` / `maxlength="254"` on name and email; style it in `styles.css` with `:root` tokens and BEM; verify `sh scripts/check.sh` PASS
- [x] 3.3 Change the submit handler in `script.js` per design decision 9 (pending guard, `aria-disabled`, one JSON `fetch('/api/signup')` with `grade`/`months` as numbers, 10 s `AbortController`; 201 → summary from the response with heading focus; 400 → `setError`/`showMismatch`, focus first invalid in form order, unknown keys → general error; other/network/timeout → general error, focus stays on button) and update the comment at `script.js:2`; verify `sh scripts/check.sh` PASS

## 4. Browser verification

- [x] 4.1 With `python3 server/app.py` running, in Playwright: submit a valid form by mouse and by keyboard → summary «Старт», «6 месяцев», «26 460 ₽», focus on heading, one row in SQLite; pressing Enter twice sends one request (network log); no console errors
- [x] 4.2 In Playwright with `page.route('/api/signup')` stubs: 400 `errors.email` → text in `#signup-email-error`, `aria-invalid`, focus on email, button active; 400 mismatch with `suggested_program` → «Выбрать «Основу»» works and recalculates; 400 only `errors.months` → general error
- [x] 4.3 In Playwright: server stopped → general error announced, values kept, focus on the button, button active; stubbed hang → general error after 10 s; retry with `201` clears the error; client-invalid form sends no request
- [x] 4.4 Regression in Playwright at 360px, 768px and 1280px: no horizontal scroll, all Feature A anchors and «Выбрать» preselect work, live calculator and «—» state unchanged, Tab reaches every form control and the switch button with nothing skipped or trapped; save evidence in `docs/evidence/`

## Workflow follow-up

- Review the diff, then archive the change with `/opsx:archive` once the owner accepts it.
