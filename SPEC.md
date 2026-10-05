# Spec: NSE Systematic Trading System (V1)

Status: **Draft v2**, revised per owner Phase 0 review (2026-09-30); awaiting final approval
Related: [Intent](docs/intent/trading-system.md) · [Capability map](CAPABILITY-MAP.md) ·
[Constraints](CONSTRAINTS.md) · [Decisions](docs/decisions/README.md)

---

## 1. Objective

Build a robust, reproducible algorithmic trading system for Indian equities that can be evaluated
historically and then run continuously in **paper trading**. It is the evidence base for a later,
separate decision about trading real money in the owner's account.

The system answers one question honestly: *does this systematic strategy deserve real capital?* It must be able to answer "no".

### User stories
1. Ingest free NSE end-of-day data into validated, immutable snapshots; data problems surface as failures.
2. Backtest a systematic strategy with versioned Indian costs, adverse slippage, corporate actions and point-in-time universe membership.
3. Evaluate against **pre-registered, locked criteria** and see a pass/fail table, failures first.
4. Add new strategies without changing the engine.
5. Run controlled ablations: Baseline, +Laya, +Claude, +Laya+Claude.
6. Run a Gate-A-passing strategy in paper trading daily on two tracks (algorithm-only, live paper).
7. Veto, pause a stock, pause the strategy, emergency-pause, close a position, or add a manual trade.
   Each is recorded separately and always passes hard risk limits.
8. See *Algorithm decision → Manual intervention → Final paper order* for every trade, and intervention P&L attribution.
9. Audit any decision: inputs, signal, every risk check, sizing, the three prices, order and fill.

### Non-goals (V1)
Real-money execution or broker order placement · F&O, shorting, leverage, intraday · multiple users/auth ·
Claude or Laya deciding trades · optimise-until-pass workflows · full merger/demerger modelling · paid data ·
automated NSE scraping as core ingestion.

---

## 2. Architecture

### Layers (ADR-010)
```
Infrastructure   NSE file provider · Parquet/SQLite stores · alerts · Laya · Claude · CLI · API · Dashboard
      ↓
Application      ports · feature engine (Polars) · engine · audit · evaluation · interventions · paper runner
      ↓
Domain           value objects · calendar · strategy · portfolio construction · risk · costs · execution rules · ledger rules
```
Dependencies point downward only. Domain is pure Python: no I/O, wall clock, unseeded randomness,
Polars, model SDKs, HTTP, DB drivers or UI.

### Principles
1. **One engine for backtest and paper.** Only the data source and clock differ.
2. **Point-in-time everything.** Queries are "as of trading date D"; the engine cannot request later data.
3. **Stateless, pluggable strategies.** `Strategy.generate(FeatureSet, as_of) → Signals` (ADR-005).
   Portfolio-dependent logic lives in `risk`.
4. **Risk is the only gate to orders.** Only `RiskEngine.check` creates `RiskApprovedOrder`; the
   simulator accepts nothing else. Algorithm and manual orders face the same hard limits (ADR-012).
5. **Three distinct prices** (ADR-003): signal price (T close), reference execution price (T+1 official
   open), simulated fill price (reference + adverse slippage). The simulator never sees data after the T+1 open.
6. **Models are optional feature producers.** Laya and Claude enter only via `FeatureProducer` and must win an ablation.
7. **Append-only records** with versions: cost model id, config hash, data snapshot hash, criteria hash.

### Daily step (identical in backtest and paper, per trading date D)
1. Apply corporate actions with ex-date D.
2. Re-check pending orders with `RiskEngine.check` at the D open quote (gap, cash, tradability, pauses).
3. Simulate fills: reference = D official open; fill = reference ± adverse slippage; sells before buys.
4. Mark to market at D close; update risk state (drawdown, kill switch).
5. Compute point-in-time features as of D close.
6. Strategy → Signals → TargetWeights → `RiskEngine.size` → ProposedOrders → `RiskEngine.check`.
7. *(Paper, live track only)* apply InterventionEvents from the intervention window, re-checked by `risk`.
8. Write decision records (with all three prices) and the day's manifest entry.

