# Phase 1 Tasks: Foundation + Market-Data Infrastructure

**In progress.** Phase 1 approved by the owner on 2026-10-01 (before task 1.1).
- Done, each awaiting owner review: 1.1–1.6, R1, 1.9, 1.13.
- Blocked (owner decision 2026-10-06): 1.7, 1.8, 1.12. Not started because they depend on a blocked task: 1.10, 1.11, 1.15, 1.14.
- Checkpoints C1 and C2: awaiting owner review. C3 and C4 need the blocked tasks.

This file is the single source of Phase 1 task detail (SPEC §12 points here).
Per task: objective · files · dependencies · acceptance · tests · skill · must NOT implement.
Default skills for every task: `incremental-implementation` + `test-driven-development`; `code-review-and-quality` at each checkpoint.

**Phase-wide constraints**
- **Excluded from Phase 1:**
  - automated network access; NSE downloading; full historical ingestion
  - strategy code; technical indicators; backtesting; portfolio construction; execution simulation; risk-engine implementation
  - Laya; Claude; broker integration
  - paper trading; dashboard
  - tax calculation; trading decisions
  - applying corporate-action rules
- No NSE, niftyindices, BSE, RBI or broker files are ingested (ADR-001 storage caution). Manually downloaded NSE files are **not** used unless the owner separately approves it.
- Committed fixtures are **synthetic** and format-faithful. Parsers are written against the documented real layouts, so real files can be introduced later **without changing domain contracts**.
- **Tool commands:** before first use of `uv`, `uv init`, `uv python`, `gitleaks` or `osv-scanner`, confirm the syntax locally with `--help`. Never run a command copied from docs without that check.

---

- [x] **1.1 Project skeleton** (done 2026-10-01; awaiting owner review)
  - Objective: uv project on Python 3.12, quality tooling configured, empty layered package.
  - Files: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `src/trading/__init__.py`, `src/trading/py.typed`, `src/trading/{domain,application,infrastructure}/__init__.py`, `tests/test_smoke.py`.
  - Dependencies: owner approval of the command list (see Phase 0 package §F).
  - Acceptance: `ruff check`, `ruff format --check`, `mypy` (strict), `pytest` all exit 0; `requires-python = ">=3.12,<3.13"`.
  - Tests: smoke test imports `trading`.
  - Skill: `source-driven-development` (uv/ruff/mypy config verified 2026-09-30).
  - Must NOT: add modules, CLI, or dependencies beyond the approved list.

- [x] **1.2 Architecture contracts** (done 2026-10-01; awaiting owner review)
  - Objective: enforce layering and forbidden imports mechanically.
  - Files (as built): `[tool.importlinter]`, TID251 banned-api and the `"!src/trading/domain/**"` per-file-ignore in `pyproject.toml`; `tests/architecture/test_import_contracts.py`, `test_domain_clock_and_randomness.py`, `test_domain_stdlib_only.py`, `test_model_identifiers.py`, `test_package_inits.py`. Violating packages are generated in `tmp_path` per test (no static fixture package).
  - Dependencies: 1.1.
  - Acceptance:
    - `layers` contract `trading.infrastructure → trading.application → trading.domain`.
    - `forbidden` contract: `trading.domain` may not import polars, pyarrow, anthropic, laya, torch, transformers, httpx, requests, sqlite3, or `trading.application`/`trading.infrastructure` (`include_external_packages = true`).
    - Ruff TID251 bans `datetime.datetime.now`, `datetime.date.today`, `time.time`, `random` in the domain (DC3).
    - DC12 scan test: no model-identifier literals (e.g. `claude-`, `convaiinnovations/`) anywhere under `src/`.
    - Negative tests prove each contract fails on a generated violating package; DC3 is proven under default discovery and `--config pyproject.toml`; no nested Ruff config may exist; root and layer `__init__.py` files contain no imports (remediation R1, 2026-10-05).
    - Contracts for future modules (e.g. backtest ⟂ interventions, DC10) are **deferred** to the phases that create those modules.
  - Tests: negative contract tests.
  - Skill: `source-driven-development` (import-linter docs verified), `test-driven-development`.
  - Must NOT: create placeholder modules just to write contracts for them.

