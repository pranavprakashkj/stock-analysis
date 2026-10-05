# Capability Map: NSE Systematic Trading System (V1)

Status: **Approved structure** (owner, 2026-09-30); revised per Phase 0 review · Source: [intent](docs/intent/trading-system.md), [SPEC.md](SPEC.md)

Module ids are stable (kebab-case, never renamed). Dependency direction is
**Infrastructure → Application → Domain**, never the reverse (ADR-010). No cycles.

## Domain (pure Python; no I/O, no clock, no Polars, no model/HTTP/DB/UI imports)

| Module id | Responsibility | Depends on |
|---|---|---|
| `core-domain` | Value objects: Instrument, Symbol, TradingDate, Bar, OpenAuctionQuote, CorporateAction, IndexMembership, FeatureSet, Signal, TargetWeight, ProposedOrder, RiskApprovedOrder, Fill, Position, PortfolioSnapshot, Money, ReasonCode | — |
| `calendar` | Session arithmetic over a supplied, versioned list of every session (special sessions marked; no weekday or holiday rule) | core-domain |
| `strategy` | `Strategy` protocol + implementations (baseline momentum first). FeatureSet → Signals | core-domain |
| `portfolio-construction` | Signals → TargetWeights | core-domain |
| `risk` | `RiskEngine`: sizing, hard limits, kill switch, pauses; the only producer of `RiskApprovedOrder` | core-domain |
| `costs` | Versioned cost-model rules (brokerage, STT, exchange, GST, SEBI, stamp duty, DP, slippage) | core-domain |
| `execution-sim` | Order lifecycle and fill rules; accepts only `RiskApprovedOrder` + `OpenAuctionQuote` | core-domain, costs |
| `ledger` | Append-only event rules and invariants (cash, holdings, corporate-action effects, dividends) | core-domain |

## Application (orchestration; defines ports; Polars allowed)

| Module id | Responsibility | Depends on |
|---|---|---|
| `ports` | Protocols: `MarketDataProvider`, `SnapshotStore`, `LedgerStore`, `AuditStore`, `Clock`, `AlertProvider`, `FeatureProducer` | core-domain |
| `feature-engine` | Point-in-time feature computation (Polars) → domain `FeatureSet`; hosts optional `FeatureProducer`s | ports, core-domain |
| `engine` | Deterministic daily step shared by backtest and paper | domain modules, feature-engine, ports |
| `audit` | Decision records, intervention records, run manifests, trial registry (logic; storage via port) | ports, core-domain |
| `evaluation` | Backtest runs, walk-forward, sealed holdout, baselines, statistics, criteria report, ablations | engine, audit |
| `interventions` | Validated manual commands → InterventionEvents → live-track orders, always via `risk` | risk, audit, ports |
| `paper-runner` | Scheduling entry, data readiness, catch-up, two-track execution, alerts | engine, interventions, ports |

## Infrastructure (adapters and interfaces; implement ports)

| Module id | Responsibility | Depends on |
|---|---|---|
| `nse-file-provider` | `MarketDataProvider` over imported NSE bhavcopy/corporate-action files (dev only) | ports |
| `storage` | Parquet snapshot store (Polars); SQLite ledger/audit stores | ports |
| `alerts-log` | `LogAlertProvider` | ports |
| `augment-laya` | `FeatureProducer` wrapping Laya (optional) | ports |
| `augment-claude` | `FeatureProducer` for Claude news features + non-authoritative explanations (optional) | ports |
| `cli` | Commands: ingest, backtest, evaluate, paper run, emergency pause | application |
| `api` | FastAPI query + command endpoints | application |
| `dashboard` | React + TypeScript + Vite; talks only to `api` | api (HTTP only) |

## Hard boundary rules (import-linter contracts, see CONSTRAINTS.md)

- Domain imports only the standard library and `core-domain`.
- `strategy` imports nothing except `core-domain` (no Laya, Claude, HTTP, DB drivers, UI, providers, Polars).
- Application imports domain and `ports`; never infrastructure.
- `augment-*` outputs enter only as `FeatureSet` entries with an as-of date via `FeatureProducer`.
- The backtest path has no dependency on `interventions`.

## Development sequence (owner-approved 2026-09-30; see SPEC §11)

| Phase | Name | Modules |
|---|---|---|
| 1 | Foundation + market data | tooling, `core-domain` (market-data value objects only), `calendar`, `ports` (MarketDataProvider, SnapshotStore), `nse-file-provider`, `storage` (Parquet) |
| 2 | Domain models | remaining `core-domain` value objects, `ledger` rules |
| 3 | Features | `feature-engine` |
| 4 | Backtesting | **4.0:** ADR-017 lock, sealed holdout, holdout ledger, governance tests. Then `costs`, `execution-sim`, `audit`, `engine`, `storage` (SQLite), non-strategy baselines; invariants: no leverage, no shorting, cash check; synthetic data only |
| 5 | Baseline strategy | `strategy` (protocol + momentum), `portfolio-construction` |
| 6 | Preliminary evaluation | `evaluation` (research + validation, `pre-risk-engine`); **requires ADR-012/013 locked first** |
| 7 | Risk engine | `risk` |
| 8 | Locked Gate A | `evaluation` (sealed holdout run under the already-locked ADR-012 + ADR-013) |
| 9 | Laya experiment | `augment-laya` |
| 10 | Claude experiment | `augment-claude` |
| 11 | Paper trading | `interventions`, `paper-runner`, `alerts-log`, `cli`, Docker Compose |
| 12 | Dashboard | `api`, `dashboard` |
| 13 | Hardening | CI, security review, runbook |
