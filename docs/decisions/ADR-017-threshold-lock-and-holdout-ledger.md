# ADR-017: Mechanically enforced threshold lock, sealed holdout and holdout-use ledger

## Status
Accepted (owner requirement, 2026-09-30) as the required mechanism; revised after an adversarial review the same day.
**Amended 2026-10-05 by [ADR-018](ADR-018-data-access-modes-and-information-timing.md)** (access modes; integrity and
operational reads; forward window; capital grid within one use) and **[ADR-020](ADR-020-snapshot-canonical-identity-and-provenance.md)**
(snapshot hashes in the use key are canonical-content hashes). Where §5–§6 conflict with ADR-018, ADR-018 governs.
Implemented as **task 4.0**, at the start of Phase 4 (backtesting), so it exists before any code can compute a strategy
result on real data. Not part of Phase 1.

## Date
2026-09-30

## Context
- Owner requirements:
  - ADR-012 limits and ADR-013 criteria are locked before Phase 6 or **any** strategy evaluation produces results.
  - Versioned threshold configs; every run records the exact versions; runs are refused without a lock.
  - Phase 6+ code cannot modify thresholds; changes need a new ADR, a new config version and a new protocol.
  - Holdout: every configuration tested counts as a use; max 3 per window; new window after 3; no silent reset; metadata persisted; the limit enforced by code.
- A single-user local repository cannot be made tamper-*proof* against its owner. The goal is that **the normal code path cannot bypass**, and any out-of-band bypass is **detectable**.

## Decision

### 1. When results may exist
- **Real-data rule:** every snapshot carries `origin = synthetic | real` (from Phase 1) and a date range.
  Any command that runs a strategy, a baseline portfolio or the engine over a `real` snapshot is an **evaluation run**, including `backtest`.
- **Before the lock exists, the engine refuses `real` snapshots.** Phases 2–5 are developed and tested on synthetic data only.
- **Non-strategy data measurements are allowed before the lock:** data-quality reports and liquidity distributions (ADR-012 §2a).
  They compute no returns and no portfolio values, and they exclude holdout dates.

### 2. Versioned threshold configuration
- Thresholds live only in immutable files: `configs/locked/evaluation-criteria.v<N>.toml` and `configs/locked/risk-limits.v<N>.toml`.
- Each declares `version`, `adr`, `adr_sha256`, `locked_on`, `approved_by`. Every field is required. There is no "proposed" state inside a locked file, and a file with a missing value fails validation.
- A new version is a new file. Existing versions are never edited.
- The **maximum holdout uses per window (3)** is a field of the locked evaluation-criteria file, not of any window entry.

### 3. Lock registry
- `configs/locked/LOCKS.toml` (machine-readable) and `docs/decisions/LOCKS.md` (human-readable) list each locked version with
  SHA-256 of the config file, the ADR it implements, **and ADR-017 itself**, plus date and approver. Hashing whole ADR files means a typo fix requires a new lock entry; this cost is accepted.
- Only the owner creates lock entries. An agent may prepare one but must present it for approval.

### 4. Enforcement points
| Mechanism | Enforces |
|---|---|
| **Pre-flight on every evaluation run** | Referenced config versions exist in `LOCKS.toml`; config, ADR and ADR-017 hashes match; else **refuse** (non-zero exit) |
| **Frozen, loader-only thresholds** | Thresholds are obtainable only from the locked-config loader; no env/argument/default path (DC15) |
| **Run manifest** | Config versions and hashes, ADR hashes, ledger head hash, holdout-use entry (if any), code SHA, lockfile hash, snapshot hash, cost-model id. Manifests are written to git-tracked `evaluation-registry/runs/` |
| **Governance tests** (run in the task-check command from 4.0 onward; CI later) | Locked files match LOCKS hashes; ledger chain valid; ledger length ≥ highest `seq` referenced by any committed manifest; windows valid (§5) |
| **Clean-state requirement** | A holdout run refuses to start if `configs/locked/`, `LOCKS.*` or the ledger have uncommitted changes, and records `HEAD` SHA |
| **Floor guard** | Diffs that modify or delete lines in `configs/locked/`, `LOCKS.*` or the ledger are flagged as a weakened bar |

### 5. Sealed holdout
- The holdout date range of each registered window is stored in a **separate sealed snapshot**. Non-holdout snapshots exclude those dates.
  The `MarketDataProvider` used by backtest/research commands cannot open sealed snapshots.
- Only `evaluate --split holdout --window <id>` can open a sealed snapshot, and only for a registered window.
  **Without a registered window, holdout dates are unreadable.**
- **Window rules:** windows cannot overlap; a new window's start date must be later than the end date of **every** earlier window,
  so it requires new data; windows are declared by lock entries; the max-uses value comes from the locked criteria file.

### 6. Holdout-use ledger
- `evaluation-registry/holdout-uses.jsonl`, git-tracked, append-only, hash-chained:
  `{seq, window_id, use_key, strategy_id, purpose, run_id, timestamp, criteria_version, risk_version, code_sha, prev_entry_sha256, entry_sha256}`.
- **Use key** = hash of (strategy config, code SHA, lockfile hash, non-holdout and sealed snapshot hashes, cost-model id,
  membership version, risk-limit version, criteria version). **Any** difference means a new use, including re-judging the same strategy under new criteria.
- **Write-ahead:** the entry is appended and flushed **before** the sealed snapshot is opened. A crash after opening still leaves the use recorded.
- **Identical re-run** (same use key) creates no new use. The result must be byte-identical; a mismatch aborts, is recorded as an incident, and the use still stands.
- **Limit:** opening a window whose ledger already has 3 distinct use keys is **rejected**.
- **Truncation detection:** manifests record the ledger head hash and `seq`, and the governance test fails if the ledger is shorter than any committed manifest implies. Git history shows deletions.
- **No reset command exists.** A new window starts its own count, and old entries remain.
- **Scope:** the limit is **per window, across all strategies and hypotheses**.
- **What one use covers:** one Gate A evaluation of **one candidate configuration**, including its mandated sub-analyses on the
  same candidate: benchmark and baseline comparisons, A4 random-entry seeds, A12 cost multiples, A14 start-date jitter.
  These are prescribed diagnostics of that candidate, not alternative candidates. A13 neighbours never touch the holdout.
- **Any other read of holdout dates** (exploratory, diagnostic, historical Claude runs) is also a use. There is no free peek.

### 7. Changing a locked threshold
1. A superseding ADR states the change, its **non-return justification**, and that it is post hoc if any results exist.
2. A new config version file and a new lock entry.
3. A new protocol: results under the old version stay labelled; any holdout re-evaluation under the new version is a **new use** (§6).

### 8. What this cannot prevent (disclosed)
Rewriting git history, or deleting both manifests and ledger entries consistently. Mitigations: a remote backup of the
repository (owner's choice) and committing each holdout run's manifest promptly. Stronger attestation (external signing) is deferred until before real money.

## Consequences
- Phases 2–5 run only on synthetic data. Real-data results start after full ingestion (blocked on ADR-001 access), the liquidity measurement, and the owner's lock.
- **Ablation budget conflict** (owner decision): the baseline uses 1 of 3 uses, so three augmented variants cannot each get their own holdout use. See the final Phase 0 package.
