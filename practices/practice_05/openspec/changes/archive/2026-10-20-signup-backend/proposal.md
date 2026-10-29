# Proposal

## Why

The sign-up form (Feature B) validates and prices a request, then shows a summary, but the request is lost:
nothing leaves the browser. The owner wants a local backend that accepts a sign-up, stores it and prices it
on the server, so a submitted request actually exists somewhere and its price cannot be set by the client.

## What Changes

- New local backend in Python standard library only (no pip packages, no frameworks), started with one command.
- New endpoint `POST /api/signup`: validates the request, computes the price on the server from
  `docs/requirements.md`, stores the request and returns the stored result. Accepts only same-origin JSON
  requests (protection against other sites posting to the local server).
- The same server serves only the page files (`index.html`, `styles.css`, `script.js`), so page and API share
  one origin and nothing else in the project is reachable over HTTP.
- `script.js`: after the existing client-side validation passes, the form sends one request to `/api/signup`.
  The confirmation summary is shown only after the server accepted the request and is built from its answer.
  Server field errors are shown next to the fields (including the grade/program switch button); if the server
  cannot be reached or does not answer in 10 s, the form stays filled in and a general error is shown.
- **BREAKING (product contract)**: `docs/requirements.md` says «Stack: vanilla HTML, CSS and JavaScript» and
  Feature B says «On valid submit: no network request». Product/Stack gains «local backend on the Python standard
  library (Feature C)», Feature B becomes «one request to `/api/signup` on the same origin», and a new
  «Feature C — sign-up backend» section lists the endpoint and every new text. Approved by the owner in explore.
- New visible text on the page: only «Не удалось отправить заявку. Попробуйте ещё раз.». New API-only error texts
  (not reachable from the page form): «Выберите срок обучения.», «Имя — не длиннее 100 символов.»,
  «Email — не длиннее 254 символов.». All are added to Feature C.
- Project rules updated to allow the backend: `AGENTS.md` (new `server/` folder, Python backend, how to run,
  Check section and pre-finish checklist), `.gitignore` (stored data). The runner check «script.js sends no
  network requests» is tightened to «script.js only calls `/api/signup`», not removed. A backend test is added
  to `scripts/check.sh`.

Preserved (must keep working exactly as today):
- All Feature A sections, counts, anchors and CTAs.
- Live price calculation in the browser, the «—» / «Выберите программу» state, 1 month default.
- Client-side validation, its Russian messages and the grade/program suggestion button.
- «Выбрать» buttons preselect the program; summary content and focus on its heading.
- The MCP server `olympiad-pricing` and its self-test stay unchanged.

Not in this change:
- Admin page, listing or exporting stored requests, editing or deleting them.
- Sending email or any other notification.
- Authentication, payments, rate limiting, captcha.
- Deployment, HTTPS, CORS, running on a public host.
- A price API for the live calculator (`GET /api/quote`): the calculator stays client-side.
- Deduplicating repeated requests; retention policy (stored data is deleted by hand).
- New visible content beyond the texts listed above.

## Capabilities

### New Capabilities
- `signup-submission`: accepting a sign-up request from the page, validating and pricing it on the server,
  storing it, and how the page reacts to success, field errors and an unreachable server.

### Modified Capabilities
None (no existing specs in `openspec/specs/`).

## Impact

- New: `server/app.py` (HTTP server + API), `server/data/` (SQLite file, git-ignored),
  `scripts/test_backend.py` (backend test run by `scripts/check.sh`).
- Changed: `script.js` (submit handler), `index.html` (general error element, `maxlength` on name and email),
  `styles.css` (its style),
  `scripts/check_page.py` (network check tightened), `scripts/check.sh` (runs backend test),
  `docs/requirements.md` (Feature B wording + Feature C), `AGENTS.md`, `.gitignore`.
- Reused, not changed: pricing logic `load_contract()` / `quote()` from `mcp/olympiad_pricing/server.py`.
- Runtime: Python 3 (already required by the runner and MCP). Local only, `127.0.0.1`.
- Personal data (parent's name and email) is stored on disk in the local SQLite file only.
