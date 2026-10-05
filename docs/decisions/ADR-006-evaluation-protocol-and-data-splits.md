# ADR-006: Evaluation protocol: chronological splits, sealed holdout, trial registry, ablations

## Status
Accepted (owner, 2026-09-30) for splits and rules. Thresholds are in ADR-013 (draft, not locked).
Data feasibility for these dates is verified in Phase 1.

## Date
2026-09-30

## Context
- The owner requires criteria and procedures defined and locked before evaluating the final strategy.
- One market history + many variants = data-snooping risk.

## Decision
### Splits (owner decision)
| Period | Dates | Use |
|---|---|---|
| Warm-up | before 2011-01-01 (length = longest feature look-back) | Look-back only; never scored |
| Research | 2011-01-01 → 2019-12-31 | Design, parameter selection (walk-forward) |
| Validation | 2020-01-01 → 2022-12-31 | Out-of-sample check during development; **not** for parameter selection |
| Sealed holdout | 2023-01-01 → 2026-06-30 | One final Gate A evaluation per strategy configuration |
| Forward paper | Starts only **after** a strategy passes locked Gate A | True out-of-sample |

**If free data cannot reliably support these dates** (coverage gaps, membership history unavailable
for early years, benchmark TRI missing), the limitation is **flagged in the Phase 1 data-quality
report and brought to the owner**. Dates are not silently changed.

### Rules
1. **Walk-forward** inside research with an embargo between fit and test windows of at least one rebalance period plus the longest label horizon.
2. **The holdout is sealed.** It is readable only via `evaluate --split holdout`, which requires
   a locked ADR-013 hash, and logs who ran it, when, and the strategy config hash. **The holdout
   is never used for parameter selection, feature selection, or strategy design.**
3. **One shot per configuration.** A configuration evaluated on the holdout is final. A revised
   configuration is labelled `holdout-contaminated` (forward paper trading becomes its only valid
   out-of-sample test) or waits for new data.
4. **Trial registry:** every run on any split is recorded (config hash, split, results); counts feed ADR-013's deflated Sharpe.
5. **Baselines** in every report: Nifty 100 TRI; point-in-time equal-weight universe; random entry at matched turnover and costs.
6. **Pre-registration:** ADR-013 is locked and its hash recorded before any holdout run or ablation verdict.
7. **Failure is reported, not optimised away.** There is no automated tuning loop over validation or holdout.

### Ablations (owner decision)
Variants, all on identical dates, universe, capital grid, costs, risk limits and criteria:

| Variant | Description |
|---|---|
| B | Baseline |
| B+L | Baseline + Laya features |
| B+C | Baseline + Claude features |
| B+L+C | Baseline + both |

- The baseline establishes its own Gate A result first.
- Augmented variants are designed and frozen using **research and validation only**, then each
  receives one holdout evaluation (rule 3).
- A component is admitted to the production paper strategy **only** if its improvement meets the
  locked methodology (ADR-013 X-criteria).
- **Constraints that limit historical ablations** (see Consequences): model-knowledge contamination and news-data availability.

## Alternatives Considered
- **Random K-fold:** leaks future into past.
- **Walk-forward only, no holdout:** walk-forward results get iterated on; a sealed holdout is the only defence.
- **Longer history (2000s):** more regimes, more reconstruction effort; revisit if power analysis requires.

## Rationale
Chronological splits plus a one-shot, access-logged holdout make "no goalpost moving" mechanical.

## Consequences
- **Human look-ahead** cannot be eliminated: the owner and Claude broadly know how markets behaved in
  2023–2026. Mitigation: configurations and criteria are frozen before holdout runs; forward paper is the final arbiter.
- **Disclosed sequencing risk:** augmented variants are designed after the baseline's holdout result
  is known. Knowing the baseline's holdout behaviour can influence augmentation design. Mitigation:
  augmented configurations are frozen from research/validation evidence, and the report discloses the ordering.
- **Claude contamination:** Claude's training data covers the entire 2011–2026 window. A Claude
  news/qualitative feature evaluated historically may encode knowledge of outcomes. Historical B+C
  and B+L+C results are therefore **exploratory and labelled contaminated**, and cannot alone admit
  Claude (**open decision** on the forward admission test; see ADR-013 X4).
- **Laya contamination** depends on the input: price-derived text states are low-risk; news text over periods covered by the base model's pretraining is contaminated in the same way.
- **News data:** any text-based feature needs a free, timestamped historical news source; none is identified yet (**open**).
- Holdout ~3.5 years gives limited statistical power (quantified in ADR-013).
