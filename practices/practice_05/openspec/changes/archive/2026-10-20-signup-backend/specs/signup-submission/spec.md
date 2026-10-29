# Spec Delta

## Purpose

Lets a parent's sign-up request leave the page: a local server accepts it, validates and prices it from the
product requirements, stores it, and the page shows the stored result or explains why it was not stored.

## ADDED Requirements

### Requirement: Accept a valid sign-up
The server SHALL accept `POST /api/signup` with a JSON object `{program, grade, months, parent_name, email, consent}`.
A valid request MUST be stored once and answered with `201` and JSON
`{id, program, program_name, months, monthly_rub, discount_percent, discount_rub, total_rub, display}`,
where `display` has the same `monthly`, `discount`, `total` strings as the `quote` tool.

#### Scenario: Valid request is stored
- **WHEN** the client posts `{"program":"start","grade":5,"months":6,"parent_name":"Анна","email":"anna@example.ru","consent":true}`
- **THEN** the response is `201` with an integer `id`, `program` `start`, `program_name` «Старт», `months` 6, `monthly_rub` 4410, `discount_percent` 10, `discount_rub` 2940, `total_rub` 26460 and `display.total` «26 460 ₽» (non-breaking space)
- **AND** exactly one new stored request exists with program `start`, grade 5, months 6, parent_name «Анна», email «anna@example.ru», monthly_rub 4410, discount_percent 10, discount_rub 2940, total_rub 26460

#### Scenario: Every program and duration
- **WHEN** a valid request is posted for each of the 9 combinations of program and months 1, 3, 6 with a matching grade
- **THEN** `monthly_rub`, `discount_percent`, `discount_rub`, `total_rub` and `display` equal the `quote` tool result for the same program and months

#### Scenario: Stored text is trimmed
- **WHEN** a valid request has `parent_name` «  Анна  » and `email` « anna@example.ru »
- **THEN** the stored and returned values are «Анна» and «anna@example.ru»

### Requirement: Price and unknown fields come only from the server
The server MUST compute the price from `docs/requirements.md`. Any field other than the six request fields
MUST be ignored and MUST NOT be stored or echoed.

#### Scenario: Client sends a fake price
- **WHEN** a valid request also contains `"monthly_rub":1,"discount_percent":99,"discount_rub":1,"total_rub":1,"display":{"total":"1 ₽"},"admin":true`
- **THEN** the response and the stored request contain only server-computed prices and no `admin` field

### Requirement: Field validation matches the page
The server SHALL validate in field order `program`, `grade`, `months`, `parent_name`, `email`, `consent` and answer
an invalid request with `400` and `{"errors": {<field>: <message>}}` containing every invalid field. It MUST NOT
store an invalid request. Messages are exactly those in the field-error table below.

#### Scenario: Missing fields and no consent
- **WHEN** the client posts `{"program":"base","grade":7,"months":1,"parent_name":"","email":"x","consent":false}`
- **THEN** the response is `400` and `errors` has exactly three keys: `parent_name` «Укажите имя родителя.», `email` «Проверьте email: например, name@example.ru.», `consent` «Нужно согласие на обработку данных.»
- **AND** nothing is stored

#### Scenario: Field-error table
- **WHEN** a request contains one of these values, all other fields valid
- **THEN** the response is `400` with exactly this key and message, and nothing is stored:

  | Input | Key | Message |
  |---|---|---|
  | `program` missing, not a string, or not `start`/`base`/`intensive` | `program` | «Выберите программу.» |
  | `grade` missing, not a JSON integer (`"7"`, `7.0`, `true`), or outside 5–9 | `grade` | «Выберите класс ребёнка.» |
  | `months` missing, not a JSON integer, or not 1, 3, 6 | `months` | «Выберите срок обучения.» |
  | `parent_name` missing, not a string, empty or whitespace only after trim, or containing control characters (including line breaks) | `parent_name` | «Укажите имя родителя.» |
  | `parent_name` longer than 100 characters after trim | `parent_name` | «Имя — не длиннее 100 символов.» |
  | `email` missing, not a string, or empty after trim | `email` | «Укажите email родителя.» |
  | `email` not matching `^[^ \t\r\n\f\v@]+@[^ \t\r\n\f\v@]+\.[^ \t\r\n\f\v@]+$` | `email` | «Проверьте email: например, name@example.ru.» |
  | `email` longer than 254 characters after trim | `email` | «Email — не длиннее 254 символов.» |
  | `consent` anything other than JSON `true` (`"true"`, `1`, `false`, missing) | `consent` | «Нужно согласие на обработку данных.» |

#### Scenario: Grade does not match the program
- **WHEN** the client posts a request with `program` `start`, `grade` 7, other fields valid
- **THEN** the response is `400` with body `{"errors": {"program": "Для 7 класса подходит «Основа»."}, "suggested_program": "base"}`
- **AND** nothing is stored

### Requirement: Only same-origin JSON requests are accepted
The server SHALL answer a request whose `Content-Type` is not `application/json` (parameters such as `charset`
allowed) with `415`, and any request whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, or whose
`Origin`, when present, is not `http://` plus such a host, with `403`. Nothing MUST be stored.

#### Scenario: Cross-site form post
- **WHEN** a request to `/api/signup` has `Content-Type: text/plain` and a valid JSON body
- **THEN** the response is `415` and nothing is stored

#### Scenario: Foreign origin or host
- **WHEN** a valid JSON request has `Origin: http://evil.example`, or `Host: evil.example:8000`
- **THEN** the response is `403` and nothing is stored

