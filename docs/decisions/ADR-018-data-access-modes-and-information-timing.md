# ADR-018: Data access modes and information timing (amends ADR-017 §5–§6)

## Status
Accepted (owner-directed remediation, 2026-10-05). Amends ADR-017 §5 (sealed holdout) and §6 ("any other read is a use").
Phase 1 delivers the timing vocabulary and the pure access-policy function with tests; enforcement inside providers,
snapshots and the ledger is built at the points named in §7.

## Date
2026-10-05

## Context
An adversarial review (2026-10-01) found contradictions in the ADR-017 model:
- every read of a holdout date counted as a use, yet paper trading needs feature look-back into the holdout window;
- only market-data snapshots were sealed; benchmark (TRI), T-bill, membership and corporate-action records for holdout dates were not;
- data-quality checks required on the holdout (ADR-013 A19) would themselves consume a use;
- the capital grid and the full-history checks (A5, A6) interact with the use count;
- data after the current window (Jul 2026 onward) had no rule.

The statistical meaning of the holdout must not weaken, and paper trading must never see information
that was not available at its simulated time.

## Decision

### 1. Time vocabulary (used everywhere: domain types, providers, manifests)
| Term | Meaning | Examples |
|---|---|---|
| **Observation date** | The trading date an observation describes | Bar of D; TRI value of D; T-bill auction date |
| **Knowledge time** (`known_at`) | The earliest instant the information was available to a market participant. Timezone-aware | Bar of D: publication of D's end-of-day file (after D's close). Corporate action: announcement time. Membership change: announcement time. T-bill: result release time |
| **Effective date** | The date an event takes effect | Ex-date; membership effective date; series-change date |
| **As-of instant** (`as_of`) | The information cut-off of a query. A record is visible only if `known_at ≤ as_of` | The decision point after D's data is published |
| **Feature look-back** | Observation dates read to compute a feature at `as_of`, e.g. the previous 252 sessions | Still subject to `known_at ≤ as_of` |
| **Evaluation range** | The dates whose results are scored by a run | Research 2011–2019; holdout window dates |
| **Paper-trading date** | The real trading date D processed by the paper runner; its `as_of` is D's decision point | Forward dates after Gate A |

Rules:
- **A record's visibility depends on its knowledge time**, never only on its observation or effective date.
  A corporate action announced before `as_of` with an ex-date after `as_of` **is** visible (it is known); a bar observed on D is not visible before D's file is published.
- When only a date is known for `known_at`, the record is treated as known at the **end of that date** (conservative within the day).
  ADR-007's fallback rules (U1–U3) decide knowledge time where it is missing. They are not implemented in Phase 1.
- Knowledge times are stored timezone-aware. Conversion to the IST trading calendar happens in infrastructure.

### 2. Windows
- A **window** is a registered date range (`window_id`, `start`, `end` or open-ended, **kind**). Windows are declared by lock entries (ADR-017 §3).
  - Kind `HOLDOUT`: sealed evaluation windows; only `gate_a` and `ablation` uses may name them.
  - Kind `FORWARD`: windows consumed by paper trading; only `paper_forward` uses may name them.
  - A use whose purpose does not match its window's kind is denied, so a holdout window cannot be relabelled as a forward window.
- Each use carries a **`config_key`** (the configuration) and a **`use_key`** (the ledger use). Operational access requires one `config_key` across its uses; the `use_key`s differ by window (§4).
- **Window W1** = the ADR-006 holdout, 2023-01-01 → 2026-06-30.
- **Any instant on or after the start of the earliest registered window is sealed.** Information known on or after that start is invisible outside a covering use.
- **Unregistered future dates** (after the last registered window ends, e.g. Jul 2026 onward today) are readable by **no** mode,
  except integrity access (§3 B), until a window covering them is registered.
- Sealing applies to **every date-indexed dataset**: bars (all series), corporate actions, membership changes, identity-map entries
  (symbol/ISIN changes), series changes and typed absences, benchmark TRI, T-bill rates, calendar overrides, and any later feature or
  model output. Sealing is by **knowledge time**, so every such record carries a `known_at` **field**.
  - *Clarification (owner, 2026-10-05; wording only, semantics unchanged):* carrying the field is not the same as having a
    **resolved** knowledge time. A record may carry `known_at = null` when its knowledge time is unresolved, e.g. a corporate
    action without an announcement date (ADR-007 C3/C4, U1–U3).
  - An unresolved record is **visible in no mode and at no `as_of`**: visibility functions never treat it as known.
  - It is never assigned a fallback timestamp. Only an accepted ADR-007 policy can resolve it.
  - Until resolved it influences no strategy, backtest, evaluation, paper trading or corporate-action adjustment.
  - If it is still unresolved where a data-quality or evaluation boundary needs it, it is a **data-quality failure**, never an inference.

### 3. Access modes
| Mode | Purpose | May read | Returns | Counts as a holdout use? |
|---|---|---|---|---|
| **A. RESEARCH** | Backtests, walk-forward, validation, data measurements (e.g. liquidity distributions) | Records with `known_at ≤ as_of`, where `as_of` is **strictly before** the start of the earliest registered window | Full values | No (sealed data is unreachable) |
| **B. INTEGRITY** | Validate sealed and unregistered data: parsing, schema, OHLC consistency, calendar completeness, identity continuity, previous-close continuity | Sealed records are read **only inside the integrity runner** (task 1.10), never through `check_access`, which refuses integrity grants | **Only** an `IntegrityReport`: closed-enum dataset and rule codes, counts, and failure locations (rule, observation date, instrument id). **No prices, volumes, returns, index levels, rates or free text** | No |
| **C. HOLDOUT EVALUATION** | A registered Gate A or ablation use of one candidate configuration (ADR-017 §6) | Records with `known_at ≤ as_of`, where `as_of` ≤ the window's end, for the window named by the use | Full values, **inside the use only** | **Yes, one use**, recorded write-ahead before access |
| **C′. OPERATIONAL (paper)** | Paper trading of the configuration that passed Gate A | Requires **exactly one `paper_forward` use** whose window contains `as_of`. Reads records with `known_at ≤ as_of` from research-era data, the forward window, and earlier windows **only via the same configuration's `gate_a` use** (never an ablation use) | Full values | **No new use per day.** It runs under existing uses of **one configuration key**: the Gate A use on W1 (warm-up) and one `paper_forward` use on the forward window (§4) |
| **D. FUTURE WINDOWS** | — | Nothing until registered | — | — |

