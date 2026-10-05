# ADR-012: Risk engine, safety constraints and kill switch

## Status
- **§3 control behaviour: LOCKED (owner, 2026-09-30):**
  - freeze new buys; never liquidate
  - emergency pause stops all paper trading activity (both tracks)
  - no liquidate-all in V1
  - independent flags; pause/resume cannot clear the freeze; only a manual reset clears it

  Exception: the `symbol_paused` allowances are OPEN.
- **§2 numeric values: Proposed**, to be locked via ADR-017 before Phase 6.
- **Liquidity thresholds:** data-derived, chosen later by the §2a methodology.

All values are safety constraints, **never tuned against historical returns**.

## Date
2026-09-30

## Context
- Owner requirement: manual intervention may override the strategy, never the portfolio risk controls. Invalid or
  unsafe orders are **blocked, not warned**.
- Limits shape results, so every value is fixed before any evaluation result exists.

## Decision

### 1. Interface (domain; design sketch, not implementation)
```python
class RiskEngine(Protocol):
    def size(self, targets: Sequence[TargetWeight], portfolio: PortfolioSnapshot,
             quotes: Mapping[InstrumentId, PriceEstimate], limits: RiskLimits) -> Sequence[ProposedOrder]: ...
    def check(self, order: ProposedOrder, source: OrderSource,          # ALGORITHM | MANUAL | CORPORATE_ACTION
              portfolio: PortfolioSnapshot, controls: TradingControls, limits: RiskLimits) -> RiskDecision: ...
    def on_mark_to_market(self, portfolio: PortfolioSnapshot, controls: TradingControls,
                          limits: RiskLimits) -> tuple[TradingControls, Sequence[RiskEvent]]: ...

RiskDecision = Approved(order: RiskApprovedOrder, adjustments) | Blocked(reasons: tuple[RiskViolation, ...])
```
- `execution` accepts only `RiskApprovedOrder`, which only `RiskEngine.check` can construct (CONSTRAINTS DC6).
- `check` runs at order creation (after T close) **and** at fill time against the T+1 open (ADR-003).
- **Hard limits (§2) never depend on `OrderSource`.** Control flags (§3) may depend on it by design; the dependency is stated per flag.

### 2. Limits and their classification

| Limit | Value | Kind | Review policy |
|---|---|---|---|
| No leverage (gross exposure ≤ equity) | always on | **Hard invariant** | Not configurable |
| No shorting (sell qty ≤ held qty) | always on | **Hard invariant** | Not configurable |
| Cash required (buy value + estimated costs ≤ available cash after same-open sells) | always on | **Hard invariant** | Not configurable |
| Max stock weight (at fill price) | **10%** of equity | **Safety constraint** | To be locked (ADR-017) |
| Max portfolio exposure | **98%** of equity | **Safety constraint** | To be locked (ADR-017) |
| Max order value | ≤ **10% of equity** | **Safety constraint** | To be locked (ADR-017) |
| Max order value, liquidity bound | ≤ **0.5%** of the stock's 20-session median daily traded value | **Data-derived safety threshold** (initial value) | May be revised **only before lock**, via §2a. After lock: superseding ADR + new config version + new trial |
| Max positions | **20** | Safety / diversification constraint | To be locked (ADR-017) |
| Kill-switch trigger | **20%** below peak equity | **Safety constraint** | To be locked (ADR-017) |
| Min price, min liquidity, max participation | **Owner input before lock**, via the §2a methodology only | **Data-derived safety thresholds** | As above |

### 2a. Data-derived safety thresholds vs strategy parameters

| | **DATA-DERIVED SAFETY THRESHOLD** | **STRATEGY PARAMETER** |
|---|---|---|
| Examples | Min price, min liquidity (median daily traded value), max participation, the 0.5% order-liquidity bound | Momentum look-back, skip period, holdings count, rebalance frequency, trend-filter window, volatility-sizing window |
| Chosen from | Distributions of **market data only** (prices, traded value, volume) across the eligible universe. **No return, P&L or strategy output is computed or consulted** | Research-period walk-forward results (ADR-005) |
| Lives in | `configs/locked/risk-limits.v<N>.toml` (ADR-017) | Strategy config (registered as trials) |
| May be optimised? | **Never** | Only on the research period, within the pre-declared grid |
| Counted as a trial? | Changing it after lock: yes, new trial and new protocol | Every variant: yes |

**Methodology for liquidity thresholds (executed after full data ingestion, before any strategy evaluation):**
1. **Phase 1:** define the `LiquidityThresholds` value object only. Fields are required, with **no defaults and no values**. It is **not** wired to environment variables or general settings; values will come only from the locked config loader (ADR-017, task 4.0).
2. Measure, over the point-in-time eligible universe and the **research + validation window only (2011 → 2022; holdout dates are sealed, ADR-017 §5)**, the distributions of price and of 20-session median daily traded value, per year and per capital level.
3. Document the methodology and the measured distributions in `docs/data/liquidity-thresholds.md`. No strategy code runs during this step.
4. The **form of the rule is pre-registered now, before any real data is seen** (owner decision; proposal):
   - `min_median_traded_value` = the 5th percentile of member-day 20-session median traded value
   - `min_price` = the 1st percentile of member-day close
   - `max_participation` and `order_liquidity_fraction` chosen so the largest order at the ₹1Cr capital level is ≤ the stated fraction for ≥ 95% of member-days

   Only the **numbers** come from the measurement; the rule does not change after the data is seen.
