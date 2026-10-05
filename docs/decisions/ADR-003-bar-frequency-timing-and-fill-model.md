# ADR-003: Daily bars; T-close signal, T+1 official open reference, separately modelled slippage

## Status
Accepted (owner, 2026-09-30). Slippage parameter values are UNVERIFIED research assumptions (ADR-008).

## Date
2026-09-30

## Context
- Free data is end-of-day (ADR-001).
- The same timing model applies to backtest and paper.
- NSE's official open comes from the pre-open call auction; a retail order entered later will
  not necessarily trade at that price, so slippage must be modelled explicitly and adversely.

## Decision
### Three prices, kept distinct in types and records
| Term | Definition | Used for |
|---|---|---|
| **Signal price** | T close (and any data up to and including T close) | Features, signals, target weights, sizing estimates |
| **Reference execution price** | T+1 **official open** | The benchmark price the simulated order is executed against |
| **Simulated fill price** | Reference execution price adjusted by the slippage model, always **adverse** (buys higher, sells lower) | Ledger, P&L, costs |

Each decision record stores all three, plus the slippage component separately, so slippage is
reported as its own cost line.

### Rules
1. Bar frequency: daily.
2. Signals use information available at T close only. **Earliest execution is T+1.**
3. The execution simulator receives only the T+1 **open** and data known *before* T+1's open
   (e.g. T and earlier volume for participation estimates). It must not see T+1 high, low, close,
   volume or anything later. This is enforced by the type it receives (an `OpenAuctionQuote`, not a `Bar`) and by a look-ahead test.
4. Slippage model (V1): `simulated_fill = reference × (1 ± (base_bps + impact_bps(participation)))`,
   `participation = order_value / (k × ADV_value_up_to_T)`; parameters are config, versioned with the cost model (ADR-008), UNVERIFIED, and stress-tested.
5. Orders are valid for one session; unfilled orders expire and are recorded.
6. Fill-time checks (using only the T+1 open): cash after same-open sells, gap-at-open resizing so risk limits hold at the fill price, tradability (no quote → no fill).
7. **Price bands:** because rule 3 forbids using T+1's high/low, V1 cannot detect "locked at band" at the open. V1 therefore fills any order with a valid open quote. **Known limitation**: fills on band-locked opens are optimistic. Revisit with a data source providing band/auction status.

## Alternatives Considered
- **Fill at T close:** rejected (look-ahead).
- **Fill at T+1 VWAP (turnover/volume):** uses data after the execution point. Rejected as primary; may be reported as a *diagnostic* only, never used for fills.
- **Intraday bars:** no free source at depth; revisit with a paid/broker adapter.

## Rationale
The T+1 open is the earliest honest price on EOD data; making slippage a separate, adverse, stress-tested component keeps its uncertainty visible instead of folded into the fill.

## Consequences
- Paper trading on EOD data validates process, reproducibility and operations. **It cannot
  independently measure execution quality**, because the reference and the fill both derive from the same open.
  Gate B's fill-error criterion (ADR-013 B5) therefore needs an independent price source, or must be
  explicitly marked "not measurable"; **open**.
- Band-locked open fills are a documented optimistic bias (rule 7).
