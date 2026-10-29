# Proposal

## Why

Sign-ups are now stored by the local backend (Feature C, capability `signup-submission`), but nobody sees that
anything happens: the page looks the same with zero or a hundred requests. The owner wants the landing to show
how many people have already signed up, in total and per program, as social proof, without exposing any
personal data.

## What Changes

- New endpoint `GET /api/signups/stats` (and `HEAD`): answers `200` JSON
  `{"total": N, "by_program": {"start": a, "base": b, "intensive": c}}`, counted from the same SQLite file the
  server stores sign-ups in (`--db`). Empty or missing database → all zeros, not an error. Other methods → `405`
  with `Allow: GET, HEAD`; a foreign `Host` (or `Origin`) → `403`, same as `POST /api/signup`.
  `Cache-Control: no-store`. The answer has no names, emails, dates or ids.
- `index.html`: one empty, hidden line inside `#signup`, between the intro text and the form.
- `script.js`: on page load, one `GET /api/signups/stats` with a 5-second timeout. If the answer is a valid
  `200` with `total > 0`, the line shows «Уже записались: 12 — Старт: 5, Основа: 4, Интенсив: 3».
  Numbers use the page's grouping style (`26 460`), without «₽». In every other case (zero, error, timeout,
  invalid body, page opened without the server) the line stays hidden and no error is shown.
- The count is read once per page load; it does not change after the visitor's own successful sign-up.
- Rules: `docs/requirements.md` gains «Feature D — sign-up counter» (endpoint, line text, hidden states) and the
  Feature C «Not included» item becomes «viewing stored requests» with a note that aggregate counts are Feature D.
  `AGENTS.md` mentions the endpoint. `scripts/check_page.py`: the network check changes from «script.js calls
  only /api/signup» to «script.js calls only /api/signup and /api/signups/stats, one fetch each» (still no other
  transports). `scripts/test_backend.py` tests the new endpoint.
- New visible text: only the counter line pattern «Уже записались: N — Старт: a, Основа: b, Интенсив: c».
  Program names come from the existing select options.

Preserved (must keep working exactly as today):
- Feature A: all sections, exact counts, anchors and CTAs (the line is inside `#signup`, not a new section).
- Feature B: live price calculation, validation messages, the grade/program switch, «Выбрать» preselect,
  summary and focus, Tab order (the line is plain text, not focusable).
- Feature C: `POST /api/signup` contract and error texts, the static-file whitelist, same-origin checks,
  data privacy (`0700`/`0600`, log line «METHOD path STATUS», nothing personal in logs).
- The MCP server `olympiad-pricing` and its self-test stay unchanged.

Not in this change: a list or view of individual sign-ups, names or emails anywhere on the page, an admin page,
authentication, live or periodic refresh of the counter, caching, charts, a separate page or section,
deduplication of sign-ups before counting.

## Capabilities

### New Capabilities
- `signup-stats`: the public, aggregate-only sign-up counter: the read-only stats endpoint and the counter line
  on the page, including when the line is hidden. Kept separate from `signup-submission` because it has a
  different consumer (any visitor, read-only) and its own privacy boundary (counts only), and it can grow
  (for example, a per-card counter) without touching the submission contract.

### Modified Capabilities
None. `signup-submission` requirements stay as they are: the new path is an API path, not a page file, and the
submission contract does not change (see design.md, Open Questions).

## Impact

- Code: `server/app.py` (route, aggregate query), `script.js` (one fetch on load, render), `index.html` (one hidden
  line in `#signup`), `styles.css` (one BEM element `signup__stats` with existing tokens).
- Rules and checks: `docs/requirements.md`, `AGENTS.md`, `scripts/check_page.py`, `scripts/test_backend.py`.
- API: new `GET`/`HEAD /api/signups/stats`; existing endpoints unchanged.
- Dependencies: none (Python standard library, vanilla JavaScript).
- Data: read-only access to the existing `signups` table; no schema change, no new files.
