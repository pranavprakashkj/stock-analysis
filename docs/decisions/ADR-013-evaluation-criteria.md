# ADR-013: Evaluation criteria: Gate A (Backtest → Paper), Gate B (Paper → Real money), ablations

## Status
- **LOCKED policy (owner, 2026-09-30):**
  - Gate B B5 NOT ASSESSED, so Gate B is INCOMPLETE for execution realism and V1 evidence cannot authorise real money.
  - Diagnostics are never described as proof of execution quality.
  - Holdout reuse is limited to 3 uses per window, enforced (§Holdout reuse, ADR-017).
- **Numeric criteria: Proposed, NOT LOCKED.** They are locked via ADR-017 before Phase 6 produces any result.
- Thresholds are **never** chosen or adjusted using backtest results.

## Date
2026-09-30

## Classification
- **STATISTICAL:** the criterion controls a stated error rate under a stated model. The chosen level (e.g. 0.90) is still a judgement about error trade-offs.
- **DESIGN:** a judgement about acceptable behaviour. No test justifies the exact number.
- **OPERATIONAL:** a requirement about correctness, data integrity, reporting or operations. Pass/fail.

## Methodological fixes in this revision
1. **Lock timing:** ADR-012 values (all of them, including liquidity limits) and ADR-013 are locked **before Phase 6 produces any result**. The harness checks the lock on **every** evaluation run, not only holdout runs (§Locking).
2. **PSR:** Bailey & López de Prado probabilistic Sharpe ratio on **daily** excess returns, with sample skewness and kurtosis.
3. **Power table corrected:** the previous table applied the SR²/2 term at annual frequency, which overstated the standard error. With daily observations the term is negligible, so `SE(annual SR) ≈ 1/√T` (i.i.d.). Fat tails and negative skew make the true SE larger; the PSR formula accounts for this.
4. **Drawdown basis:** daily net-of-costs, pre-tax equity. Tax affects the profitability criteria only.
5. **Time underwater:** longest span from an equity peak until it is regained; an unrecovered spell at period end counts at its length so far.
6. **Bootstrap:** stationary block bootstrap, mean block length 20 sessions, 10,000 resamples (DESIGN).
7. **Regime labels are point-in-time:** the volatility median is an **expanding** median using data up to each date. (A full-history median would include the holdout, which is look-ahead in the labels.)
8. **Evaluation periods per criterion are explicit** (table column "Period").
9. **Multiplicity with staged decisions:** see X1.
10. **Holdout reuse is controlled** (A11b, §Holdout reuse).

## Power reality check (i.i.d. approximation `SE ≈ 1/√T`, indicative only)
| Sample | Years | Observed SR needed, 90% | Observed SR needed, 95% |
|---|---|---|---|
| Holdout | 3.5 | ≈ 0.69 | ≈ 0.88 |
| Research walk-forward OOS | 6 | ≈ 0.52 | ≈ 0.67 |
| Paper | 1 | ≈ 1.28 | ≈ 1.65 |

Probability of passing A11b alone, for true SR 0.5 / 0.7 / 1.0 / 1.3: **36% / 51% / 72% / 87%** at 0.90, versus 24% / 37% / 59% / 78% at 0.95.
One year of paper trading needs an observed SR ≈ 1.3 for 90% confidence, so **Gate B is operational and consistency validation, not proof of edge**.

## General rules
1. All criteria in a gate must pass; no composite score.
2. Returns are net of all costs and slippage; profitability uses estimated post-tax returns (ADR-008).
3. Gate A is assessed per capital level; paper requires a pass at ₹5L.
4. Excess returns use the 91-day T-bill series (source per the access review).
5. Reports list failed criteria first, with value, threshold and margin; they state the cost-model version and its VERIFIED/UNVERIFIED status.
6. **No threshold may be changed after any evaluation output exists**, except by a superseding ADR that declares the change post hoc; affected results are labelled.

## Gate A: Backtest → Paper trading

