# Spec Delta

## Purpose

Shows visitors how many people have already signed up, in total and per program, using aggregate counts only,
so the landing gives social proof without exposing any stored personal data.

## ADDED Requirements

### Requirement: Stats endpoint returns aggregate counts
The server SHALL answer `GET /api/signups/stats` (query string ignored) with `200` JSON exactly
`{"total": N, "by_program": {"start": a, "base": b, "intensive": c}}`, counted from the stored sign-ups in the
database the server was started with. All values are non-negative integers and `total` equals `a + b + c`.
`HEAD` gets the same status and headers without a body.

#### Scenario: Counts after three sign-ups
- **WHEN** three valid sign-ups were stored (Старт, Старт, Основа) and the client sends `GET /api/signups/stats`
- **THEN** the response is `200` with body `{"total": 3, "by_program": {"start": 2, "base": 1, "intensive": 0}}`

#### Scenario: Empty database
- **WHEN** no sign-up has been stored yet
- **THEN** the response is `200` with body `{"total": 0, "by_program": {"start": 0, "base": 0, "intensive": 0}}`

#### Scenario: Database file is gone
- **WHEN** the database file was deleted while the server runs and the client requests the stats
- **THEN** the response is `200` with all counts `0`, and no new database file is created by this request

#### Scenario: HEAD request
- **WHEN** the client sends `HEAD /api/signups/stats`
- **THEN** the response is `200` with `Content-Type: application/json; charset=utf-8` and an empty body

### Requirement: Stats never expose personal data
The stats response MUST contain only the keys `total` and `by_program`, and `by_program` only `start`, `base`,
`intensive`: no names, emails, dates, ids or prices. It SHALL carry `Cache-Control: no-store`. The server log line
for it is `GET /api/signups/stats 200` with no query string.

#### Scenario: Only counts in the answer
- **WHEN** a sign-up from «Анна», anna@example.ru was stored and the client requests the stats
- **THEN** the response body has exactly the keys above, contains neither «Анна» nor «anna@example.ru», and has `Cache-Control: no-store`

#### Scenario: Log after a stats request
- **WHEN** the client requests `/api/signups/stats?x=1`
- **THEN** the server output contains `GET /api/signups/stats 200` and does not contain `x=1`

### Requirement: Stats endpoint accepts only same-origin reads
The stats endpoint SHALL apply the same `Host` and `Origin` check as `POST /api/signup` and answer `403` JSON when
it fails. Any method other than `GET` or `HEAD` MUST get a JSON `405` with header `Allow: GET, HEAD`. Every error
is JSON with `Content-Type: application/json; charset=utf-8`.

#### Scenario: Foreign host
- **WHEN** the client sends `GET /api/signups/stats` with `Host: evil.example`
- **THEN** the response is a JSON `403`

#### Scenario: Wrong method
- **WHEN** the client sends `POST /api/signups/stats` or `DELETE /api/signups/stats`
- **THEN** the response is a JSON `405` with header `Allow: GET, HEAD`, and no sign-up is stored or removed

### Requirement: Page shows the counter line
`#signup` SHALL contain one line between the intro text and the form, hidden until data arrives. On page load
the page sends one `GET /api/signups/stats`. On a valid `200` with `total` greater than `0` the line shows
«Уже записались: N — Старт: a, Основа: b, Интенсив: c» with numbers in the page's number style.

#### Scenario: Counter after three sign-ups
- **WHEN** the stats answer is `{"total": 3, "by_program": {"start": 2, "base": 1, "intensive": 0}}`
- **THEN** the line is visible and reads «Уже записались: 3 — Старт: 2, Основа: 1, Интенсив: 0»

#### Scenario: Large numbers
- **WHEN** the stats answer has `total` `12345` (`start` 12000, `base` 300, `intensive` 45)
- **THEN** the line reads «Уже записались: 12 345 — Старт: 12 000, Основа: 300, Интенсив: 45», grouped like the prices but without «₽»

#### Scenario: Counter is not a control
- **WHEN** a keyboard user tabs through `#signup`
- **THEN** the counter line is not focusable and the Tab order is the same as before this change

### Requirement: Counter stays hidden when there is nothing reliable to show
The line MUST stay hidden, with no error message and no script error, when `total` is `0`, the response is not
`200`, the body is not the expected shape, there is no answer within 5 seconds, or the page is opened without the
server. The sign-up form, the price calculator and sending a sign-up MUST work as before in all these cases.

#### Scenario: Nobody signed up yet
- **WHEN** the stats answer has `total` `0`
- **THEN** the counter line stays hidden

#### Scenario: Server not available
- **WHEN** the page is opened with `python3 -m http.server` or from `file://`
- **THEN** the counter line stays hidden, there is no script error, and the calculator and client validation work as before

#### Scenario: Server answers an error or garbage
- **WHEN** the stats request answers `500`, or `200` with a body missing `by_program`, or with a negative or non-integer count
- **THEN** the counter line stays hidden

#### Scenario: No answer in time
- **WHEN** the stats request does not answer within 5 seconds
- **THEN** the request is aborted and the counter line stays hidden

### Requirement: Counter is read once per page load
The page SHALL request the stats exactly once per page load and MUST NOT request them again after a sign-up;
the visible numbers change only on the next page load.

#### Scenario: After a successful sign-up
- **WHEN** a parent submits a valid sign-up and the server answers `201`
- **THEN** the page has sent exactly one stats request in total and the counter line keeps its earlier text or stays hidden