- [x] **1.3 Config and structured logging** (done 2026-10-05; awaiting owner review)
  - Objective: typed configuration from env + TOML; JSON logs.
  - Files: `src/trading/infrastructure/config.py`, `src/trading/infrastructure/logging.py`, `configs/example.toml`, tests.
  - As built: runtime deps `pydantic`, `pydantic-settings` (approved Phase 1 list; Polars waits for its task); mypy `pydantic.mypy` plugin; import-linter contract "Domain imports no logging, os or tomllib". Settings: only `log.level`, all required, keys case-sensitive; non-secret settings only from the TOML file, secrets only from `TRADING_<FIELD>` env vars for top-level `SecretStr` fields (none defined yet); `.env` is not read. Logs: fixed keys `ts, level, logger, event, run_id, track, trading_date, fields, exc, stack`; `configure_logging` owns the root logger; `run_id` supplied by the caller (generated by the CLI in 1.14).
  - Dependencies: 1.1.
  - Acceptance: invalid or missing config fails fast with a clear message; secrets only from env; logs are JSON with `run_id`, `level`, `event`. TOML loading via `TomlConfigSettingsSource` returned from `settings_customise_sources` (verified requirement).
  - Tests: valid/invalid config; log format.
  - Skill: `source-driven-development`, `test-driven-development`.
  - Must NOT: add model ids, credentials, strategy, cost, risk or threshold settings. Thresholds never go through env/general settings (ADR-017).

**Checkpoint C1:** checks green; contracts proven by negative tests; owner review.

- [x] **R1 Review remediation (2026-10-05; awaiting owner review)**: ADR-018/019/020; delivered early, tested, and reused by later tasks:
  - `domain/identity.py` (InstrumentId, Symbol, Isin, dated IdentityMap), `domain/timing.py` (IST, knowledge-time visibility: `known_by`, `effective_on`), `domain/availability.py` (Series, SeriesChange, typed Absence)
  - `application/data_access.py` (ADR-018 access modes, WindowRegistry, IntegrityReport)
  - `infrastructure/storage/canonical.py` (canonical-v1 snapshot id, SourceFileRecord, manifest hash)
  - architecture follow-ups (package-init import ban; DC3 moved into the root config)

- [x] **1.4 Market-data value objects (domain)** (done 2026-10-05; awaiting owner review)
  - Objective: immutable, validated domain types for market data.
  - As built: `market.Bar` (adds published `traded_value`, ADR-012 §2a); `corporate_actions.CorporateAction` (`known_at` optional only without an announcement date: None = unresolved, U1-U3; kind-specific terms deferred to 1.12); `universe.IndexMembershipChange` (IndexMembership as dated ADDED/REMOVED events, closed `IndexName`), `universe.LiquidityThresholds`; shared exact-type checks in `domain/checks.py`; R1 identity/timing refined (type checks, control characters, `start_of_date`). Dev dependency `hypothesis`.
  - Unresolved corporate actions (owner clarification 2026-10-05; ADR-018 §2): every record *carries* the `known_at` field, but only a resolved one *has* a knowledge time.
    - `known_at=None` = unresolved: a parsed record that is visible at no `as_of`, never given a fallback timestamp, and influences nothing downstream until resolved.
    - Still unresolved where a data-quality or evaluation boundary needs it → data-quality failure (1.10).
  - Files: `src/trading/domain/market.py` (Bar keyed by `InstrumentId`, carrying `Series`, `observation_date` and `known_at`; reuse R1 identity/timing/availability types, do not duplicate them), `src/trading/domain/corporate_actions.py` (typed kinds per ADR-007; published ex-date, record date, optional announcement date; source and confidence fields), `src/trading/domain/universe.py` (IndexMembership; `LiquidityThresholds` value object with required fields `min_price`, `min_median_traded_value`, `max_participation`, `order_liquidity_fraction`: **no defaults, no values, not wired to any loader**, ADR-012 §2a); tests.
  - Dependencies: 1.2.
  - Acceptance: frozen dataclasses; invariants enforced (prices > 0; high ≥ max(open, close); low ≤ min(open, close); volume ≥ 0); stdlib only.
  - Tests: unit + hypothesis property tests.
  - Skill: `api-and-interface-design`, `test-driven-development`.
  - Must NOT: add `OpenAuctionQuote` (execution concept, Phase 4), Signal, Order, Fill, Position, Money, or any ledger/risk type.

