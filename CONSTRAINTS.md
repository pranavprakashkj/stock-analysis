# Constraints

Last reviewed: 2026-09-30 · Status: **Draft**, awaiting owner approval

This file is the project's quality bar. It does not get weakened to make a change pass.
Tightening is silent; loosening requires an explicit owner decision recorded in the commit message.

## Intake (defaults applied, confirm or change)

| Question | Default applied | Why |
|---|---|---|
| Q1 Dimensions beyond the floor | Types, lint, coverage, security (secrets + deps), architecture boundaries, **plus domain constraints below** | Python backend with a financial ledger; UI dimensions deferred until a dashboard exists |
| Q2 Block or warn mid-task | **Block** on floor, types, lint, architecture, domain constraints; coverage blocks on changed lines | Agents will write most of the code; a warning nobody reads is not a constraint |
| Q3 Target numbers vs measure-and-hold | Stated targets for new code (greenfield: nothing to ratchet from yet); ratchet project coverage once code exists | No legacy code, so targets are achievable from day one |
| Q4 Slowest acceptable check before hand-back | ~90 s at task end; fast checks < 5 s; unlimited in CI | Longer loops get skipped |

## Enforcement status (updated 2026-10-05)

| Dimension | Status |
|---|---|
| Types (mypy strict), lint/format (ruff), tests (pytest) | **Enforced** since Task 1.1 |
| Architecture (import-linter; DC1, DC2, DC3, DC12; package `__init__` import ban) | **Enforced** since Task 1.2 / remediation R1 |
| Domain imports no `logging`, `os` or `tomllib` (import-linter) | **Enforced** since Task 1.3 |
| Domain imports no filesystem or process modules; application imports no network libraries; no provider SDKs anywhere (import-linter) | **Enforced** since Task 1.6 |
| Market-data ports, dataset and test fakes: no clock, randomness, environment, files or network (AST scan) | **Enforced** since Task 1.6 |
| Property tests (hypothesis; derandomised, no example database) | **Enforced** since Task 1.4 |
| Coverage (pytest-cov) | **Planned**: not installed yet; added in the task that first needs it |
| Secrets (gitleaks), dependencies (osv-scanner), code security (semgrep) | **Planned**: not installed; owner decision (local vs CI) |
| Floor | Enforced by diff review only; no mechanical floor guard yet |

All Ruff rules, including the domain-only DC3 bans, live in the root `pyproject.toml`. Nested Ruff config files under `src/` or `tests/` are forbidden (test-enforced), because Ruff uses the closest config without merging.

## Floor (always enforced)

- No new suppressions: `# type: ignore`, `# noqa`, `# pragma: no cover`, `pytest.mark.skip`/`xfail` without a linked reason
- No unimplemented stubs: `raise NotImplementedError` in shipped paths, `pass`-only functions, bare `except:` or `except Exception: pass`
- No skipped or deleted tests without a reason in the commit message
- No secrets in source; `.env` is git-ignored; only `.env.example` is committed
- No market data snapshots or SQLite databases committed
- This file, locked evaluation criteria (ADR-013 once locked), and risk hard-limit values are not weakened to make a change pass
- No modification (only additions) of files under `configs/locked/`; `LOCKS.*` and `evaluation-registry/holdout-uses.jsonl` are append-only (ADR-017)

## Enforced with numbers (planned, installed in Phase 1)

| Dimension | Rule | Checked by | Runs at | Reason |
|---|---|---|---|---|
| Types | Zero errors, strict mode | `uv run mypy --strict src tests` | every edit | Strong typing is a core requirement |
| Lint/format | Zero errors | `uv run ruff check . && uv run ruff format --check .` | every edit | Consistency, catches bug classes |
| Secrets | No findings | `gitleaks git --redact --no-banner` (history) / `gitleaks dir --redact --no-banner` (working tree); `detect` is deprecated since v8.19.0 | every commit, CI | API keys (Anthropic, broker later) must never land in git; `--redact` keeps values out of logs |
| Coverage: changed lines | ≥ 80% (≥ 90% in `src/trading/domain/`) | `uv run pytest --cov --cov-report=lcov` + diff intersection | task end, CI | 80% forces a test on every change; domain logic decides money movements, so higher |
| Coverage: project | Must not fall (ratchet, 0.5% tolerance) | same lcov | CI | Holds the line without an arbitrary target |
| Architecture | Zero contract violations | `uv run lint-imports` | task end, CI | Enforces domain purity and model isolation (below) |
| Dependencies | Nothing at high or above | `osv-scanner scan source -r .` | CI | **External** check: judged by a vulnerability database, not our tests |
| Code security | No high findings | `semgrep scan --config p/python` | CI | **External** check |

## Domain constraints (project-specific, enforced by import-linter contracts and dedicated test suites)

Each rule becomes enforceable in the phase that creates the code it governs. Phase 1 activates DC1, DC2, DC3, DC12 and DC17–DC20. The rest activate at their phase:
- DC9 (sealed holdout) and DC13–DC15: task 4.0 (ADR-017), before any engine can run on real data
- DC16: Phase 2
- DC4–DC8, DC10, DC11: when their modules are created

