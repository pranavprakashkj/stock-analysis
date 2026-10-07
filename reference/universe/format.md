# Index-membership reference format (v1)

Status: format only (task 1.13). **No real membership history is committed.** The curated Nifty 100 history
is built later from NSE Indices reconstitution announcements (ADR-002 §2); Phase 1 uses small synthetic files.

## Model
A **seed** is the complete member set on `coverage_start`. Dated **changes** (`added` / `removed`) follow it, and
sourced **count exceptions** record dates on which the index legitimately has a count other than 100.
This is the dated `IndexMembershipChange` event model (task 1.4), not a list of membership periods.

## Fields
One file is one membership history of one index. TOML, UTF-8. Unknown keys are rejected.

| Field | Meaning |
|---|---|
| `format` | `"index-membership-v1"` |
| `index` | An `IndexName` value: `"NIFTY 100"` |
| `version` | History version id: non-empty, no whitespace (recorded in run manifests and use keys, ADR-018 §4) |
| `coverage_start`, `coverage_end` | Inclusive TOML dates the history is complete for |
| `seed.effective_date` | Must equal `coverage_start` |
| `seed.known_at` | When the seed list was public |
| `seed.source` | Evidence for the seed list (required, non-empty) |
| `seed.members` | The complete member set on `coverage_start`: `InstrumentId` strings, no duplicates |
| `changes[]` | Zero or more changes, in any order |
| `changes[].instrument_id` | `InstrumentId` string (canonical identity; never a symbol) |
| `changes[].change` | `"added"` or `"removed"` |
| `changes[].effective_date` | TOML date inside the coverage range (both ends included). Need not be a trading session |
| `changes[].known_at` | When the change was announced |
| `changes[].source` | Evidence for the change (required, non-empty) |
| `exceptions[]` | Zero or more sourced member-count exceptions |
| `exceptions[].effective_on` | TOML date inside the coverage range |
| `exceptions[].expected_count` | The member count on that date (non-negative integer, not 100) |
| `exceptions[].known_at` | When the exception's evidence was public |
| `exceptions[].source` | Evidence for the count (required, non-empty) |

**Knowledge time** (`known_at` everywhere): a TOML offset date-time is used as given; a TOML date means the end of
that date in IST (ADR-018 §1). A local date-time without an offset is rejected.

```toml
format = "index-membership-v1"
index = "NIFTY 100"
version = "example-v1"
coverage_start = 2030-01-01
coverage_end = 2030-01-15

[seed]
effective_date = 2030-01-01
known_at = 2029-12-20
source = "example: constituent list"
members = ["INS-001", "INS-002"]  # ... all 100 members

[[changes]]
instrument_id = "INS-002"
change = "removed"
effective_date = 2030-01-08
known_at = 2030-01-03T19:00:00+05:30
source = "example: reconstitution notice"

[[exceptions]]
effective_on = 2030-01-08
expected_count = 99
known_at = 2030-01-03
source = "example: notice stating the vacancy"
```
The example is synthetic.

## Owner-decided rules (tasks/todo.md, task 1.13)
| Rule | Rejects (category) |
|---|---|
| G1 coverage | A trading session in the coverage range without a defined member set, including a range the trading calendar does not cover (`coverage_gap`) |
| G2 seed | A missing seed, or a seed not effective on `coverage_start` (`missing_seed`) |
| Seed then changes | Nothing: the seed is the initial state on `coverage_start`; changes effective that day then apply under the normal rules |
| Changes inside coverage | A change effective before `coverage_start` or after `coverage_end` (`outside_coverage`) |
| G3 / O3 transitions | `added` for a current member; `removed` for a non-member; duplicate seed members (`invalid_transition`) |
| O2 conflicts | Two changes for one instrument on one effective date (`conflicting_change`) |
| Count | A member count other than 100 after all changes of an effective date (or on `coverage_start`), unless a sourced exception for that date states the count (`member_count`) |
| Sources | A missing or blank `source` (`missing_source`) |

**Exception semantics:** on `effective_on`, a count other than 100 is valid only when a sourced exception for that
effective date is known by the requested `as_of`. Exceptions are point-in-time: no date ranges, no "until the next
change". They are retained in the history so later reporting can enumerate them.

**Knowledge time:** effective date and knowledge time are independent. A change is visible in "members on D as
of `as_of`" when `known_at <= as_of` and its effective date `<= D`. A later-effective change may be known before
an earlier-effective one.

**As-of counts:** the 100-member rule (with exceptions) applies to the complete history. A knowledge-limited as-of
view may hold a temporary count other than 100 (e.g. a removal announced before its replacement) without any
exception, and is not flagged.

## Implementation-derived rules (follow from the decisions above)
| Rule | Rejects (category) | Why |
|---|---|---|
| Exceptions must be used | An exception for a date with no change and that is not `coverage_start`, or one stating a count other than the actual count (`member_count`) | The count is only evaluated on those dates; an unused or wrong exception could hide a missing member |
| One exception per date | Two exceptions for one date (`member_count`) | The stated count must be unambiguous |
| Exceptions inside coverage | An exception dated outside the coverage range (`outside_coverage`) | Same scope as changes |
| An exception states a non-normal count | `expected_count` of 100 (`member_count`) | It would excuse nothing |
| Non-empty seed | A seed with no members (`missing_seed`) | A seed must be a complete member set |
| Partial views apply visible events in effective order | Nothing | With only the visibility rule, an instrument's membership in a partial view is decided by its latest visible event (`added` → member, `removed` → not a member) |

## Unresolved / future concerns
- **Converting to `MarketDataset` (task 1.15).** `MarketDataset` allows one membership change per
  (index, instrument, effective date). A seed member removed on `coverage_start`, or a seed plus same-day changes,
  needs a defined mapping to `IndexMembershipChange` records there.
- **Reporting exceptions (task 1.10 or later).** Exceptions are retained in `MembershipHistory`; no report type
  exists yet.
- **Calendar knowledge time** remains unresolved (reference/calendar/format.md).

## Domain mapping and queries
`load_membership(text, calendar)` returns a `MembershipHistory`:
- the seed (`MembershipSeed`, members sorted by id);
- the changes as `IndexMembershipChange` records, sorted by effective date, then instrument id;
- the exceptions as `MemberCountException` records, sorted by effective date.

Queries:
- `members_on(D, as_of=...)` applies the seed, then the visible changes. It raises for a D outside the coverage
  range, or an `as_of` before the seed is known: the answer is unknown, not empty.
- `count_exception(D, as_of=...)` returns the exception for exactly that date, if one is known by `as_of`.