### Paper trading: two tracks (ADR-014)
Algorithm track (never sees interventions) and live paper track (algorithm + interventions). Algorithm-only
and manually influenced performance are computed from separate ledgers. Backtests have no intervention input.

### Roles of Laya and Claude

| | Laya | Claude |
|---|---|---|
| May | Produce optional timestamped classification features | Produce optional structured news features; write non-authoritative explanations and reports (stored apart from decision records) |
| Never | Place, veto or size orders; change risk limits; be a prerequisite of the baseline | Same |
| Leakage | Fine-tune on research only (with embargo); calibrate on validation only; never touch holdout | Historical results within its training window are exploratory only; admission needs a forward test (ADR-013 X4, open) |
| Admission | Only with an "improves" verdict (ADR-013 X1–X6) | Same |
| Reproducibility | Pinned model revision; CPU inference | Model id, prompt hash, full output stored; a backtest cache miss fails the run |

---

## 3. Tech Stack (ADR-010, ADR-011)

| Concern | Choice |
|---|---|
| Language | Python 3.12 via uv (lockfile committed) |
| Validation/config | Pydantic v2, pydantic-settings, TOML |
| Dataframes | Polars (application and infrastructure only) |
| Storage | Parquet snapshots; SQLite ledgers/audit |
| Tests | pytest, pytest-cov, hypothesis |
| Quality | ruff, mypy --strict, import-linter |
| API | FastAPI (Phase 12) |
| Dashboard | React + TypeScript + Vite (Phase 12) |
| Runtime | Docker Compose locally (Phase 11); deployment-agnostic |

No dependencies are installed until Phase 1 is approved.

---

## 4. Commands (planned; created in Phase 1, extended later)

```
Setup:        uv sync
Fast checks:  uv run ruff check . && uv run ruff format --check . && uv run mypy
Tests:        uv run pytest
Task checks:  uv run pytest --cov --cov-report=lcov && uv run lint-imports
Full checks:  task checks && gitleaks git --redact --no-banner && osv-scanner scan source -r .
Import data:  uv run trading data import --dir <import-dir>                           (Phase 1; synthetic fixtures only in Phase 1)
Data report:  uv run trading data report --snapshot <id>                              (Phase 1)
Backtest:     uv run trading backtest --config configs/<strategy>.toml                 (Phase 4+)
Evaluate:     uv run trading evaluate --config ... --split research|validation         (Phase 6)
Holdout:      uv run trading evaluate --split holdout --window <id>   (ADR-017: lock pre-flight, registered window, write-ahead ledger entry, ≤ 3 uses)
Paper:        uv run trading paper run [--date YYYY-MM-DD]                             (Phase 11)
Emergency:    uv run trading paper emergency-pause --reason "..."                      (Phase 11)
```

---

## 5. Project Structure (planned)

```
SPEC.md  CAPABILITY-MAP.md  CONSTRAINTS.md  CLAUDE.md
docs/intent/ · docs/decisions/ · docs/data/ (data feasibility & terms) · docs/runbook/
src/trading/
  domain/           core, calendar, strategy/, portfolio_construction, risk, costs, execution, ledger
  application/      ports, feature_engine, engine, audit, evaluation, interventions, paper_runner
  infrastructure/   market_data/nse_files, storage/{parquet,sqlite}, alerts, augment/{laya,claude}, cli, api
dashboard/          React + TS + Vite (Phase 12)
configs/            strategy, risk-limits, cost-models, evaluation (TOML, validated)
reference/          curated, versioned: index membership history, calendar holidays/special sessions
data/               imports and snapshots (git-ignored)
tests/  unit/ · property/ · golden/ · lookahead/ · contract/ · integration/
```

---

## 6. Code Style

Illustrative only:

```python
@dataclass(frozen=True, slots=True)
class Signal:
    instrument_id: InstrumentId    # canonical identity (ADR-019); Symbol is display-only
    as_of: TradingDate
    action: Action                 # BUY | SELL | HOLD
    score: float
    reasons: tuple[ReasonCode, ...]


class Strategy(Protocol):
    name: str
    def generate(self, features: FeatureSet, as_of: TradingDate) -> Sequence[Signal]: ...
```

- Frozen dataclasses (domain) or Pydantic models (boundaries); no bare dicts or dataframes across layers.
- `Decimal` paise-quantised money in ledger/costs; float64 in feature math.
- Explicit domain exceptions / result types; no silent `except`.
- Structured JSON logs with `run_id`, `track`, `trading_date`.
- Small functions; composition over inheritance; interfaces as `typing.Protocol`.

---

## 7. Testing Strategy

| Level | What | Location |
|---|---|---|
| Unit | Domain functions; table-driven risk rules; cost components | `tests/unit/` |
| Property | Ledger invariants (no negative cash/shares; value conservation across fills and corporate actions) | `tests/property/` |
| Golden | Hand-computed cost cases (provisional model), corporate-action effects, P&L | `tests/golden/` |
| Look-ahead | Perturb anything after T (bars, corporate actions, membership, T+1 high/low/close) → decisions at T and fills at T+1 unchanged | `tests/lookahead/` |
| Contract | Every `MarketDataProvider` passes one suite | `tests/contract/` |
| Integration | Engine over fixtures with fakes; determinism (byte-identical reruns) | `tests/integration/` |
| Replay | Paper algorithm-track decisions reproduced by backtest replay | Phase 11 |
| Browser | Dashboard controls and decision → intervention → order display | Phase 12 |

---

## 8. Boundaries

**Always:** run task checks before commits · query as-of dates · inject clock/data/storage · record reason
codes · route every order through `risk` · record every run in the trial registry · validate inputs at boundaries ·
state the cost-model version and status in every result.

**Ask first:** adding dependencies · changing locked criteria (new ADR) · changing risk limits · changing
cost model or fill model · running the holdout · changing module boundaries · any automated download from NSE.

**Never:** let Claude/Laya place, veto or size orders · record a manual action as an algorithm decision ·
put manual input into a backtest · select parameters on validation or holdout · read holdout dates outside a
recorded holdout use, or exceed 3 uses per window (a revised config on the holdout is a new use **and** carries the
`holdout-contaminated` label) · run a strategy on real data before the ADR-017 lock · weaken CONSTRAINTS.md · commit secrets or data ·
place real orders · silently change split dates.

---

## 9. Success Criteria (V1)

1. Data: research + validation windows imported into content-hashed snapshots, and holdout dates into a **sealed** snapshot (ADR-017 §5),
   each with a data-quality report; coverage limitations flagged to the owner, not hidden.
2. Point-in-time Nifty 100 membership reconstructed and reconciled against published index levels.
3. Determinism: same manifest → byte-identical outputs.
4. Look-ahead suite passes for every feature, signal, order and fill path.
5. Cost model computes golden cases exactly (to the paisa) and every report shows the cost-model version and status.
6. A new strategy can be added and evaluated with zero engine changes (demonstrated by a second trivial strategy in tests).
7. Baseline has a recorded, locked-criteria Gate A verdict (pass **or** fail).
8. Ablations B / B+L / B+C / B+L+C produce verdicts (improves / no improvement / inconclusive) under the locked methodology.
9. If a strategy passes Gate A: the paper runner runs unattended, catches up in order, alerts, and replays identically.
10. All manual controls work, are risk-checked, and are attributed separately.

---

## 10. Open Questions

See §11 sequencing notes and the ADR open items; consolidated list in the Phase 0 review summary.

---

## 11. Development Sequence (owner-approved 2026-09-30)