### 4. Paper trading and the forward window (resolves the look-back contradiction)
- Paper trading of configuration C is a **forward holdout evaluation of C**: a fixed configuration observed on data that did not exist when it was designed.
- Before paper trading starts, a **forward window** W2 is registered, starting the day after W1 ends (2026-07-01), with an open end.
  **One** use is recorded for C on W2 (purpose `paper-forward`). All paper days of C are covered by that single use.
- **Warm-up look-back** into W1 is covered by C's existing Gate A use on W1. Reading W1 for C reveals nothing new about C.
- **Use keys (amends ADR-017 §6):** a use is keyed by the **configuration key**: strategy config, code SHA, lockfile, cost model, risk and criteria versions, seeds, membership and calendar versions.
  - For a **closed** window, the sealed snapshot hash is also part of the key, so correcting closed-window data after a run is a new use (as before).
  - For an **open forward** window the data grows daily, so its snapshot hashes are **recorded per day in manifests but not part of the key**.
  - Operational access requires the paper configuration key to **equal** the Gate A configuration key. Any code or config change during paper trading is a different configuration: a new use and a restart of the Gate B period (disclosed cost; refactor-only commits included).
- A **different** configuration (e.g. an augmented variant on a shadow track) needs its **own** uses, counted against the same per-window limit.
- The forward window can later be **closed** by a lock entry setting its end date. A future hypothesis then needs a window starting after that end.
- **Consequence, disclosed:** data from 2026-07-01 onward cannot serve as a clean holdout for new hypotheses once C's paper results on it have been seen.
  This is the honest cost of paper trading; ADR-017 §5's "new window must start after every earlier window ends" rule already implies it.

### 5. Uses, capital grid and full-history checks
- **One use covers one candidate configuration across the whole capital grid** (₹5L, ₹25L, ₹1Cr; ADR-004).
  The capital levels are mandated sub-analyses of the same candidate, like A4 seeds, A12 cost multiples and A14 start-date jitter (ADR-017 §6).
  Capital is therefore excluded from the use key.
- Full-history risk checks (ADR-013 A5, A6) and benchmark comparisons that touch W1 run **inside** the same use.
- Seeds for random entry and bootstraps are **part** of the use key (a re-roll is a new use). They are recorded in the manifest.

### 6. Integrity access in detail
- Integrity checks run in a dedicated runner (task 1.10). They may compute on values internally but **emit only** an `IntegrityReport`.
  It contains closed-enum dataset and rule codes, `checked`/`failed` counts per rule, and failure locations `(rule, observation date, instrument id or none)`.
  There is no free text, so a rule name cannot encode a value. A test walks the report type recursively and rejects any field that could carry a value.
- `check_access` refuses integrity grants. Integrity is not a value-read permission.
- Integrity runs are logged (who, when, which dataset, report hash) but do not count as uses.
- **Residual leakage, disclosed:** failure locations reveal *that* an anomaly exists at a date, e.g. a suspension. They reveal no prices or returns.
  The owner accepts this as the minimum needed to satisfy ADR-013 A19 before a use is spent.

### 7. Where each rule is enforced
| Rule | Enforced by | Delivered |
|---|---|---|
| Time vocabulary, `known_at ≤ as_of` visibility | Domain timing types + pure visibility functions | **Phase 1 (remediation)** |
| Access-mode decisions (modes A–D) | Pure application-layer policy function | **Phase 1 (remediation)** |
| `IntegrityReport` carries no values | Type + structural test | **Phase 1 (remediation)** |
| Provider as-of semantics (known-by-T vs effective-on-T) | `MarketDataProvider` contract suite | Task 1.9 |
| Snapshots partitioned by knowledge-time window; sealed partitions | Snapshot store + importer | Task 1.11 (partition metadata), task 4.0 (sealing) |
| Use recording, write-ahead, limits | Holdout ledger | Task 4.0 (ADR-017) |
| **Read-time verification that a grant's uses exist in the ledger** (grants issued only by the ledger) | Ledger-issued grants | **Task 4.0. Until then grants are unverified claims**, and the policy must not be wired to real data |
| Paper binding to the Gate A use key | Paper pre-flight | Phase 11 |

## Alternatives Considered
- **Exempt paper trading from the seal:** rejected by the owner; it would let any configuration read W1 freely.
- **Count every paper day as a use:** makes paper trading impossible under a 3-use limit, and is statistically wrong: one fixed configuration on one window is one experiment.
- **Seal only market data:** rejected. Benchmark and membership changes in W1 reveal holdout outcomes.

## Consequences
- ADR-017 §6 "any other read of holdout dates is a use" now reads: any **research or evaluation** read is a use. Integrity reads (§6) and operational reads covered by an existing use key (§4) are not new uses.
- The holdout dates are unchanged, and so are the 3-use limit and every threshold.
- Paper trading consumes the forward window W2 for new-hypothesis purposes (§4 consequence).
