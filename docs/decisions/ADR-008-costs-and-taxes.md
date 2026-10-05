# ADR-008: Versioned, configurable cost model: provisional and UNVERIFIED until broker data is provided

## Status
Accepted (owner, 2026-09-30) for structure. **All rate values are UNVERIFIED provisional research assumptions.**

## Date
2026-09-30

## Context
- The owner requires results that stay positive after brokerage, taxes, slippage and other realistic costs.
- No broker contract notes are available yet. Broker-specific charges must not be invented and treated as final.
- Statutory rates changed over 2011–2026; broker charges vary by broker and plan.

## Decision
1. **Cost model = versioned configuration**, identified by `cost_model_id` (e.g. `cm-0.1-provisional`)
   plus content hash. Every backtest, evaluation and paper report states the exact `cost_model_id` and
   hash used, and whether it is `UNVERIFIED` or `VERIFIED`.
2. **Components** (each configurable, each reported separately in decision records and cost-drag reports):
   brokerage · STT · exchange transaction charges · GST · SEBI charges · stamp duty · DP charges · slippage (ADR-003).
3. **Each component entry records:** basis (bps of value, fixed ₹ per order, fixed ₹ per scrip per sell day),
   side(s) it applies to, what GST applies to, effective-from date, source reference, and status (`UNVERIFIED`/`VERIFIED`).
4. **Provisional assumptions (`cm-0.1-provisional`, research only, all UNVERIFIED):**

   | Component | Provisional assumption | Why this assumption | To verify against |
   |---|---|---|---|
   | Brokerage | ₹20 per executed order (flat), both sides | Conservative relative to ₹0-delivery discount plans; penalises small orders | Owner's broker contract note |
   | STT | 0.1% of value, buy and sell (delivery) | Current statutory delivery rate as understood | CBDT / exchange circulars, by date |
   | Exchange transaction charges | NSE rate as currently understood (~0.003% of value) | Statutory; revised in 2024 | NSE circulars, by date |
   | SEBI charges | ₹10 per crore of value | Statutory as understood | SEBI circulars |
   | Stamp duty | 0.015% of value, buy side only (delivery) | Uniform national rate since 2020 as understood | Indian Stamp Act amendments; pre-2020 state rates differ |
   | GST | 18% on brokerage + exchange charges + SEBI charges (not on STT or stamp duty) | Statutory as understood | GST notifications |
   | DP charges | ₹15.93 per scrip per sell day (incl. GST) | Typical discount-broker/CDSL level | Owner's broker |
   | Slippage | base 10 bps + participation impact (ADR-003), adverse | Placeholder; open-auction slippage for retail orders unmeasured | Paper-trading diagnostics / intraday data later |

   **Simplification flagged:** `cm-0.1-provisional` applies today's understood rates to the whole 2011–2026 history.
   **This does not represent the historical period accurately.** Several components changed during the window
   (for example stamp duty was state-specific before 2020, exchange charges were restructured in 2024, and capital-gains
   tax rates changed in 2024), and the direction of the error differs by component and year.
   - Every report produced with `cm-0.1-provisional` carries the label **"costs: current-rate approximation, UNVERIFIED for history"**.
   - Historical rate versions (effective-from dates) are added only from verified primary sources (exchange/SEBI circulars, Finance Acts), each creating a new `cost_model_id`.
   - No result may be described as "historically cost-accurate" until every component used over the evaluated window is `VERIFIED`.
5. **Cost stress:** evaluation also runs at multiples of the provisional costs (ADR-013 A12) and reports the **break-even cost multiple**.
6. **Taxes:** reported as a separate, estimated **post-tax** series: FIFO lots; no loss carry-forward in V1 (simplification).
   Rate inputs verified 2026-09-30 against Budget memoranda and the Income-tax Act 2025 Gazette (see ADR-007 sources S5):

   | Item (listed equity, STT paid, resident individual) | Rule | Evidence |
   |---|---|---|
   | Long-term threshold | > 12 months holding | VERIFIED |
   | LTCG before 01.04.2018 | Exempt (s.10(38)) | VERIFIED |
   | LTCG 01.04.2018 → 22.07.2024 | 10% above ₹1 lakh (s.112A); cost grandfathered to FMV on 31.01.2018 | VERIFIED |
   | LTCG from 23.07.2024 | 12.5% above ₹1.25 lakh (ITA 2025 s.198 from 01.04.2026) | VERIFIED |
   | STCG before 23.07.2024 | 15% (s.111A) | VERIFIED |
   | STCG from 23.07.2024 | 20% (ITA 2025 s.196 from 01.04.2026) | VERIFIED |
   | Dividends before 01.04.2020 | Exempt for shareholder (DDT paid by company); s.115BBDA above ₹10 lakh | VERIFIED (115BBDA start year UNVERIFIED) |
   | Dividends from 01.04.2020 | Slab rate (owner input) | VERIFIED rule; slab **owner input** |
   | Dividend TDS | 10%; threshold ₹5,000 → ₹10,000 from 01.04.2025 (timing effect only) | VERIFIED |
   | Bonus lots, bonus stripping | See ADR-007 | VERIFIED rules; modelling choice open |
   | Surcharge, cess, rebates, basic-exemption interaction | **Not modelled in V1**; post-tax figures are labelled an approximation | Design |

   Tax outputs are estimation inputs to Gate A (A1), **not tax advice**.
7. **Gate A may not be locked as passed on UNVERIFIED costs** without the report showing the status prominently.
   Whether a final Gate A verdict requires VERIFIED costs is **open** (proposal: yes, before paper → real money; not required before paper trading).

## Alternatives Considered
- **Single flat bps cost:** hides fixed fees and rate changes.
- **₹0 brokerage assumption:** optimistic; rejected as the default provisional choice.
- **Ignore taxes:** rejected (owner requirement).

## Rationale
Explicit, versioned, status-tagged components prevent provisional numbers from quietly becoming "facts".

## Consequences
- Golden cost tests start from hand-computed cases on the provisional model; they are re-based on real contract notes when available (new `cost_model_id`).
- Every result carries its cost-model version, so results under different versions are never silently compared.
