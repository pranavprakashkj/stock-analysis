# ADR-019: Instrument identity and the market-data contract

## Status
**LOCKED** (owner-directed remediation, 2026-10-05). Amends ADR-001 D1 and D6, and the illustrative `FeatureSet` and `Signal` examples in ADR-010 and SPEC §6.

## Date
2026-10-05

## Context
- Symbols change (renames, mergers) and can be reused. Keying data by symbol splits one company's history or merges two.
- Corporate actions filtered by ex-date hide actions that were already announced, and leak ones that were not.
- The earlier design returned EQ-series bars only. A collapsing stock that moves to BE/BZ then "disappears", is marked at a stale price, and its absence looks like missing data.

## Decision

### 1. Identity
| Identifier | Role | Rules |
|---|---|---|
| **`InstrumentId`** | **Canonical internal identity** of an equity instrument | Opaque, stable, never reused; assigned once by the identity map. Every dataset, feature, signal, order, position and ledger entry that refers to an instrument uses it |
| **`Symbol`** | Display and external-reference only (NSE trading symbol) | May change; may be reused by a different instrument at a different time; never used as a key across dates |
| **`Isin`** | External identifier | Recorded when available (legacy bhavcopy files have none). Can also change, e.g. on a face-value split, so it is not the canonical identity |

- **Identity mapping is dated:** `IdentityMap` entries `(instrument_id, symbol, valid_from, valid_to | open)`.
  - A symbol change appends an entry for the **same** `InstrumentId`. It never creates a new instrument.
  - A symbol maps to at most one instrument on any date. Overlapping assignments are rejected.
  - Resolving a symbol on a date outside every entry is an explicit error, never a guess.
- Provider contracts take and return `InstrumentId` wherever identity matters. `Symbol` appears only as descriptive data.

### 2. Information timing
Uses the ADR-018 vocabulary: observation date, knowledge time (`known_at`), effective date, `as_of`.
- **Known as of T:** a record is visible at `as_of` iff `known_at ≤ as_of`.
- **Effective on T:** an event takes effect on date T iff `effective_date == T`.
- Providers answer both questions separately:
  1. *what was known by `as_of`* (e.g. corporate actions announced, with any ex-date);
  2. *what takes effect on date T, among what was known by `as_of`*.
- **Corporate actions are filtered by knowledge time, never solely by ex-date.**

### 3. Series and legitimate absence
- Providers return bars of **all series** for an instrument (EQ, BE, BZ, …), each tagged with its series.
  Series is data about the bar, not part of identity. Eligibility rules (ADR-002 §3: new buys from EQ only) are applied later by strategy/risk, not by the data layer.
- A **series change** is a typed, sourced event `(instrument_id, effective_date, from_series, to_series, known_at, source)`. It is **not** a data-quality failure.
- **Absence** of a bar for an instrument on a session is always represented explicitly as one of:

| Reason | Meaning | Legitimate? | Requires |
|---|---|---|---|
| `SUSPENDED` | Trading suspended by the exchange | Yes | Source reference |
| `SERIES_CHANGED` | No bar in the old series because the instrument moved series (the new-series bar is returned) | Yes | Linked series-change event |
| `DELISTED` | After the last trading day | Yes | Source reference |
| `NOT_YET_LISTED` | Before the first trading day | Yes | Source reference |
| `DATA_UNAVAILABLE` | The source does not cover this period or instrument (a coverage limitation) | **No.** Reported as a coverage gap | — |
| `MISSING_OBSERVATION` | Expected but absent, with no explanation | **No.** Data-quality failure | — |

- A legitimate reason **without** a source reference is invalid and must be recorded as `MISSING_OBSERVATION`.
- Legitimate absences are **never** silently converted into missing-data failures, and missing data is never silently treated as legitimate.
- Valuation of absent holdings (STALE rules, write-downs) remains ADR-007 U20/U27 and is not decided here.

## Alternatives Considered
- **ISIN as canonical id:** absent in legacy files and can change on face-value splits.
- **Symbol as key with rename handling downstream:** every consumer would re-implement identity resolution.
- **EQ-only data with series filtering at the source:** causes the stale-price optimism and false missing-data failures found in the review.

## Consequences
- Task 1.4 value objects use `InstrumentId`. Task 1.8 builds the dated identity map from symbol-change lists.
- Task 1.9's contract suite tests both timing questions (§2), all-series return, and the absence representation.
- Task 1.10 treats legitimate, sourced absence and series changes as valid. Unsourced or unexplained absence is a failure.
