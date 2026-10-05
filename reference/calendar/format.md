# Trading calendar reference format (v1)

Status: format only (task 1.5). **No calendar data is committed yet.** Real NSE session lists are curated after
the data-access decision (ADR-001); Phase 1 tests use small synthetic calendars.

## What a calendar file states
One file is one **calendar version**. It lists **every session explicitly**. There is no weekday rule and no
holiday-subtraction rule: a weekday that is not listed is not a session, and a weekend day that is listed is one.

| Field | Meaning |
|---|---|
| `format` | `"trading-calendar-v1"` |
| `version` | Calendar version id: non-empty, no whitespace. Recorded in run manifests and use keys (ADR-018 §4) |
| `coverage_start`, `coverage_end` | Inclusive date range the file is complete for. Unlisted days inside it are known non-sessions; questions about days outside it are errors |
| `sessions` | Every session in increasing date order, no duplicates, each inside the coverage range |
| `sessions[].date` | The session date (domain field `Session.day`) |
| `sessions[].kind` | `regular` or `special` (a session the source marks as special, e.g. a weekend session) |
| `sessions[].source` | Optional reference to the evidence (exchange circular). Documentation only; not part of the domain type |

```toml
format = "trading-calendar-v1"
version = "example-v1"
coverage_start = 2030-01-01
coverage_end = 2030-01-15

[[sessions]]
date = 2030-01-02
kind = "regular"

[[sessions]]
date = 2030-01-05
kind = "special"
source = "example circular reference"
```
The example dates are synthetic.

## Domain mapping
`trading.domain.calendar.TradingCalendar(version, coverage_start, coverage_end, sessions)`, with
`sessions: tuple[Session(day, kind), ...]`. The domain validates order, duplicates and coverage, and refuses
questions outside the coverage range. Parsing this file is an infrastructure task; no loader exists yet.

## Unresolved: knowledge time of calendar entries (required by ADR-018 §2)
ADR-018 §2 seals calendar overrides (e.g. an added special session, or a holiday declared at short notice) by
knowledge time. **v1 has no per-entry knowledge time, and this is unresolved, not decided.**
- A whole-file version cannot stand in for it.
  - If a curated file counts as known only from its curation date, it is invisible to every research `as_of`.
  - If it counts as always known, a short-notice closure on day D leaks into a decision taken before it was announced.
    For example, `next_session(D-1)` at `as_of` D-5 would skip D.
- Until this is resolved, a v1 calendar must not be presented as known-as-of any instant in a sealed or
  look-ahead-sensitive path. Resolution likely adds an optional `sessions[].known_at` (and a `known_at` for removed
  sessions) in a v2 format. An as-of-aware lookup may then change the calendar API.
- The domain calendar does no knowledge-time filtering (task 1.5). The dependency belongs to the provider,
  contract and snapshot tasks (1.9, 1.11) and to sealing (4.0).

## Not modelled
**Session hours** (e.g. a short special session) and their effect on bar publication time.