Governance tests run in the local task-check command from 4.0 onward. CI arrives in Phase 13 unless the owner pulls it earlier.

| ID | Rule | Checked by | Reason |
|---|---|---|---|
| DC1 | Layers: `trading.infrastructure` → `trading.application` → `trading.domain`, never reversed | import-linter layers contract | Owner-required dependency direction (ADR-010) |
| DC2 | `trading.domain` (incl. `strategy`) never imports `polars`, `pyarrow`, `anthropic`, `laya`, `torch`, `transformers`, HTTP clients, DB drivers, or any application/infrastructure module | import-linter forbidden contract | Baseline independent of models, I/O, providers and dataframes; models cannot decide trades |
| DC10 | Backtest path has no dependency on `interventions` | import-linter forbidden contract | Backtests never contain manual intervention (ADR-014) |
| DC11 | Every result artifact records `cost_model_id`, its hash and VERIFIED/UNVERIFIED status | integration test on report/manifest schema | Provisional costs never silently become final (ADR-008) |
| DC12 | No model identifiers (e.g. Claude model names, Laya repo/revision) as literals in `src/`; they come from validated config | test scanning `src/` for model-id patterns outside `configs/` | Model choice is configuration (ADR-016) |
| DC13 | **Every** evaluation run (any split) refuses to start unless the referenced locked config versions and ADR files match `configs/locked/LOCKS.toml` hashes; manifest records versions and hashes | harness pre-flight + integration test + governance immutability test (ADR-017) | Criteria and limits locked before results |
| DC14 | Holdout-use ledger is append-only and hash-chained; a 4th use of a window is rejected; no reset path exists | governance tests: chain verification, limit rejection, missing-ledger refusal (ADR-017) | Holdout reuse control |
| DC15 | Evaluation and risk code obtain thresholds only from the locked-config loader; no threshold literals | import-linter forbidden contract + test scanning for threshold names/literals | Thresholds cannot drift in code |
| DC16 | A corporate-action rule with status `UNRESOLVED` is never applied; the event becomes a data-quality failure | unit + integration tests (ADR-007 register) | Unresolved rules never become silent behaviour |
| DC3 | No wall-clock (`datetime.now`, `date.today`, `time.time`) or unseeded randomness in `trading.domain` | ruff TID251 banned-api in root `pyproject.toml`, scoped by `"!src/trading/domain/**"` per-file-ignore; tested under default discovery and `--config pyproject.toml` | Determinism and reproducibility |
| DC17 | Visibility is decided by knowledge time (`known_at ≤ as_of`) and the ADR-018 access modes; no mode reads unregistered future dates; integrity output carries no market values | `tests/domain/test_timing.py`, `tests/application/test_data_access.py` | Holdout meaning and look-ahead (ADR-018) |
| DC18 | Instruments are keyed by `InstrumentId`; the symbol map is dated and non-overlapping | `tests/domain/test_identity.py` | Identity (ADR-019) |
| DC19 | Absence is typed; legitimate reasons need evidence; unsourced or unexplained absence is a failure | `tests/domain/test_availability.py` | No stale-price optimism or false failures (ADR-019) |
| DC20 | Snapshot id = canonical-v1 SHA-256 over logical content; provenance is separate | `tests/infrastructure/test_canonical_snapshot.py` | Reproducible identity (ADR-020) |
| DC4 | Every feature has a look-ahead perturbation test | `tests/lookahead/` + a registry test that fails if a registered feature lacks one | Look-ahead bias is the costliest silent error in backtesting |
| DC5 | Determinism: two runs with the same manifest are byte-identical | `tests/integration/test_determinism.py` | Reproducibility requirement |
| DC6 | Every order passes through `risk`; no code path creates a fill without a risk decision record | integration test + type design (`execution` accepts only `RiskApprovedOrder`, constructible only by `RiskEngine.check`) | Hard limits cannot be bypassed, including by manual trades |
| DC7 | Manual interventions are a distinct record type and never written to the algorithm track | unit + integration tests on `interventions` | Separation of algorithm vs manual performance |
| DC8 | Cost model matches golden contract-note cases to the paisa | `tests/golden/` | Cost underestimation inflates results |
| DC9 | Holdout snapshot readable only via the sealed evaluate command; every access logged | integration test | Prevents goalpost moving |

## Measured, not yet enforced

| Metric | Today | Direction |
|---|---|---|
| Project coverage | n/a (no code) | recorded after Phase 1; must not fall |
| Task-check duration | n/a | must stay ≤ 90 s |

## Deferred dimensions

| Dimension | Why deferred | Revisit |
|---|---|---|
| Accessibility (axe) | No UI until Phase 12 | Phase 12 (React dashboard, ADR-011) |
| Web performance | Same | Phase 12 |
| Mutation testing (mutmut) | Valuable for risk/cost/ledger assertions; add once those exist | Phase 4 (costs/ledger), Phase 7 (risk) |

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|---|---|---|---|---|---|
| (none) | | | | | |
