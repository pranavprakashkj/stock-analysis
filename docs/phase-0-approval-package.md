# Phase 0 Final Approval Package

Date: 2026-09-30 · Status: **awaiting owner approval**. Nothing installed · no application code · nothing committed.
Detail: [SPEC.md](../SPEC.md), [ADR index](decisions/README.md), [tasks/plan.md](../tasks/plan.md), [tasks/todo.md](../tasks/todo.md).

## A. Final locked decisions
| # | Decision | Where |
|---|---|---|
| 1 | No scripted access to restricted sources without permission; pursue NSE permission; investigate a broker API; broker data is **not** assumed survivorship-safe; delisted/merged/renamed/suspended cases are tested explicitly | ADR-001 |
| 2 | Kill switch: freeze new buys, never liquidate; emergency pause stops **all** paper trading activity (both tracks); no liquidate-all in V1; independent flags; only a manual reset clears the freeze | ADR-012 §3 |
| 3 | Failed baseline: no paper trading of it; no loosening; no Laya/Claude rescue; infrastructure kept; new hypothesis; failure recorded as a valid result | ADR-015 |
| 4 | Laya/Claude optional; cannot override strategy, risk, limits or execution; model ids in config; leaked historical Claude results exploratory; admission only through predefined ablation | ADR-016 |
| 5 | Gate B: B5 NOT ASSESSED; INCOMPLETE for execution realism; V1 cannot authorise real money; diagnostics never presented as proof | ADR-013 |
| 6 | Holdout: every configuration is a use; max 3 per window; new window after 3; no reset; persisted; enforced by code | ADR-013, ADR-017 |
| 7 | Lock mechanism: versioned immutable threshold configs, lock registry, pre-flight refusal, manifests, governance tests, sealed holdout, write-ahead hash-chained ledger. Implemented as task 4.0, before any engine touches real data | ADR-017 |
| 8 | Liquidity thresholds are DATA-DERIVED SAFETY THRESHOLDS, never strategy parameters. Phase 1 defines the value object only | ADR-012 §2a |
| 9 | Unresolved corporate-action rules are never applied; an event needing one becomes a data-quality failure | ADR-007 register |
| 10 | Phase 1 boundary and synthetic-only fixtures | tasks/todo.md |

## B–J
See the conversation summary of 2026-09-30.