- [x] **1.5 Trading calendar (domain)** (done 2026-10-05; awaiting owner review)
  - Objective: session arithmetic over a versioned reference list.
  - As built: `domain/calendar.py` `TradingCalendar(version, coverage_start, coverage_end, sessions)`, an explicit sorted session list (no weekday rule), `SessionKind` REGULAR/SPECIAL, `OutsideCalendarError` (unknown) distinct from `NotASessionError`; `reference/calendar/format.md` (format only, no data); synthetic Jan-2030 fixture in `tests/domain/test_calendar.py`. Knowledge time of calendar entries (ADR-018 §2) is **unresolved** and recorded in format.md for 1.9, 1.11 and 4.0.
  - Files: `src/trading/domain/calendar.py`, `reference/calendar/format.md`, a small synthetic calendar fixture; tests.
  - Dependencies: 1.4.
  - Acceptance: next/previous session, is-session, sessions-between; special sessions representable; dates outside the loaded range raise explicitly.
  - Tests: unit tests on the synthetic calendar.
  - Skill: `test-driven-development`.
  - Must NOT: fetch or populate real holiday lists (a curation task after the access decision).

- [x] **1.6 Ports and fake provider (application)** (done 2026-10-06; awaiting owner review)
  - As built: `application/ports.py` (`MarketDataProvider`: identity_map, bars, absences, series_changes, corporate_actions, membership_changes, each with keyword-only `as_of`; `SnapshotStore` (**provisional**); `SnapshotId`; errors `UnknownInstrumentError`, `OutsideCoverageError`, `KnowledgeUnavailableError`, `UnknownSnapshotError`). **Deviation:** `application/market_dataset.py` (`MarketDataset`, `DataOrigin`) added as the validated payload of providers and snapshots (coverage, knowledge cut-off, uniqueness, linked series changes). Fake in `tests/fakes/fake_market_data.py` with synthetic fixture `tests/fakes/synthetic_market.py`; pytest `pythonpath = ["tests"]`. `series_changes` was added after review so a known series change is visible from its own knowledge time. Identity ends (`IdentityMapEnd`) were added on the owner hold so an as-of view never shows a symbol's end before it was known. Contracts: domain no filesystem/process modules, application no network, no provider SDKs anywhere.
  - Objective: `MarketDataProvider` and `SnapshotStore` protocols; in-memory fake.
  - Files: `src/trading/application/ports.py`, `tests/fakes/fake_market_data.py`.
  - Dependencies: 1.4.
  - Acceptance: protocols use domain types only and `InstrumentId` keys; queries take an `as_of` instant and return records filtered by knowledge time (ADR-018/019); bars of all series; typed `Absence` records; the fake supports both.
  - Tests: via 1.9.
  - Skill: `api-and-interface-design`.
  - Must NOT: add Clock, LedgerStore, AlertProvider or FeatureProducer ports.

- [x] **1.9 Provider contract suite** (done 2026-10-06; awaiting owner review)
  - Objective: one reusable suite every `MarketDataProvider` must pass.
  - As built: `tests/contract/market_data_contract.py` (`MarketDataProviderContract`, a base class taking a `make_provider` fixture) and `tests/contract/test_fake_provider.py` (binds the fake). It absorbs the 1.6 suite (`test_market_data_contract.py`, removed, so nothing is duplicated). It adds an exhaustive known-exactly-by-as_of check at every knowledge instant (±1 µs, each probe in IST, UTC and UTC+14) covering every query and identity resolution of every symbol and instrument on every coverage day, compared as multisets; a look-ahead perturbation test (records known later change no earlier answer), separate effective-on-T tests for actions and membership, and series-change error rules. Domain fix: `IdentityMap.ends()` is in content order, not input order. Calendar: the port exposes no calendar query, so the v1-calendar knowledge-time limitation stays recorded for 1.15 and later.
  - Files: `tests/contract/market_data_contract.py`, `tests/contract/test_fake_provider.py`.
  - Dependencies: 1.6.
  - Acceptance (ADR-019 §2–3): **known-by-`as_of`** (nothing with `known_at > as_of`; an action announced before `as_of` with a later ex-date IS returned) and **effective-on-T among known** are tested separately; corporate actions are never filtered by ex-date alone; knowledge time for actions without an announcement date is not inferred (**no fallback policy** in Phase 1), and an unresolved action (`known_at=None`) is never returned as known at any `as_of`; bars of all series returned and tagged; legitimate absence returned as typed `Absence`, never omitted; membership by effective date and knowledge time; deterministic ordering; unknown-instrument errors. Calendar: v1 calendars carry no per-entry knowledge time (reference/calendar/format.md), so a provider must not present one as known-as-of any instant on a sealed or look-ahead-sensitive path until that is resolved.
  - Tests: the fake passes. The NSE file provider must pass it in 1.15.
  - Skill: `test-driven-development`, `doubt-driven-development` (look-ahead guarantee).
  - Must NOT: add network or performance tests.

