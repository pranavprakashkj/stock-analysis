# ADR-016: Laya and Claude as optional augmentation layers

## Status
**LOCKED** (owner, 2026-09-30). Any augmentation must pass the predefined ablation/evaluation process (ADR-013 X-criteria, locked via ADR-017) before it can influence the production paper strategy.

## Date
2026-09-30

## Context
- The baseline strategy must work, and be evaluated, independently of any model.
- Laya (convaiinnovations/laya) is a text classifier returning probabilities for typed questions (model card, VERIFIED 2026-09-30).
- Claude is an LLM whose training data may cover the entire evaluation window.

## Decision
1. **Baseline independence:** the baseline strategy, risk engine and execution have no dependency on Laya or Claude (import contracts, CONSTRAINTS DC2).
2. **Laya** = optional structured signal/classification layer. **Claude** = optional qualitative/news/analysis layer.
   Both implement the application-layer `FeatureProducer` port and contribute only timestamped entries to `FeatureSet`.
3. **Neither can override:** strategy decisions, the risk engine, position limits, exposure limits, or execution constraints.
   Their outputs are inputs to a strategy variant. They are never commands. They have no access to order, risk or ledger interfaces.
4. **Admission:** an augmented variant enters the production paper strategy only with an "improves" verdict under ADR-013 X1–X6.
5. **Model identifiers are configuration.** Claude's model name, Laya's model repository and revision, prompts and
   parameters live in validated configuration. **No model id is hard-coded in business logic** (CONSTRAINTS DC12).
   Each call records model id, revision, prompt hash and output.
6. **Leakage:** historical Claude results over any period its training data may cover are **exploratory only**.
   Laya historical results may be treated as admissible only if the input is **judged unlikely** to carry outcome knowledge
   (e.g. price-derived states rather than news text). This is an **assumption, not a verified property**: a pretrained model could
   still encode period-specific associations. It also requires that fine-tuning/calibration respect the splits (research-only
   fine-tuning, validation-only calibration, never holdout). Whether a given Laya input qualifies is decided and recorded before the experiment.
   Forward evaluation uses shadow tracks during paper trading (ADR-014).
7. **Reproducibility:** in backtests a missing cached model output fails the run; it is never regenerated silently.
8. Claude-written explanations are labelled non-authoritative and stored separately from decision records.

## Alternatives Considered
- **Models as trade deciders:** rejected (owner).
- **Hard-coded model ids:** rejected. Model deprecation would force code changes and hide which model produced a result.

## Consequences
- Phases 9–10 build only adapters and experiment configurations; no domain module changes are expected.
- A text-based experiment needs a timestamped news source, which is not yet identified (open).
