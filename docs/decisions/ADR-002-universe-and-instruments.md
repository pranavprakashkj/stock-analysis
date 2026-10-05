# ADR-002: Point-in-time Nifty 100, NSE cash equities, delivery, long-only

## Status
Accepted (owner, 2026-09-30). Reconciliation tolerance open until measured in Phase 1.

## Date
2026-09-30

## Context
- Using today's constituents for historical tests is survivorship bias.
- Free data has no ready-made historical constituent list (ADR-001).
- Impact and slippage assumptions are only credible for liquid stocks.

## Decision
1. **Universe:** Nifty 100, point-in-time. A stock is eligible for *new purchases* on D only if it
   was an index member on D. Membership switches on the **effective date**, not the announcement date.
2. **Membership history:** a curated, versioned file in `reference/`, rebuilt from NSE Indices
   reconstitution announcements, with a source reference per change.
3. **Instruments:** NSE EQ series only; stocks moved to BE/BZ/trade-for-trade (and, where data
   allows, surveillance-flagged) are ineligible for new buys.
4. **Orders:** cash delivery, long-only, no leverage, no F&O, no intraday.
5. **Index removal policy (owner decision):** if a held stock leaves the Nifty 100:
   - the existing position is **kept**;
   - **new purchases are blocked** (including top-ups and rebalancing increases);
   - the strategy may still generate an **exit**, processed normally;
   - there is **no forced exit solely because of index removal**.
   The position stays in all risk calculations; its exit reason is whatever the strategy says,
   and the decision record notes `NOT_IN_UNIVERSE` status.
   *Distinct from* ADR-007's unsupported-corporate-action exit (e.g. delisting), which is forced for ledger-correctness reasons.
6. **Validation:** rebuild a Nifty 100 proxy from the membership file and prices and compare
   with published index levels; tolerance set after measuring (Phase 1, **open**).

## Alternatives Considered
- **Nifty 50:** less reconstruction effort but narrow breadth for ranking.
- **Nifty 200/500:** broader, but more reconstruction effort and less credible fills on EOD data.
- **Force-sell on removal:** rejected by owner; forced index-event selling is a known cost drag and not part of the strategy.
- **Static current list:** rejected (survivorship bias).

## Rationale
Nifty 100 balances breadth, liquidity and reconstruction effort; point-in-time membership is non-negotiable.

## Consequences
- Held non-members can linger if the strategy's exit rule depends on ranks within the universe;
  the strategy spec (Phase 5) must define how held non-members are scored for exit.
  Tracked as a strategy-design item, not a new policy.
- Benchmark is Nifty 100 TRI (ADR-006); free TRI source to be confirmed in Phase 1.