**Checkpoint C2.**

- [ ] **1.7 Legacy bhavcopy parser (infrastructure)** — **BLOCKED (owner decision 2026-10-06)**
  - Blocked: the repository does not establish the legacy grammar (TIMESTAMP format; delimiter/quoting/line endings; header rules; trailing columns; later column variations; encoding/BOM; numeric grammar; whitespace/padding; duplicate semantics; one-date-per-file; full SERIES grammar). Implementation needs authoritative source documentation or an authoritative sample. No "UNVERIFIED" grammar assumptions are to be created.
  - Decided output: a typed, source-faithful `LegacyBhavcopyRow` with SYMBOL, SERIES, observation date (from TIMESTAMP), OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, TOTTRDQTY, TOTTRDVAL, ISIN when present, and the source line/record number. It does **not** require `InstrumentId` or `known_at`. Conversion to `Bar` happens only after identity mapping (1.8) and a knowledge-time policy exist. `Bar` is not weakened.
  - Knowledge time: none is manufactured. Parser execution time, file modification time, download/acquisition time, current time and the observation date are never used as `known_at`. A later data-governance decision (ADR) defines how an authoritative acquisition/publication fact becomes a knowledge time.
  - The acceptance line below ("→ `Bar`s") is superseded by the decided output above.
  - Objective: parse the pre-July-2024 CM bhavcopy layout (SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP; ISIN when present).
  - Files: `src/trading/infrastructure/market_data/nse_files/legacy_bhavcopy.py`, `tests/fixtures/nse/legacy/*.csv` (synthetic), tests.
  - Dependencies: 1.4.
  - Acceptance: rows of **every series** → `Bar`s with series preserved (no EQ filter in the data layer, ADR-019 §3); malformed rows reported with line numbers, never dropped silently; works with and without an ISIN column.
  - Tests: golden tests on synthetic fixtures.
  - Skill: `test-driven-development`.
  - Must NOT: download; adjust prices; filter the universe.

- [ ] **1.8 UDiFF parser and identity mapping (infrastructure)** — **BLOCKED (owner decision 2026-10-06)**
  - Blocked: depends on 1.7, and also has unresolved source-format evidence (see 1.12).
  - Objective: parse the UDiFF CM bhavcopy (ISIN, `SctySrs`) and map symbols to stable `InstrumentId`s via a symbol-change list.
  - Resolved in 1.6 (owner hold, 2026-10-06): a symbol assignment (`IdentityMapEntry`, open-ended) and its end (`IdentityMapEnd`, with `valid_to`) are separate records, each with its own `known_at`. The map builds `IdentityMap(entries, ends)` from the symbol-change list, recording each end at its own announcement time.
  - Files: `.../nse_files/udiff_bhavcopy.py`, `.../nse_files/identity.py`, synthetic fixtures, tests.
  - Dependencies: 1.7.
  - Acceptance: builds the domain `IdentityMap` (dated, non-overlapping); same instrument → same id across the format switch and across symbol changes; an ISIN change without identity evidence is reported, not silently remapped; unmapped symbol discontinuities reported.
  - Tests: golden + cross-format consistency.
  - Skill: `test-driven-development`, `doubt-driven-development`.
  - Must NOT: fetch the symbol-change list.

- [ ] **1.12 Corporate-action parser (infrastructure)** — **BLOCKED (owner decision 2026-10-06)**
  - Blocked under the same source-fidelity rule as 1.7: the repository does not sufficiently establish the corporate-action record format or the subject grammar (one verified example). Do not implement it with invented subject patterns. 1.8 also stays blocked (depends on 1.7; source-format evidence unresolved).
  - Objective: free-text subjects → typed `CorporateAction` with confidence.
  - Files: `.../nse_files/corporate_actions.py`, synthetic fixtures, tests.
  - Dependencies: 1.4.
  - Acceptance: parses split, bonus, dividend (incl. special); recognises merger, demerger, rights, buyback, other as flagged kinds; unparsed or low-confidence input → data-quality failure record; announcement date captured when present, else marked absent (ADR-007 C3/C4).
  - Tests: golden tests with hand-written subjects per kind, including ambiguous ones.
  - Skill: `test-driven-development`.
  - Must NOT: apply actions to prices or holdings; encode tax rules; compute C4 fallback knowledge times (Phase 2).

