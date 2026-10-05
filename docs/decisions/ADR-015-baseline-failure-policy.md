# ADR-015: What happens if the baseline fails Gate A

## Status
**LOCKED** (owner, 2026-09-30)

## Date
2026-09-30

## Context
- The baseline (ADR-005) is a research hypothesis. Failing Gate A is a plausible and informative outcome.
- The main risk after a failure is rescuing the result: loosening thresholds, adding components until it passes, or re-testing tweaks on the spent holdout.

## Decision
If the baseline fails Gate A:
1. **The failed baseline is not paper traded**, neither fully nor partially, nor on a shadow track presented as a candidate.
2. **Infrastructure and evaluation framework are preserved**: data pipeline, engine, risk, evaluation harness, trial registry and reports remain as built.
3. **A new strategy hypothesis is researched and tested** as a separately registered effort (new ADR, new trial-registry entries). A tweak of the failed baseline evaluated on the same holdout is labelled `holdout-contaminated` (ADR-006). **Every** configuration evaluated on the holdout, including new hypotheses, increments the holdout-use count *h*, which deflates A11b and is capped (ADR-013 §Holdout reuse).
4. **Gate A thresholds are not loosened** to rescue the strategy (ADR-013 general rule 6; ADR-017 change procedure).
5. **The failed strategy is recorded as a valid research result**: its Gate A report, trial-registry entries and holdout-use entry are kept, not deleted or re-labelled as an error.
6. **Neither Laya nor Claude is added to rescue it.** An augmented variant must pass the ablation criteria **and** Gate A on its own merits (ADR-013 X6), and must be designed from research/validation evidence only.

## Alternatives Considered
- **Paper-trade anyway "to learn":** would produce evidence about a strategy already known to fail its criteria; rejected. (Operational testing of the paper runner itself may use a clearly labelled non-candidate configuration if the owner approves separately.)
- **Loosen thresholds:** defeats pre-registration.

## Rationale
It keeps a failure a failure, and protects the credibility of any later pass.

## Consequences
- A failed holdout is spent for that configuration. Future hypotheses carry the disclosed risk that the holdout period is known (ADR-006 human look-ahead); forward paper trading remains the final arbiter.
