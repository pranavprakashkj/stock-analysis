# ADR-004: Starting capital is configuration; evaluated at ₹5L, ₹25L, ₹1Cr; paper starts at ₹5L

## Status
Accepted (owner, 2026-09-30)

## Date
2026-09-30

## Context
- Capital changes results: integer-share rounding at small capital, flat per-order/per-day fees
  (larger % drag at small size), market impact at large size.
- The owner has not fixed live capital and wants it changeable without touching strategy logic.

## Decision
1. `starting_capital` is required configuration with no default in code; strategy code never reads it.
   Sizing uses it only through `risk`/portfolio construction.
2. Evaluation capital grid: **₹5,00,000 · ₹25,00,000 · ₹1,00,00,000**. Every evaluation reports metrics per level.
3. Gate A (ADR-013) is assessed per level; the report states the levels at which the strategy passes.
4. **Initial paper-trading capital: ₹5,00,000.**
5. Rounding-to-zero trades are recorded as `SKIPPED_ROUNDING`, never silently dropped.

## Alternatives Considered
- **Single assumed capital:** hides capital sensitivity.
- **Fractional shares / percent-only returns:** unrealistic for NSE cash equities.

## Rationale
Makes the future live-capital decision evidence-based.

## Consequences
- 3× evaluation runs; trivial at daily frequency.
- **Implication to note:** paper trading at ₹5L only meaningfully forward-tests the ₹5L result. If
  Gate A passes only at ₹25L/₹1Cr, paper at ₹5L would test a configuration that did not pass. The
  paper-start check must confirm Gate A passed **at the paper capital level**.