- [ ] **1.10 Validation and data-quality report (application)**
  - Objective: rules that block bad data.
  - From 1.6: `MarketDataset` raises on structural duplicates, so the integrity report must be built from parsed records before a dataset is constructed. Cross-record checks left here: an old-series bar after a series change; a bar outside its symbol's validity; near-duplicate corporate actions (same action from two sources) and a resolved action with an unresolved copy; a calendar session with neither a bar nor an absence (missing observation).
  - Files: `src/trading/application/data_quality.py`, tests.
  - Dependencies: 1.5, 1.7, 1.8, 1.12.
  - Acceptance:
    - **Blocking failures** (block the snapshot or mark the range unusable, with a reason): `MISSING_OBSERVATION` and unsourced legitimate claims; missing sessions vs calendar; OHLC inconsistency; non-positive prices; duplicates; unmapped symbols; unparsed or unrecognised corporate actions; a corporate action whose knowledge time is still unresolved (`known_at=None`) where the range needs it (never inferred, ADR-018 §2).
    - **Not failures** (ADR-019 §3): sourced suspensions, delistings, not-yet-listed periods and series changes; `DATA_UNAVAILABLE` is reported as a coverage gap.
    - Report output for sealed data is an `IntegrityReport` only (ADR-018 §6), built from the R1 closed enums `IntegrityDataset` / `IntegrityRule`; a new rule is a new enum member (reviewed code change), never free text. The runner reads sealed data internally; it never calls `check_access` with an integrity grant.
    - **Review flags only** (U6 unresolved): overnight move > 40% without an action; split/bonus ratio mismatch (ADR-007 C7). Provisional parameters are labelled in the report.
    - No auto-correction.
  - Tests: one corrupted-fixture test per rule.
  - Skill: `test-driven-development`, `doubt-driven-development`.
  - Must NOT: silently drop records; implement waivers that satisfy A19.

- [ ] **1.11 Parquet snapshot store (infrastructure)**
  - Objective: immutable, content-addressed snapshots.
  - Open dependency (task 1.5): calendar versions have no per-entry knowledge time yet (ADR-018 §2; reference/calendar/format.md). Partitioning or sealing calendar data by knowledge time needs that resolved first.
  - Open (from 1.6): the `SnapshotStore` protocol is provisional. A dataset is several tables plus origin, coverage and knowledge cut-off, but ADR-020 defines the id of one table, so the combined id needs an ADR-020 addendum. Provenance (manifest) and metadata are not yet parameters. `read` is unconditioned, so sealing must sit in front of it before real data is stored. Coverage and knowledge cut-off must be persisted (and hashed).
  - Files: `src/trading/infrastructure/storage/parquet_snapshots.py`, tests.
  - Dependencies: 1.6, 1.10.
  - Acceptance: snapshot id = R1 `snapshot_id` (canonical-v1, ADR-020), **never** a hash of Parquet bytes; **Parquet round-trip test**: write → read → same id, and re-writing with different writer options gives the same id; source-file manifest stored with `manifest_hash`; an existing id is never overwritten; only validated data is written; Polars native Parquet writer (no pyarrow); prices stored as `DECIMAL`, no float columns. Snapshot metadata records `origin = synthetic | real`, date range, parser versions and data-quality report hash, so ADR-017 sealing and the real-data guard can build on it later. Partition metadata by knowledge-time window (ADR-018 §2) is recorded; sealing itself is not implemented in Phase 1.
  - Tests: determinism and immutability tests (tmp dirs, synthetic data).
  - Skill: `source-driven-development`, `test-driven-development`.
  - Must NOT: add SQLite or run storage.

**Checkpoint C3.**

