# Tasks

## 1. Contract and rules

- [ ] 1.1 Add «Feature D — sign-up counter» to `docs/requirements.md` (endpoint, line text «Уже записались: N — Старт: a, Основа: b, Интенсив: c», place in `#signup`, hidden states, read once per load) and change the Feature C «Not included» item to «viewing stored requests» with a note that aggregate counts are Feature D; verify `sh scripts/check.sh` still PASS
- [ ] 1.2 Mention `GET /api/signups/stats` in `AGENTS.md` (Files: `server/app.py` line; Run locally: the counter is hidden without the server); verify `sh scripts/check.sh` PASS

## 2. Backend endpoint

- [ ] 2.1 Add stats tests to `scripts/test_backend.py` first (all zeros before any sign-up; counts equal a `GROUP BY` on the database after the existing sign-ups; `HEAD` empty body; `POST`/`DELETE` → `405` with `Allow: GET, HEAD`; foreign `Host` → `403`; only allowed keys; no «Анна» / «anna@example.ru»; `Cache-Control: no-store`; log has `GET /api/signups/stats 200` and no `x=1`; deleted database → zeros and no new file); verify they FAIL against the current server
- [ ] 2.2 Implement the route and read-only count in `server/app.py` (design decisions 1–3); verify `python3 scripts/test_backend.py` passes all checks in under 10 s and `sh scripts/check.sh` PASS

## 3. Page counter

- [ ] 3.1 Tighten `scripts/check_page.py`: allow exactly one `fetch` to `/api/signup` and one to `/api/signups/stats`, nothing else (other transport checks unchanged); add a check that `#signup-stats` is inside `#signup`, before the form, and has `hidden`; verify both new checks FAIL on the current page
- [ ] 3.2 Add `<p class="signup__stats" id="signup-stats" hidden></p>` to `index.html` after `.signup__text`, and `.signup__stats` to `styles.css` with existing tokens (BEM, rem, no raw hex); verify the markup check from 3.1 passes
- [ ] 3.3 Add the stats block to `script.js` (design decision 5: one fetch on load, 5 s abort, shape check, `total > 0`, `textContent`, shared number grouping with `formatRub`); verify `sh scripts/check.sh` PASS including «script.js parses»

## 4. Browser verification (Playwright, server with a scratchpad `--db`, test data «Анна», anna@example.ru)

- [ ] 4.1 Empty database: line hidden; then 3 sign-ups (Старт, Старт, Основа) and reload: line reads «Уже записались: 3 — Старт: 2, Основа: 1, Интенсив: 0»; after one more sign-up the line does not change until reload and exactly one stats request was sent; no console errors
- [ ] 4.2 Failure cases via `page.route`: `500`, `200` without `by_program`, a negative count, no answer (line hidden after ~5 s); and the page served by `python3 -m http.server`: line hidden, no script error, calculator and client validation still work
- [ ] 4.3 Large numbers via `page.route` (`12345` = 12000 + 300 + 45): line reads «Уже записались: 12 345 — Старт: 12 000, Основа: 300, Интенсив: 45»; at 360 / 768 / 1280 px no horizontal scroll; Tab order in `#signup` unchanged (line not focusable)
- [ ] 4.4 Record results in `docs/evidence/stats-browser-check.md` with screenshots; verify `sh scripts/check.sh` PASS and `openspec validate signup-stats --strict` valid

## Workflow follow-up

- Independent review by a separate agent, then human acceptance.
- Sync specs and archive the change after acceptance.