### Requirement: Malformed requests are rejected as JSON
The server SHALL answer: no `Content-Length` with `411`; `Content-Length` over 10240 bytes with `413` before reading
the body; empty body, broken JSON or a non-object (`[]`, `null`) with `400`. These and all other error responses
(`403`, `404`, `405`, `415`, `500`) MUST be JSON `{"error": ...}` with `Content-Type: application/json; charset=utf-8`.
None of them MUST store anything or stop the server.

#### Scenario: Broken JSON
- **WHEN** the client posts `{not json` to `/api/signup`
- **THEN** the response is a JSON `400` and the next valid request still gets `201`

#### Scenario: Non-object JSON
- **WHEN** the client posts `[]` or `null`
- **THEN** the response is a JSON `400`

#### Scenario: Body too large
- **WHEN** the client posts with `Content-Length: 10241`
- **THEN** the response is a JSON `413` and nothing is stored

#### Scenario: Wrong method or unknown API path
- **WHEN** the client sends `GET /api/signup`, or `POST /api/unknown`
- **THEN** the response is a JSON `405` with header `Allow: POST`, or a JSON `404`

### Requirement: Serve only the page files
The server SHALL answer `GET` and `HEAD` for `/`, `/index.html`, `/styles.css`, `/script.js` (query string ignored)
and MUST answer `404` for every other path, so stored data, `docs/`, `.git` and server code are never served.
Other methods on these paths get `405` with `Allow: GET, HEAD`. It SHALL listen on `127.0.0.1` only.

#### Scenario: Page loads from the server
- **WHEN** a browser opens `http://127.0.0.1:8000/`
- **THEN** the page loads with its stylesheet and script and there are no console errors

#### Scenario: Query string on a page file
- **WHEN** the client requests `/script.js?v=1`
- **THEN** the response is `200` with the script

#### Scenario: Private files are not reachable
- **WHEN** the client requests `/server/data/signups.sqlite3`, `/docs/requirements.md`, `/.git/config`, `/../AGENTS.md` or `/%2e%2e/AGENTS.md`
- **THEN** the response is `404`

### Requirement: Stored personal data stays private
The server MUST NOT log request bodies, query strings or tracebacks with request data; the log line is method,
path without query, and status. The data folder SHALL be created with mode `0700` and the database file with `0600`.

#### Scenario: Log after a sign-up
- **WHEN** a valid sign-up is posted
- **THEN** the server output contains `POST /api/signup 201` and contains neither the parent's name nor the email

### Requirement: Page sends one request after client validation
After the existing client-side validation passes, the page SHALL send one JSON `POST` to `/api/signup` with
`grade` and `months` as numbers. While it waits, further submits MUST be ignored, the button gets
`aria-disabled="true"` and keeps focus. The request MUST time out after 10 seconds.

#### Scenario: Invalid form never reaches the server
- **WHEN** the form fails client-side validation
- **THEN** no request is sent and the existing field errors are shown as before

#### Scenario: Double submit
- **WHEN** a parent presses Enter twice while the request is pending
- **THEN** exactly one request is sent

### Requirement: Page shows the summary from the server's answer
On `201` the page SHALL replace the form with the existing summary, filled from the response: «`program_name`»,
duration label for `months`, `display.total`, and «Мы свяжемся с вами по email»; focus moves to the summary heading.

#### Scenario: Successful submit
- **WHEN** a parent submits Старт, 6 months and the server answers `201`
- **THEN** the summary shows «Старт», «6 месяцев», «26 460 ₽» and «Мы свяжемся с вами по email», and focus is on its heading

### Requirement: Page shows server field errors next to the fields
On `400` with `errors`, the page SHALL show each message for `program`, `grade`, `parent_name`, `email`, `consent`
in that field's existing error element and focus the first of them in form order. With `suggested_program` it
MUST show the existing mismatch message and switch button. Any other key MUST show the general error below.

#### Scenario: Server returns an email error
- **WHEN** the server answers `400` with `errors.email` «Проверьте email: например, name@example.ru.»
- **THEN** the text is in `#signup-email-error`, the email field has `aria-invalid="true"` and focus, and the button is active again

#### Scenario: Server returns a grade mismatch
- **WHEN** the server answers `400` with `errors.program` and `suggested_program` `base` for grade 7
- **THEN** the program error shows «Для 7 класса подходит «Основа».» with the button «Выбрать «Основу»», and pressing it selects Основа and recalculates the price

#### Scenario: Server returns an error for a key without a field
- **WHEN** the server answers `400` with only `errors.months`
- **THEN** the general error is shown and the form stays filled in

### Requirement: Page keeps the form when the request fails
If the request fails, times out, or gets any status other than `201` or a `400` with `errors`, the page MUST keep
the form and its values, show «Не удалось отправить заявку. Попробуйте ещё раз.» in a status element outside the
price live region, announced to screen readers, keep focus on the submit button and make it active again.

#### Scenario: Server is not running
- **WHEN** a parent submits a valid form and the request fails (server stopped or page opened via `file://`)
- **THEN** the form stays filled in, the general error is shown and announced once, focus is on the submit button and it is active

#### Scenario: Server hangs
- **WHEN** the server does not answer within 10 seconds
- **THEN** the page shows the general error and the button is active again

#### Scenario: Retry clears the general error
- **WHEN** after a general error the parent submits again and the server answers `201`
- **THEN** the summary is shown and the general error is gone
