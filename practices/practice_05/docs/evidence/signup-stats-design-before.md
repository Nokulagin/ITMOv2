# Design

## Context

See proposal.md (Why) and specs/signup-stats/spec.md (behavior). Current state that shapes the approach:

- `server/app.py` routes every method through one `dispatch`: Host/Origin check (`same_origin`) first, then exact
  path matching (static whitelist, `/api/signup`), else JSON `404`. `send_json` already sets
  `Content-Type: application/json; charset=utf-8`, `Cache-Control: no-store`, skips the body for `HEAD`, and closes
  the connection on errors. `log_request` prints only «METHOD path STATUS».
- `init_db` creates the data folder (`0700`) and file (`0600`) at start-up. `sqlite3.connect(path)` on a missing
  file would silently create a new one with default permissions.
- `script.js` is one IIFE that returns early if `#signup-form` is missing; `formatRub` groups numbers ≥ 10 000.
  Program names live in the `<select>` options (`Старт (5–6 класс)` → `Старт`).
- `scripts/check_page.py` allows exactly one `fetch`, to `/api/signup`. `scripts/test_backend.py` starts one server
  on a free port with a temporary database and must finish in under 10 s.

## Goals / Non-Goals

**Goals:**
- Read-only aggregate endpoint that cannot leak personal data or change the database or its permissions.
- A counter that never blocks or breaks the form: it is decoration, so every failure is silent.
- Reuse the existing request pipeline (origin check, JSON errors, logging) instead of a parallel one.

**Non-Goals:**
- Performance work (an index, caching, a counter table): the table is small and local.
- Changing how sign-ups are stored or validated.

## Decisions

1. **Route inside the existing `dispatch`, after the origin check.** The stats path is matched exactly
   (`/api/signups/stats`, query ignored), next to `/api/signup`. `GET`/`HEAD` → handler; other methods → `405`
   with `Allow: GET, HEAD`. Order of checks for a request: Host/Origin (`403`) → path (`404` if unknown) →
   method (`405`) → read counts → `200`. Alternative: a separate prefix router for `/api/*` — rejected, two paths
   do not need it and one pipeline keeps the 403/404/JSON behavior identical.

2. **Count with one `SELECT program, COUNT(*) … GROUP BY program`**, then fill a dict with all three program ids
   from the pricing contract (`self.server.contract`) defaulting to `0`; `total` is the sum. Programs not in the
   contract are ignored (cannot happen, validation rejects them). Alternative: three `COUNT` queries — rejected,
   one query is simpler and consistent within one read.

3. **Open the database read-only: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.** If the file or the table
   is missing (`sqlite3.OperationalError`), answer zeros. This guarantees the stats request never creates a file
   with wrong permissions and never writes. Alternative: reuse `init_db` — rejected, a read must not recreate data
   the owner deleted by hand. Other database errors fall through to the existing `500` handler (logged without
   request data).

4. **Markup: one `<p class="signup__stats" id="signup-stats" hidden></p>` in `index.html`, right after
   `.signup__text` and before `<form>`.** It is outside the form, so the summary that replaces the form after `201`
   leaves the line as it was. Empty and hidden in the HTML, so with JavaScript off or no server nothing shows and
   the static page contract does not change. Plain `<p>`: not focusable, no `aria-live` (the text appears once on
   load, before the visitor reaches the section). Style: muted text with existing tokens, like `.signup__text`.

5. **Script: a separate small block in `script.js`**, run on load, not inside the form logic, so it cannot affect
   validation or the pending guard. One `fetch('/api/signups/stats')` with an `AbortController` and a 5 s timer.
   Render only if `response.status === 200` and the body passes a shape check: `total` and the three counts are
   non-negative integers and `total > 0`. Any exception (network, abort, JSON parse) is caught and leaves the line
   hidden. Text is built with `textContent`, program names from the `<select>` option text before « (». Numbers use
   a shared helper split out of `formatRub` (grouping only), so counts and prices group the same way.
   Alternative: reuse the 10 s timeout of the sign-up — rejected, a counter that appears after 10 s is noise.

6. **Runner change is a tightening, not a loosening.** `check_page.py` accepts exactly two `fetch` uses: one to
   `/api/signup` and one to `/api/signups/stats`, each at most once; every other transport check stays. A new
   check verifies `#signup-stats` exists inside `#signup`, before the form, and has `hidden`.

7. **Backend tests in the existing run**, against the same temporary database: stats before any sign-up (all
   zeros), after the existing sign-ups (compare with `GROUP BY` on the database), `HEAD`, `405` for `POST` and
   `DELETE` with `Allow`, `403` for a foreign `Host`, only allowed keys, no personal data, `Cache-Control`,
   query string not logged, and the deleted-database case last (remove the file, expect zeros and no new file).

## Risks / Trade-offs

- [Low counts on a fresh install look discouraging] → the line is hidden at `0`; small non-zero numbers are shown
  as they are, the owner accepted this.
- [Counts include test or duplicate sign-ups] → deduplication is out of scope; the owner cleans the database by
  hand, as already stated in Feature C.
- [Aggregates could hint at a person when counts are tiny] → only per-program totals, no dates or grades; the
  server is local only.
- [The counter is stale after the visitor's own sign-up] → accepted decision; it updates on the next load.
- [Deleting the database while the server runs makes the next sign-up fail] → existing Feature C behavior, not
  changed here; stats keep answering zeros.

## Migration Plan

No data migration: the `signups` table is read as is. Rollback is reverting the commit; stored data is untouched.

## Open Questions

- The `signup-submission` requirement «Serve only the page files» says every other path gets `404`. It was written
  for non-API paths (`/api/signup` already exists alongside it), so it is not modified here. If a reviewer reads it
  as covering API paths, add a MODIFIED delta that names `/api/signup` and `/api/signups/stats` as the API
  exceptions; behavior and tasks stay the same.