| ID | Criterion | Threshold | Period | Class | Rationale |
|---|---|---|---|---|---|
| A1 | Post-tax net CAGR | > T-bill return | Holdout | DESIGN | Must beat the risk-free alternative after costs and tax |
| A2 | Net Sharpe vs Nifty 100 TRI | Strategy > benchmark | Holdout | DESIGN | Relative anchor; point estimate |
| A3 | Net Sharpe vs equal-weight point-in-time universe | Strategy > equal-weight | Holdout | DESIGN | Edge must come from selection |
| A4 | vs random entry (≥ 1,000 seeds; same rebalance dates, holdings count, weighting, costs, eligible universe) | > 95th percentile | Holdout | **STATISTICAL** | One-sided p < 0.05 against "no selection skill"; same-period test |
| A5 | Max drawdown | ≤ Nifty 100 TRI max DD over the same period **and** ≤ **25%** | Holdout **and** full 2011 → Jun 2026 | DESIGN | Risk tolerance; checking all periods creates no selection leak |
| A6 | Max time underwater | ≤ **24 months** | Holdout and full history | DESIGN | Long underwater spells cause abandonment |
| A7 | Regime behaviour (benchmark vs 200-day MA; 60-day vol vs expanding median) | Net return > 0 in up-trend; DD < benchmark DD in down-trend | Full history | DESIGN | Long-only should lose less in bear markets |
| A8 | Walk-forward folds (3-year expanding initial window; annual folds 2014–2019) | ≥ 4 of 6 positive net excess return; binomial p reported | Research | DESIGN | Rejects results driven by one or two years; not evidence of edge |
| A9 | P&L concentration | No calendar year > 50% of net P&L; top 5 trades < 25% | Holdout | DESIGN | Guards against one-event results |
| A10 | Activity | ≥ 100 closed round trips **and** ≥ 30 rebalances | Holdout | DESIGN | Floor against a handful of bets; implies rebalancing at least ~monthly |
| A11a | Deflated Sharpe (trial count from registry) | ≥ 0.95 | Research walk-forward OOS | **STATISTICAL** | Corrects for selection where selection happened |
| A11b | PSR on holdout, **deflated for holdout reuse** (§Holdout reuse) | ≥ **0.90** | Holdout | **STATISTICAL** | See power table |
| A12 | Break-even cost multiple (fees and slippage together) | ≥ 2.0 | Holdout | DESIGN | Costs UNVERIFIED; open-auction slippage unmeasured |
| A13 | Parameter neighbourhood (adjacent pre-declared grid values; ±20% for continuous) | All neighbours net Sharpe > 0; median ≥ 50% of base | Research walk-forward OOS **and** validation (**not** holdout, so non-candidate configurations never touch it) | DESIGN | Rejects sharp optima |
| A14 | Start-date jitter (first 20 holdout sessions) | All satisfy A1 | Holdout (same configuration) | DESIGN | Removes lucky starts |
| A15 | Intended orders filled | ≥ 95%; unfilled by reason reported; any fill over the participation cap = invariant violation | Holdout | DESIGN | Fills are optimistic by construction (ADR-003) |
| A16 | Cost-model golden tests | Pass | n/a | OPERATIONAL | |
| A17 | Look-ahead and determinism suites | Pass | n/a | OPERATIONAL | |
| A18 | Kill-switch behaviour (**owner decision; see note**) | Proposed: trigger is reported; A5/A6 are measured on the actual (frozen) path | Holdout and full history | DESIGN | |
| A19 | No unresolved data-quality failures, including **zero missing member-days** (ADR-001 plan 4). **Cannot be waived** by a recorded acceptance | Required | All evaluated periods | OPERATIONAL | Results on incomplete data are not evidence |

**A18 note (owner decision):** in backtests there is no manual reset, so a kill-switch trigger freezes buys for the rest of the run. Options:
- **(a) Trigger fails Gate A.** Because the switch fires at 20% drawdown, the effective drawdown limit becomes 20% and the owner-specified 25% cap in A5 rarely binds.
- **(b) Proposed:** the trigger is reported, and A5/A6 judge the actual frozen path, including post-trigger overshoot. This keeps the 25% cap meaningful and is conservative on returns (frozen capital).

## Holdout reuse (LOCKED, owner 2026-09-30; mechanism in ADR-017)
- Every distinct configuration tested on a holdout window counts as one use. **Maximum 3 uses per window.** After 3, a new window is required.
- The count is kept in a hash-chained, append-only ledger. There is no reset path; exceeding the limit is **rejected** by the harness; the ledger entry is persisted with the run's artifacts.
- A11b uses the Sharpe threshold deflated for *h* = number of uses of that window **up to and including this run**. For *h* = 1 it equals the PSR.
  Earlier verdicts are not re-judged; every report shows its own *h* and the window's current total.
- What counts as one use, write-ahead recording, sealing and window rules: ADR-017 §5–6. The limit is per window, across all strategies.
- **Ablation budget conflict (owner decision):** baseline (1 use) + three augmented variants (3 uses) = 4 > 3. Options:
  - **(a)** Register the ablation family (B+L, B+C, B+L+C) as **one pre-registered use** evaluated jointly, with Holm across the family, and X6 applied to the family's winner only.
  - **(b)** Evaluate only B+L on the holdout (Claude variants are forward-only anyway, per X4), using 2 of 3 uses.
  - **(c)** Wait for a new window for augmentations.

  Proposal: **(b)**, because historical Claude results are exploratory and any holdout read is a use (ADR-017 §6).

