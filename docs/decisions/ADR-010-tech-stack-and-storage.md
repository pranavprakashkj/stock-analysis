# ADR-010: Python 3.12 + uv, Pydantic, Polars at the boundary, Parquet snapshots, SQLite ledgers

## Status
Accepted (owner, 2026-09-30)

## Date
2026-09-30

## Context
- Laya is Python/PyTorch-only; the machine has Python 3.14, which the ML stack may lag.
- Strong typing, reproducibility and minimal dependencies are requirements.
- The owner requires dependency direction **Infrastructure → Application → Domain**, never reversed,
  and that dataframe objects never leak into domain models.

## Decision
| Concern | Choice |
|---|---|
| Runtime | Python **3.12** via **uv** (lockfile committed) |
| Validation/config | Pydantic v2 + pydantic-settings; TOML configs validated at load |
| Dataframes | **Polars**, only in application and infrastructure layers |
| Market data | Parquet snapshots written/read by Polars; snapshot id = content hash |
| Ledger/audit | SQLite (stdlib `sqlite3`); one DB per backtest run; one per paper track; WAL mode |
| Money | `Decimal` rupees quantised to paise in ledger and costs; float64 in feature math |
| Tests | pytest, pytest-cov, hypothesis |
| Quality | ruff, mypy --strict, import-linter |
| Logging | stdlib `logging` with a JSON formatter |
| API (later) | FastAPI |

### Layering and the dataframe boundary
```
infrastructure  (adapters: NSE files, Parquet/SQLite, Laya, Claude, alerts; interface: API, CLI)
      ↓ depends on
application     (engine, feature engine, evaluation, interventions, paper runner; ports/protocols; Polars allowed here)
      ↓ depends on
domain          (value objects, strategy, portfolio construction, risk, costs, execution rules, ledger rules; pure Python; no Polars)
```
- Domain models are frozen dataclasses of plain Python/`Decimal`/`date` values.
- The feature engine computes with Polars in the application layer and hands the domain a typed
  `FeatureSet` value object (e.g. `Mapping[InstrumentId, FeatureVector]`, keyed by `InstrumentId` per ADR-019). No `pl.DataFrame`, `pl.Series` or Polars dtypes cross into domain.
- Enforced by import-linter: `trading.domain` may not import `polars`, `pyarrow`, or any application/infrastructure module.

## Alternatives Considered
- **pandas:** ubiquitous, but index semantics and silent dtype coercion are common bug sources; weaker typing.
- **Poetry/pip-tools:** uv is faster and manages the interpreter.
- **PostgreSQL/Timescale:** a server for a single-writer workload; unnecessary in V1.
- **Polars in the domain:** faster vectorised strategies, but couples business logic to a library and weakens typing. Rejected by owner.

## Rationale
Smallest stack meeting typing, reproducibility and Laya compatibility, with the domain independent of every library except the standard library.

## Consequences
- Converting feature frames to per-symbol value objects costs some performance; negligible for ~100 symbols × daily bars.
- `uv` must be installed (Phase 1, needs approval).
