# ADR-005: First baseline: cross-sectional momentum with a market-trend filter (a research hypothesis)

## Status
Accepted (owner, 2026-09-30)

## Date
2026-09-30

## Context
- We need one systematic, interpretable baseline, independent of Laya and Claude, to establish
  a Gate A result and to serve as the control in ablations.
- Daily EOD data, next-open fills and Indian delivery costs (STT on both sides) penalise high turnover.
- Every variant tried is a trial (ADR-006); fewer, simpler variants mean less overfitting risk.

## Decision
1. **This is a research hypothesis, not an assumed profitable strategy.** The expected outcome
   is unknown; a Gate A failure is a valid, recorded result.
2. Baseline: **cross-sectional momentum** on the point-in-time Nifty 100 with a **market-trend
   filter** (reduce/stop new exposure when the benchmark is below a long moving average), rebalanced on a fixed schedule.
3. **Simple and interpretable:** few parameters (look-back, skip period, number of holdings,
   rebalance frequency, trend-filter window), each with a plain-language meaning. Every signal
   carries reason codes (rank, momentum value, trend-filter state).
4. **Parameter selection uses the research period only** (walk-forward inside 2011–2019), from a
   small grid declared before the search and recorded in the trial registry. Validation is used to
   check, not to select. **The holdout is never used for parameter selection** (ADR-006).
5. **Pluggable strategies:** strategies implement one domain protocol:

   ```python
   class Strategy(Protocol):
       name: str
       def generate(self, features: FeatureSet, as_of: TradingDate) -> Sequence[Signal]: ...
   ```

   Strategies are selected by name in configuration. The backtesting engine, evaluation harness
   and paper runner depend only on this protocol, so additional strategies are added and
   evaluated **without changing the engine**.
6. Strategies are pure domain code: no imports of Laya, Claude, HTTP clients, database drivers,
   UI, market-data providers, or dataframe libraries (CONSTRAINTS DC1–DC3).
7. Non-strategy baselines are always run alongside (ADR-006).

## Alternatives Considered
- **Short-term mean reversion:** high turnover; costs and fill realism dominate on EOD data.
- **Per-stock time-series trend:** in long-only cash equities often behaves like noisy index exposure.
- **Fundamental factors:** free point-in-time fundamentals are not in scope.
- **ML ranking models:** more trials and overfitting surface; harder to audit. Rejected for the first baseline.

## Rationale
Momentum with a trend filter needs price data only, has few parameters, and is easy to explain decision by decision.

## Consequences
- If it fails Gate A, any different strategy is a new, separately registered research effort,
  not a tweak evaluated against the same holdout (ADR-006 one-shot rule).
- Momentum is vulnerable to sharp reversals; regime criteria (ADR-013) are meant to expose this.