| # | Phase | Notes |
|---|---|---|
| 1 | Foundation + market data | Tooling, market-data value objects, calendar, NSE file provider, snapshots, data feasibility |
| 2 | Domain models | Remaining value objects; ledger rules; corporate-action rule registry with statuses (ADR-007 register; `UNRESOLVED` rules never applied) |
| 3 | Features | Point-in-time feature engine |
| 4 | Backtesting | **4.0 first:** ADR-017 lock mechanism, sealed holdout, holdout ledger, governance tests; the engine refuses `real` snapshots until a lock exists. Then engine, costs, execution, audit. **Minimal hard rules here:** no leverage, no shorting, cash check (ledger/execution invariants), plus a simple interim sizer. Developed on synthetic data only |
| 5 | Baseline strategy | `Strategy` protocol + momentum/trend-filter hypothesis |
| 6 | Preliminary evaluation | **Preconditions, in order:** full ingestion (after the ADR-001 access decision) → liquidity distributions measured on research + validation dates with the pre-registered rule (ADR-012 §2a; no strategy output) → owner locks ADR-012 + ADR-013 (ADR-017). Only then research and validation reports, labelled `pre-risk-engine`, informational |
| 7 | Risk engine | Configurable limits (locked values), volatility sizing, kill switch (FREEZE_NEW_BUYS) |
| 8 | Locked Gate A | Single sealed holdout run under the already-locked criteria → recorded verdict; failure handled by ADR-015 |
| 9 | Laya experiment | Separate from the baseline; B vs B+L |
| 10 | Claude experiment | Separate; historical results exploratory only where Claude may know the period; forward shadow-track design |
| 11 | Paper trading | Requires a Gate A pass at ₹5L; two tracks; optional shadow tracks for augmented variants |
| 12 | Dashboard | React + TS + Vite over the API |
| 13 | Hardening | CI, security review, runbook |

Laya and Claude are never prerequisites for the baseline and never determine trades unless an experiment passes the locked admission criteria (ADR-013 X1–X6).

### Baseline failure (locked, ADR-015)
If the baseline fails Gate A: no full paper trading of it; infrastructure preserved; a new hypothesis is researched
as a separately registered effort; thresholds are not loosened; Laya/Claude are not added to rescue it.

---

## 12. Phase 1 Scope: Foundation + Market Data

**Goal:** a typed, tested skeleton and a validated, snapshot-based market-data pipeline that works on
**imported files**, whatever the acquisition route turns out to be. Phase 1 does not depend on the unresolved
acquisition decision (ADR-001). **Full historical ingestion waits for that decision.**

**Done before Phase 1 (Phase 0 output):** [feasibility review](docs/data/feasibility-2026-09-30.md), which covers the terms check and coverage survey.

**Tasks:** 1.1–1.15, specified in **[tasks/todo.md](tasks/todo.md)** (single source of task detail; plan and checkpoints in [tasks/plan.md](tasks/plan.md)).
All Phase 1 tests use **synthetic fixtures**; no NSE files are ingested before permission or an explicit owner decision (ADR-001 storage caution).

**Parallel non-code tasks (owner or agent, as approved):**
- Pursue the ADR-001 acquisition decision (option A request / option B verification).
- Complete the human browser checks listed in the feasibility review.

**Out of scope:** the full exclusion list in [tasks/todo.md](tasks/todo.md) (network, downloading, full ingestion,
strategy, indicators, backtesting, portfolio construction, execution, risk engine, Laya, Claude, broker, paper, dashboard,
tax, trading decisions, applying corporate-action rules), plus API and Docker Compose.

**Dependencies to install (owner approval required at Phase 1 start):** uv (tool); runtime: polars, pydantic,
pydantic-settings; dev: pytest, pytest-cov, hypothesis, mypy, ruff, import-linter. Optional (brew or CI-only): gitleaks, osv-scanner, semgrep.

**Phase 1 exit criteria:** as stated at the end of [tasks/todo.md](tasks/todo.md).