## Gate B: Paper → Real money (algorithm track only; interventions reported separately)

Verdicts: `PASS` / `FAIL` / `INCOMPLETE`. **In V1 the best achievable verdict is `INCOMPLETE`** (B5).
**Gate B cannot authorise real-money trading on V1 evidence alone.**

| ID | Criterion | Threshold | Class | Rationale |
|---|---|---|---|---|
| B1 | Duration | ≥ **12 months** **and** ≥ **12 rebalances** **and** ≥ **50 closed round trips**, whichever takes longest | OPERATIONAL | Full annual cycle of operational events; every order path exercised |
| B2 | Replay | 100% of algorithm-track decisions reproduced by backtest replay | OPERATIONAL | |
| B3 | Paper net return within the 5th–95th percentile of block-bootstrapped backtest returns for the same horizon | Required | STATISTICAL (low power) | Detects gross divergence only |
| B4 | Drawdown | ≤ Nifty 100 TRI DD over the same period **and** ≤ 25% (same as A5); kill-switch trigger reported as in A18 | DESIGN | Same tolerance as research |
| B5 | Fill-model error vs an independent reference | **NOT ASSESSED in V1** | OPERATIONAL | No independent reference in free daily data |
| B6 | Turnover within ±50% of backtest expectation; zero unexplained replay differences | Required | DESIGN | |
| B7 | Zero unrecovered missed sessions; zero unresolved data-quality incidents; zero risk-limit bypasses | Required | OPERATIONAL | |
| B8 | Cost model VERIFIED against the owner's broker charges | Required | OPERATIONAL | ADR-008 |

**Execution-realism diagnostics (always reported; never presented as proof of execution quality):** break-even cost multiple;
slippage as a percentage of gross returns; T+1 open vs T+1 daily average price (turnover ÷ volume) dispersion. The last uses post-execution data, so it is diagnostic only.

## Ablations (B, B+L, B+C, B+L+C)

| ID | Criterion | Threshold | Class | Rationale |
|---|---|---|---|---|
| X1 | Paired improvement: difference in annualised Sharpe of daily net excess returns (variant − baseline), same dates; stationary block bootstrap; one-sided p = share of bootstrap differences ≤ 0 | Family-wise α = 0.05 across the 3 variants: **Holm** when all three p-values are decided together; a variant decided **alone and earlier** uses the Bonferroni bound **α/3 ≈ 0.0167** (which equals Holm's first step, so family-wise error stays ≤ 5% under staging) | **STATISTICAL** | The contract's "Holm across 3 variants", made valid when decisions happen at different times (B+L historically; Claude variants forward) |
| X2 | No risk degradation | Max DD not worse by > 2 pp; A5 still met | DESIGN | |
| X3 | Power disclosure: minimum detectable effect recorded before running | Required | OPERATIONAL (reporting) | An underpowered test yields "inconclusive" |
| X4 | Any model-derived feature evaluated over a period the model may have seen in training is exploratory only; admission needs a forward test | Required | OPERATIONAL (integrity) | Training-data knowledge is look-ahead |
| X6 | Admitted variant must itself pass Gate A | Required | DESIGN | ADR-015 |

Verdicts: **improves** / **no improvement** / **inconclusive**. **Expected consequence:** 12-month forward shadow tests for Claude variants are
badly underpowered, so "inconclusive" is the likely V1 outcome, and Claude is then not admitted.

## Summary of classes
- **STATISTICAL:** A4, A11a, A11b, B3, X1
- **DESIGN:** A1, A2, A3, A5, A6, A7, A8, A9, A10, A12, A13, A14, A15, A18, B4, B6, X2, X6
- **OPERATIONAL:** A16, A17, A19, B1, B2, B5, B7, B8, X3, X4

## Locking
The mechanism is [ADR-017](ADR-017-threshold-lock-and-holdout-ledger.md), summarised here:
- versioned immutable config files (`configs/locked/evaluation-criteria.v<N>.toml`, `risk-limits.v<N>.toml`)
- a lock registry with hashes of configs and ADRs
- a harness pre-flight that **refuses every evaluation run** without a valid lock
- run manifests that record versions and hashes
- an immutability test that fails the build if a locked file changes
- a new ADR, a new config version and a new protocol for any change

Lock happens **before Phase 6 produces any result**.

## Consequences
- The most likely first outcome is that the baseline fails at least one criterion (ADR-015).