- [x] **1.13 Index-membership reference format and loader** (done 2026-10-07; awaiting owner review)
  - Objective: effective-dated membership with a source per change.
  - Approved out of plan order (owner, 2026-10-06): dependencies met; the reference format is repository-defined, not an external NSE grammar.
  - Decided semantics (owner, 2026-10-06). The model stays the dated `IndexMembershipChange` event model (no membership-period/snapshot model).
    - **Gaps:** G1, every covered trading session has a defined membership set. G2, the format declares a coverage range and a complete seed membership set effective at the coverage start. G3, `REMOVED` of an instrument that is not a member and `ADDED` of an instrument that already is are rejected.
    - **Overlaps:** O2, conflicting changes for one instrument on one effective date are rejected. O3, an instrument cannot be added while active or removed while inactive. O1 (overlapping snapshots) does not apply.
    - **Effective dates** need not be trading sessions. The state on session D applies every change with effective date <= D. All changes of one effective date are applied before the member-count check.
    - **Member count** is exactly 100 unless a sourced exception is explicitly recorded; no exception categories or values are invented.
    - **Knowledge time:** every change has its own `known_at`; a date-only announcement follows ADR-018 §1 (end of that date); "members as of D" takes D and `as_of`; changes known later never affect an earlier `as_of` answer.
  - Further owner decisions (2026-10-07):
    - **Count exceptions:** a point-in-time sourced exception (`effective_on`, `expected_count`, `source`, `known_at`). On `effective_on`, a count other than 100 is valid only when an exception for that effective date is known by the requested `as_of`. No date ranges, no "until next change", no exception categories, no report abstraction. Exceptions are retained in `MembershipHistory` for later reporting.
    - **As-of counts:** the complete history keeps the 100-member invariant (with exceptions). A knowledge-limited as-of view may temporarily hold another count, needs no exception, and is not flagged.
    - **Coverage and seed:** the calendar must cover the declared coverage range; every session in it has a defined state; changes take effect inside the range. The seed is the initial state on `coverage_start`, and valid changes effective that day then apply under the normal rules.
    - **Knowledge time:** effective date and knowledge time are independent; the earlier derived knowledge-order rule is removed. A change is visible in `members_on(D, as_of)` when `known_at <= as_of` and its effective date `<= D`.
  - As built: `reference/universe/format.md` (TOML `index-membership-v1`; it separates owner-decided rules, implementation-derived rules and open concerns); `src/trading/infrastructure/market_data/membership.py`:
    - `load_membership(text, calendar)` → `MembershipHistory` (`MembershipSeed`, sorted `IndexMembershipChange` records, `MemberCountException` records);
    - `members_on(day, *, as_of)` and `count_exception(day, *, as_of)`;
    - stable `MembershipProblem` categories.
    Synthetic fixture: `tests/fixtures/universe/nifty100-synthetic.toml`. Open for 1.15: mapping a seed plus same-day changes to `MarketDataset` membership records (one change per instrument and date there).
  - Files: `reference/universe/format.md`, synthetic fixture, `src/trading/infrastructure/market_data/membership.py`, tests.
  - Dependencies: 1.4, 1.5.
  - Acceptance: rejects gaps, overlaps, missing sources, and member counts ≠ 100 unless a sourced exception is recorded; answers "members as of D". **Exceptions are listed in every report** (so they cannot hide a missing member).
  - Tests: valid/invalid synthetic files.
  - Skill: `test-driven-development`.
  - Must NOT: populate real history; access niftyindices.com.

- [ ] **1.15 NSE file `MarketDataProvider` adapter (infrastructure)**
  - Objective: compose parsers, identity mapping, membership and snapshots into a provider.
  - Files: `src/trading/infrastructure/market_data/nse_files/provider.py`, `tests/contract/test_nse_file_provider.py`.
  - Dependencies: 1.8, 1.9, 1.11, 1.12, 1.13.
  - Acceptance: passes the full contract suite (1.9) on synthetic fixtures.
  - Tests: contract suite.
  - Skill: `api-and-interface-design`, `test-driven-development`.
  - Must NOT: add caching layers, network, or price adjustment.

- [ ] **1.14 CLI: data import / data report**
  - Objective: end-to-end use on local files.
  - Files: `src/trading/infrastructure/cli/data.py` (entry point `trading`), tests.
  - Dependencies: 1.15.
  - Acceptance: `trading data import --dir <path>` → snapshot or failure report; `trading data report --snapshot <id>` prints the report; non-zero exit on failures.
  - Tests: integration test on synthetic fixtures in tmp dirs.
  - Skill: `incremental-implementation`, `test-driven-development`.
  - Must NOT: add `download`, backtest or paper commands.

**Checkpoint C4:** whole-phase review with `code-review-and-quality` (five axes); owner review; exit criteria met.

**Phase 1 exit criteria:** all checks green; contract, golden, determinism and negative-architecture tests pass; a data-quality report generated end-to-end **on synthetic fixtures**; open data-access decisions listed with status.
