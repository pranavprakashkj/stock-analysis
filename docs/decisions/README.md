# Architecture Decision Records

Format: `ADR-NNN-title.md`. Lifecycle: Proposed → Accepted → (Superseded | Deprecated). Never delete an ADR.
**LOCKED** marks an Accepted decision the owner has fixed: it changes only through a superseding ADR approved by the owner.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-market-data-source.md) | Free data behind `MarketDataProvider`; file-based ingestion; no automated NSE access without permission; survivorship rule | Accepted; **acquisition route open** (blocks full ingestion) |
| [002](ADR-002-universe-and-instruments.md) | Point-in-time Nifty 100; keep-but-no-adds on index removal | Accepted |
| [003](ADR-003-bar-frequency-timing-and-fill-model.md) | T-close signal; T+1 official open reference; adverse slippage separate | Accepted |
| [004](ADR-004-starting-capital-as-parameter.md) | Capital grid ₹5L / ₹25L / ₹1Cr; paper at ₹5L | Accepted |
| [005](ADR-005-baseline-strategy-family.md) | Momentum + trend filter as a research hypothesis; pluggable `Strategy` protocol | Accepted |
| [006](ADR-006-evaluation-protocol-and-data-splits.md) | 2011–19 / 2020–22 / sealed 2023–Jun 2026; ablations | Accepted |
| [007](ADR-007-corporate-action-scope.md) | Per-action rules, each classified VERIFIED / PROVISIONAL / NEEDS SOURCE / NEEDS DESIGN DECISION | Proposed (owner review) |
| [008](ADR-008-costs-and-taxes.md) | Versioned cost model (UNVERIFIED values); verified tax-rate table | Accepted (cost values UNVERIFIED) |
| [009](ADR-009-paper-runner-hosting-and-operations.md) | Docker Compose locally; deployment-agnostic; `AlertProvider` | Accepted |
| [010](ADR-010-tech-stack-and-storage.md) | Python 3.12, uv, Pydantic, Polars at the boundary, Parquet, SQLite | Accepted |
| [011](ADR-011-dashboard-technology.md) | React + TypeScript + Vite over the validated API | Accepted |
| [012](ADR-012-risk-controls-and-kill-switch.md) | Risk interface; safety constraints; data-derived liquidity thresholds; independent control flags; kill switch = FREEZE_NEW_BUYS | §3 control behaviour **LOCKED** (except symbol-pause allowances); numeric values to be locked via ADR-017 |
| [013](ADR-013-evaluation-criteria.md) | Gate A / Gate B / ablation criteria, classified STATISTICAL / DESIGN / OPERATIONAL | Gate B treatment and holdout reuse **LOCKED**; numeric criteria **NOT LOCKED** |
| [014](ADR-014-two-track-paper-trading-and-manual-interventions.md) | Two-track paper trading; manual interventions | Accepted |
| [015](ADR-015-baseline-failure-policy.md) | Baseline failure: no paper trading, no loosening, no rescue by Laya/Claude | **LOCKED** |
| [016](ADR-016-optional-augmentation-layers.md) | Laya/Claude optional; cannot override; model ids in config | **LOCKED** |
| [017](ADR-017-threshold-lock-and-holdout-ledger.md) | Enforced threshold lock, sealed holdout, hash-chained holdout-use ledger (task 4.0) | Accepted; amended by 018, 020 |
| [018](ADR-018-data-access-modes-and-information-timing.md) | Access modes (research, integrity, holdout evaluation, operational); time vocabulary; forward window | Accepted |
| [019](ADR-019-instrument-identity-and-market-data-contract.md) | InstrumentId identity; dated symbol map; knowledge-time as-of; all series; typed absence | **LOCKED** |
| [020](ADR-020-snapshot-canonical-identity-and-provenance.md) | Snapshot id = SHA-256 over canonical logical content; separate source-file manifest | Accepted |