5. Lock the values (ADR-017) **before Phase 6 produces any result**, and in any case before Gate A.

Rules for all values:
1. Every value is locked **before Phase 6** via ADR-017, with hashes of this file and `configs/locked/risk-limits.v<N>.toml`.
2. After lock, any change needs a superseding ADR with **non-return justification** (liquidity data, operational incidents, cost-model change). It counts as a new trial and invalidates affected Gate A verdicts.
3. No sensitivity analysis of risk limits is ever used to choose risk limits.

### 3. Trading controls: independent flags (replaces the single-state model)

Each track holds `TradingControls`, a set of **independent** flags. No flag clears another.

| Flag | Set by | Cleared by | Effect while set |
|---|---|---|---|
| `kill_switch_triggered` | **Automatic**: at mark-to-market, close-of-day equity ≤ 80% of peak equity. **Evaluated every day regardless of other flags** | `KILL_SWITCH_RESET` only (manual, reason required, **live track only**); re-bases peak equity to current equity (DESIGN choice, recorded) | All **buys** blocked (any source). Pending buys cancelled. **No automatic liquidation.** Sells allowed |
| `strategy_paused` | `PAUSE_STRATEGY` (live track only) | `RESUME_STRATEGY` | New **algorithm** orders blocked; pending algorithm orders cancelled. Manual orders and corporate-action exits allowed, subject to all other flags and limits |
| `symbol_paused[s]` | `PAUSE_SYMBOL` (live track only) | `RESUME_SYMBOL` | New **algorithm** orders in *s* blocked. **Which other orders are allowed is OPEN** (proposal: `MANUAL_CLOSE`, corporate-action forced exits and stuck-position re-issues allowed). **Not part of the locked scope** until the owner decides |
| `emergency_paused` | `EMERGENCY_PAUSE` (manual, any time) | `EMERGENCY_RESUME` (manual, reason required) | **All paper trading activity stops on both tracks**: no order creation, no fills, all pending orders cancelled (owner wording, locked) |
| `data_halt` | **Automatic**: data-quality failure for the processing date | Automatic when the date's data validates | Both tracks: no processing for that date (catch-up later, ADR-009) |

**Effective permission** for an order = no hard-limit violation **and** no applicable blocking flag. Precedence:
`emergency_paused` > `data_halt` > `kill_switch_triggered` (buys) > `strategy_paused` / `symbol_paused` (algorithm orders) > limits.

**Emergency pause scope (locked by the owner: "stops all paper trading activity"):**
- It halts **both** tracks. It is a system halt, not a strategy intervention: the algorithm track receives no trade-level manual input,
  but it is stopped.
- **Consequence, disclosed:** paused sessions are a gap in algorithm-track evidence. Each emergency-pause episode is recorded as an
  **operational incident** and counts under Gate B B7. Orders older than one session expire at resume (ADR-003), and the
  Gate B duration minimums (B1) exclude paused sessions.
- An earlier draft kept the algorithm track running during an emergency pause. That was **rejected** because it contradicts the owner's wording.

**Kill switch on the algorithm track:** there is no reset on the algorithm track. A trigger there fails Gate B (B4) and ends the
Gate B attempt for that configuration. This is intended: a live account would have required human intervention.

**Liquidate-all:** not a kill-switch behaviour. A future `MANUAL_LIQUIDATE_ALL` would be a separate, explicit manual intervention (confirmation + reason), creating sells that pass through `risk`. **Not implemented in V1** unless separately approved.

**Backtests and the algorithm track** have no manual flags and no reset. A kill-switch trigger freezes buys for the rest of that run (see ADR-013 A18 decision).

### 4. Rationale for FREEZE_NEW_BUYS (owner-adopted)
- It avoids forced selling at the lows of a V-shaped crash, and round-trip costs on the whole book.
- Unsafe-to-hold situations (implementation or data failure) are covered by the emergency pause and the automatic data halt.
- Accepted trade-off: drawdown can exceed 20% while positions await strategy exits. Whether A5's 25% cap then binds depends on the A18 decision (ADR-013).

### 5. Sizing
Volatility-scaled target weights capped by max stock weight, rounded down to whole shares; rounding-to-zero recorded (ADR-004).
Sizing parameters are strategy/portfolio-construction settings chosen on the research period (ADR-005), not risk limits.

### 6. Stuck positions and terminal events
- Unfillable sells are re-issued each session, remain in exposure, and raise an alert.
- If a held security stops trading before it can be exited, the ADR-007 **terminal-event rule** applies.

## Alternatives Considered
- **LIQUIDATE_ALL kill switch:** rejected by owner. Remains available as a future explicit manual operation.
- **Single-state control model:** rejected after review. Pausing while frozen could clear the freeze without a reset.
- **Soft limits; risk inside the strategy; tuning limits for best backtest:** rejected.

## Consequences
- Hard invariants (no leverage, no shorting, cash) are implemented in Phase 4. Flags and the full engine come in Phase 7.
- At ₹5L the 10% cap (₹50,000) makes some high-priced stocks unholdable. This is reported, not tuned away.
