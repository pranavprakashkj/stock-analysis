# Implementation Plan: Phase 1: Foundation + Market-Data Infrastructure

Status: **Draft, awaiting owner approval. Nothing here is implemented.**
Scope source: [SPEC.md §12](../SPEC.md), [CAPABILITY-MAP.md](../CAPABILITY-MAP.md), ADR-001/002/003/007/010.

## Overview
Build the typed project skeleton and a validated, snapshot-based market-data pipeline that ingests **imported files**.
It works on a handful of sample files and does not depend on the unresolved data-acquisition route (ADR-001).
No features, strategy, costs, backtest, risk, paper trading, API or UI.

## Architecture decisions this phase relies on
- Layers `trading.infrastructure → trading.application → trading.domain` (ADR-010), enforced by import-linter from task 1.2.
- Domain is pure Python; Polars only in application/infrastructure (ADR-010).
- File-based ingestion; no downloader (ADR-001).
- Money/`Decimal` types are not needed yet (no ledger in Phase 1).

## Fixture policy
- **Decided default:** committed tests use **synthetic, format-faithful fixtures** written by us, so no NSE content is stored in git or snapshots (ADR-001 storage caution).
- **Open (owner):** whether owner-supplied real samples may be used locally before NSE permission. If yes, they live in git-ignored `tests/fixtures/private/` and run only via `uv run pytest -m real_samples`.
- Samples fetched by research scripts during Phase 0 are **not** used as fixtures.

## Dependency graph
```
1.1 skeleton ─┬─ 1.2 import contracts
              ├─ 1.3 config + logging
              └─ 1.4 value objects ─┬─ 1.5 calendar
                                    ├─ 1.6 ports + fake ── 1.9 contract suite
                                    ├─ 1.7 legacy parser ─┐
                                    ├─ 1.8 UDiFF parser ──┼─ 1.10 validation ── 1.11 snapshot store ── 1.14 CLI
                                    ├─ 1.12 CA parser ────┘
                                    └─ 1.13 membership loader
1.8 + 1.9 + 1.11 + 1.12 + 1.13 ── 1.15 NSE file provider ── 1.14 CLI
```

## Task list
Tasks are recorded in [tasks/todo.md](todo.md) with full detail. Order: 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.9 → 1.7 → 1.8 → 1.12 → 1.10 → 1.11 → 1.13 → 1.15 → 1.14.
The contract suite (1.9) is built right after the ports (1.6), so parsers are developed against it (TDD).

### Checkpoints
- **C1 (after 1.1–1.3):** all checks green on the empty skeleton; import contracts fail on a deliberate violation. Owner review.
- **C2 (after 1.4–1.6, 1.9):** value objects, calendar, ports and contract suite green with the fake provider.
- **C3 (after 1.7, 1.8, 1.12, 1.10, 1.11):** parsers, validation and snapshots green on synthetic fixtures; determinism test passes.
- **C4 (after 1.13, 1.15, 1.14):** end-to-end `data import` → snapshot → `data report` on fixtures; code review (code-review-and-quality) of the whole phase; owner review.

## Risks and mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Synthetic fixtures diverge from real file formats | High | Build them from documented column layouts observed in Phase 0 samples; add owner-supplied real-sample tests |
| Acquisition route stays unresolved | Medium | Phase 1 needs only sample files; full ingestion is explicitly out of scope |
| Corporate-action free-text parsing is ambiguous | High | Parser returns typed action **plus confidence**; low-confidence or unknown = data-quality failure (ADR-007 rule 5) |
| Symbol changes before ISIN availability | Medium | Identity mapping via symbol-change list; unmapped discontinuities are failures |
| Scope creep into features/backtest | Medium | "Must NOT implement" list per task; review at C4 |

## Open questions (owner)
- Fixture policy above.
- Package name `trading` (proposed).
- Optional security tools (gitleaks, osv-scanner, semgrep): install locally via Homebrew, or CI-only later?
