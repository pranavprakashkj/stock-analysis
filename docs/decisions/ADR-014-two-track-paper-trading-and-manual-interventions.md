# ADR-014: Two-track paper trading with separately recorded manual interventions

## Status
Accepted (owner, intent interview and Phase 0 review, 2026-09-30). Intervention cut-off time and the optional shadow tracks (ADR-013 X4) are open.

## Date
2026-09-30

## Context
- Manual interventions are allowed **in paper trading only**.
- The owner must be able to evaluate the algorithm alone, separately from manually influenced performance.
- Backtests must never contain manual intervention.

## Decision
1. **Allowed manual actions (paper only):**
   - veto an algorithm trade (`VETO`)
   - pause / resume an individual stock (`PAUSE_SYMBOL`, `RESUME_SYMBOL`)
   - pause / resume the entire strategy (`PAUSE_STRATEGY`, `RESUME_STRATEGY`)
   - emergency pause-all / resume (`EMERGENCY_PAUSE`, `EMERGENCY_RESUME`), per the owner's earlier requirement: stops **all paper trading activity on both tracks** and cancels all pending orders (ADR-012 §3, locked). It is a system halt, not a trade-level input to the algorithm track; paused sessions are recorded as operational incidents
   - manually close a position (`MANUAL_CLOSE`)
   - manually create a paper trade (`MANUAL_TRADE`)
   - reset the kill switch (`KILL_SWITCH_RESET`, ADR-012)
2. **Separate event types.** Each action is an append-only `InterventionEvent` (never a `Signal` or
   algorithm `DecisionRecord`): id, timestamp, actor, type, target, **mandatory reason**, the algorithm
   decision it overrides (if any), and the resulting `RiskDecision`.
3. **Hard risk controls apply to manual orders** exactly as to algorithm orders (ADR-012). A manual
   order that violates any hard limit is **blocked** and the block is recorded. Manual actions may
   override the *strategy*, never the *risk controls*.
4. **Two tracks, completely separate:**
   - *Algorithm track*: strategy as designed; own ledger, own risk state; **never** receives intervention events.
   - *Live paper track*: algorithm output + interventions = final paper orders; own ledger and risk state.
   Algorithm-only performance is computed **only** from the algorithm track. Manually influenced
   performance is computed only from the live track. Intervention effect = live − algorithm, by type.
5. **Traceability:** each live order links to its algorithm decision (if any) and applied interventions:
   *Algorithm decision → Manual intervention → Final paper order*.
6. **Intervention window:** after signal generation (post T close) until a cut-off before T+1 fill
   processing; late commands are rejected with a message. `EMERGENCY_PAUSE` is accepted any time and applies at the next processable step.
7. **Backtests contain no manual intervention.** The backtest runner has no intervention input and no
   live track. This is enforced by type: `BacktestRunner` has no dependency on `interventions` (import contract).
8. Gate B (ADR-013) is evaluated on the algorithm track.

## Alternatives Considered
- **Single track with intervention flags:** after a veto, the algorithm's own portfolio is unobservable.
- **After-the-fact counterfactual replay:** same result, more complexity; the live algorithm track is also what Gate B replays.

## Rationale
The strategy is stateless (features → signals), so both tracks consume the same signals and differ only in portfolio state and interventions.

## Consequences
- Two ledgers and two risk states per paper day; trivial at daily frequency.
- **Open:** optional shadow tracks for B+C / B+L+C forward tests (ADR-013 X4).
- **Open:** intervention cut-off time.
