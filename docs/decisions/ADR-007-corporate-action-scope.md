# ADR-007: Corporate-action handling for V1

## Status
Proposed, revised 2026-09-30 after source verification. **Owner review required.** Every rule is classified:

- **VERIFIED:** rests on a primary source read on 2026-09-30 (cited). Secondary-only support is marked "VERIFIED (secondary)".
- **PROVISIONAL:** a working default, partly grounded, kept as a config value and labelled UNVERIFIED in outputs.
- **NEEDS SOURCE:** the rule depends on a fact we have not verified.
- **NEEDS DESIGN DECISION:** a modelling choice the owner must approve. No fact decides it.

This ADR does not invent legal or tax rules. Tax rules here are **estimation inputs** for the post-tax report (ADR-008), not advice.

## Date
2026-09-30

## Key sources (read 2026-09-30)
- S1 SEBI LODR Regulations 2015, amended to 22.01.2026, Reg 42: https://www.sebi.gov.in/legal/regulations/jan-2026/securities-and-exchange-board-of-india-listing-obligations-and-disclosure-requirements-regulations-2015-last-amended-on-january-22-2026-_99375.html
- S2 SEBI T+1 circular, 7 Sep 2021: https://www.sebi.gov.in/legal/circulars/sep-2021/introduction-of-t-1-rolling-settlement-on-an-optional-basis_52462.html
- S3 SEBI bonus T+2 trading circular, 16 Sep 2024: https://www.sebi.gov.in/legal/circulars/sep-2024/enabling-t-2-trading-of-bonus-shares-where-t-is-the-record-date_86714.html
- S4 SEBI ICDR Regulations 2018 (Reg 295), amended to 21.03.2026: https://www.sebi.gov.in/legal/regulations/mar-2026/securities-and-exchange-board-of-india-issue-of-capital-and-disclosure-requirements-regulations-2018-last-amended-on-march-21-2026-_100581.html
- S5 Budget memoranda 2018, 2020, 2022, Jul 2024, 2025 (indiabudget.gov.in); Income-tax Act 2025 Gazette: https://egazette.gov.in/WriteReadData/2025/265620.pdf
- S6 SEBI rights-issue circular, 22 Jan 2020: https://www.sebi.gov.in/legal/circulars/jan-2020/streamlining-the-process-of-rights-issue_45753.html
- S7 SEBI Delisting Regulations 2021, amended to 03.09.2025: https://www.sebi.gov.in/legal/regulations/sep-2025/securities-and-exchange-board-of-india-delisting-of-equity-shares-regulations-2021-last-amended-on-september-3-2025-_96548.html

## Common rules

| # | Rule | Class | Basis / note |
|---|---|---|---|
| C1 | Use the **exchange-published ex-date field**; never derive ex-date from record date | NEEDS DESIGN DECISION (proposed) | Supporting facts: T+1/T+2 settlement cycles VERIFIED (S2); ex-date/record-date divergence around settlement holidays VERIFIED (secondary only, Sep 2025) |
| C2 | Entitlement = holdings at the close of the session before the ex-date (E−1) | VERIFIED (secondary) | Standard ex-date meaning; buying on/after ex-date carries no entitlement |
| C3 | **Knowledge time = announcement date** when the data provides one | NEEDS SOURCE | Whether NSE's corporate-action records carry an announcement/board-outcome date is **UNVERIFIED**; it may live only in separate announcement feeds |
| C4 | **Fallback knowledge time when no announcement date** (revised) | PROVISIONAL (post-Dec-2015) · NEEDS SOURCE (pre-Dec-2015) | See the table below. The earlier fixed "E − 5 sessions" is **withdrawn**: since 13.12.2024 the minimum notice is 3 working days (S1), so E − 5 could assume knowledge before a minimum-notice announcement (look-ahead) |
| C5 | Feature adjustment is point-in-time (only actions with ex-date ≤ D); fills, valuation and the ledger use unadjusted prices | NEEDS DESIGN DECISION (proposed) | Look-ahead control; design |
| C6 | Orders store target value; an order filling on an ex-date is re-derived at the ex-date open and re-checked by risk; unsupported action → cancel | NEEDS DESIGN DECISION (proposed) | Design |
| C7 | Split/bonus ratio vs overnight price-move check (±20% tolerance); > 40% move with no action → flag | PROVISIONAL | Tolerances are judgement values |

**C4 fallback: assume the latest announcement the minimum-notice rule allows, plus one session for after-hours announcements.**
The intimation day *I* must leave ≥ *n* working days before the record date *R*, excluding *I* and *R*, so *I* ≤ *R* − (*n* + 1).
An announcement made after market hours on *I* is usable only at the close of *I* + 1.

| Period | Minimum notice *n* (S1) | Fallback: usable at close of | Class |
|---|---|---|---|
| From 13.12.2024 | 3 working days (general); 7 for Reg 37 schemes | *R* − 3 sessions (schemes: *R* − 7) | Rule text VERIFIED (S1); fallback PROVISIONAL |
| Dec 2015 → 12.12.2024 | 7 working days (general); 3 for rights (from 26.12.2019) | *R* − 7 sessions (rights: *R* − 3) | Rule text VERIFIED (S1 footnotes); fallback PROVISIONAL |
| Before Dec 2015 | Listing Agreement clause 16 (**not found**) | **no fallback**: usable only at the ex-date | **NEEDS SOURCE**; flagged per case in the data-quality report |

The fallback is conservative **only under three conditions, none of them verified**:
- companies honour the minimum notice;
- "working days" map one-to-one to exchange sessions (bank and exchange holidays can differ);
- announcements reach the market on the intimation day.

It is therefore PROVISIONAL, not a verified guarantee.
Forced exits need knowledge by the close of E−2. The fallback satisfies this post-2015 (*R* − 3 ≤ *E* − 2 under T+1). Cases that cannot be exited pre-emptively fall under the terminal-event rule below.
Delistings have no record date, so their knowledge time is the exchange announcement date (NEEDS SOURCE); without it, no pre-emptive exit.

## Per-action rules

### Splits and consolidations
| Rule | Class | Note |
|---|---|---|
| Quantity × ratio at E; total cost basis unchanged | NEEDS DESIGN DECISION (proposed; mechanically standard) | |
| Fractional entitlements (consolidations): floor the quantity; credit the fraction as cash at the E open | PROVISIONAL + NEEDS SOURCE | Real practice (sale of fractions and later distribution) and its timing not verified |
| Features: pre-E prices ÷ ratio, point-in-time | NEEDS DESIGN DECISION (proposed) | |
| Tax lots: split proportionally, original acquisition dates kept | NEEDS SOURCE | Holding-period and cost treatment of split shares not verified in S5 |

### Bonuses
| Rule | Class | Note |
|---|---|---|
| `bonus_qty = floor(qty × a/b)` at E; fraction as cash | Quantity: NEEDS DESIGN DECISION (proposed) · fraction handling: PROVISIONAL + NEEDS SOURCE | |
| **Trading restriction, bonuses announced on/after 01.10.2024:** bonus shares sellable from **record date + 2 sessions** (deemed allotment T+1, trading T+2) | **VERIFIED** (S3) | |
| **Trading restriction, bonuses before 01.10.2024:** ICDR Reg 295 required implementation (incl. trading) within 15 days of board approval (no shareholder approval) or 2 months of the board meeting (with approval) | Regulation VERIFIED (S4) | The regulation runs from **board approval**, not from the ex-date, and board-approval dates may not be in our data. So the actual lag after E is **unknown** |
| Lag used for pre-Oct-2024 bonuses: not sellable for 10 sessions after E | NEEDS DESIGN DECISION (the number is a PROVISIONAL guess, not derived from S4) | Small effect for a monthly-rebalanced strategy; reported |
| Selling bonus shares before credit | NEEDS SOURCE | Nothing found authorising it; V1 forbids it |
| Features: factor b/(a+b) point-in-time | NEEDS DESIGN DECISION (proposed) | |
| **Tax lot: bonus shares cost nil; holding period from allotment date** | **VERIFIED** for ITA 2025 (s.90(6)(d), s.2(101)) (S5); 1961-Act equivalents VERIFIED (secondary) | Applies to post-tax estimates |
| **Bonus stripping:** from AY 2023-24 (transfers from 01.04.2023), a loss on original shares bought within 3 months before the record date and sold within 9 months after, while bonus shares are retained, is disallowed and becomes the bonus shares' cost | **VERIFIED** (S5, FB2022 memo; ITA 2025 s.175(9)-(10)) | **NEEDS DESIGN DECISION:** model in the post-tax estimate (proposed) or flag only |

### Cash dividends
| Rule | Class | Note |
|---|---|---|
| Receivable at E (counts in equity, not in available cash) | NEEDS DESIGN DECISION (proposed) | |
| **Payment timing:** a declared dividend must be paid within 30 days of declaration (Companies Act s.127) | VERIFIED (secondary; primary text not reachable on 2026-09-30) | Final dividends are declared at the AGM, interim by the board. Record-date-to-payment gap not determined |
| Payment lag default: 30 calendar days after E | PROVISIONAL | Could be longer for final dividends when the AGM is after the record date; measure from data if possible |
| **Dividend tax, received before 01.04.2020:** company paid DDT; shareholder exempt (s.10(34)); s.115BBDA 10% on dividends above ₹10 lakh (start year UNVERIFIED) | VERIFIED (S5, FB2020 memo) except the 115BBDA start year | At V1 capital levels the ₹10 lakh threshold is unlikely to bind, but it is modelled if exceeded |
| **Dividend tax, received from 01.04.2020:** taxable at the owner's slab rate | VERIFIED (S5) | Slab rate: owner input |
| **TDS (s.194 / ITA 2025 s.393):** 10%; threshold ₹5,000 (from FY 2020-21), ₹10,000 from 01.04.2025 | VERIFIED (S5) | Withholding only; modelled as cash timing, not final liability |
| Features use price-return basis (split/bonus adjusted) for the baseline; total-return is a Phase 5 strategy-spec choice | NEEDS DESIGN DECISION | |

### Mergers / amalgamations
| Rule | Class | Note |
|---|---|---|
| New buys blocked from knowledge time (C3/C4) | NEEDS DESIGN DECISION (proposed) | |
| **Forced exit** at the open of the last session before E (order at E−2 close) | NEEDS DESIGN DECISION (proposed) | Alternative: model the share swap. Tax neutrality of swaps is VERIFIED (ITA 2025 s.70(1)(f), s.73), which means **our forced exit creates a taxable sale the real holder might not have had**. Reported as a known bias |
| Scheme record dates need 7 working days' notice (Reg 37 schemes, post-Dec-2024) | VERIFIED (S1) | Feeds C4 |

### Demergers
| Rule | Class | Note |
|---|---|---|
| Parent forced exit before E; no new buys until E + 20 sessions | NEEDS DESIGN DECISION (proposed) | Cool-off length is judgement |
| Parent feature adjustment factor = open(E) ÷ close(E−1) | PROVISIONAL + NEEDS SOURCE | Relies on an ex-date price-discovery session, **not verified** |
| Spun-off entity ignored until it joins the universe | NEEDS DESIGN DECISION (proposed) | |
| Demerger cost apportionment exists in tax law (ITA 2025 s.73 rows 14–15) | VERIFIED (S5) | Not used, because of the forced exit; noted for a future full model |

### Rights issues
| Rule | Class | Note |
|---|---|---|
| Rights entitlements (REs) are credited in demat and **tradable on the exchange** for letters of offer filed on/after 14.02.2020 | **VERIFIED** (S6) | |
| V1: holdings kept; REs neither sold nor exercised, so their value is forgone and reported | NEEDS DESIGN DECISION (proposed) | Because REs are tradable post-2020, ignoring them loses real value. Alternative: sell REs on their first trading day, if RE prices exist in bhavcopy (UNVERIFIED) |
| Feature adjustment by theoretical ex-rights price when ratio and issue price are available; else 20-session no-buy cool-off | PROVISIONAL | |

### Buybacks
| Rule | Class | Note |
|---|---|---|
| Ignore; record as informational | NEEDS DESIGN DECISION (proposed) | Conservative: tender gains ignored |

### Symbol / name / ISIN changes
| Rule | Class | Note |
|---|---|---|
| Stable internal id; dated symbol history from NSE symbol-change lists | NEEDS DESIGN DECISION (proposed) | List exists (VERIFIED reachable in Phase 0); access terms apply (ADR-001) |
| Renames retain ISIN (continuous history) | VERIFIED for the cases checked in the Upstox instrument files (LTI → LTM; Bharti Infratel → Indus Towers) | Not a general rule; each mapping is checked |

### Delistings and suspensions
| Rule | Class | Note |
|---|---|---|
| Voluntary delisting via reverse book building (or fixed price, from 25.09.2024); remaining holders may tender at the exit price for ≥ 1 year after delisting | **VERIFIED** (S7) | |
| V1: forced exit before the last trading day when announced | NEEDS DESIGN DECISION (proposed) | Alternative: model tendering at the exit price during the exit window, which is more accurate for voluntary delistings |
| Notice period before the last trading day | **NEEDS SOURCE** | Not found in S7 |
| Sudden suspension: valued at last close marked STALE; sells re-issued; after 60 sessions valued at ₹0 until trading resumes | NEEDS DESIGN DECISION (proposed) | 60 is judgement |
| Unrecognised action type → data-quality failure; no new buys until classified | NEEDS DESIGN DECISION (proposed) | |

### Terminal events: held security stops trading without an exit
Applies when a forced exit was impossible: unknown knowledge time (pre-2015, delistings), an unfillable sell, an
emergency pause over the exit window, or a sudden suspension.

| Rule | Class |
|---|---|
| Merger with a parsed swap ratio: convert holdings into acquirer shares at the ratio on the effective date; fractional entitlement as cash (PROVISIONAL); tax lot carried over (ITA 2025 s.70(1)(f), s.73: VERIFIED) | NEEDS DESIGN DECISION (proposed) |
| Merger without a parsed ratio, demerger, delisting, suspension: position marked `STALE` at last close; excluded from new orders; after 60 sessions valued at ₹0 for equity and risk until resolved; reported as an unexited terminal event | NEEDS DESIGN DECISION (proposed; 60 is judgement; ₹0 is deliberately conservative) |
| Voluntary delisting with a known exit price: may instead credit cash at the exit price, within the ≥ 1-year exit window (S7) | NEEDS DESIGN DECISION (alternative) |
| Every terminal event is counted and its P&L impact reported per evaluation | NEEDS DESIGN DECISION (proposed) |

## Unresolved-rule register (owner requirement 2026-09-30)

**No unresolved rule may silently become production behaviour.** Mechanism (implemented from Phase 2, when rules are first applied):
1. **Every** handling rule in this ADR has an id: U1–U20 and U21–U28 below. Any rule later found without an id defaults to `UNRESOLVED`. Each has a status in `configs/corporate-action-rules.toml`:
   - `ACCEPTED`: owner-approved design or verified rule
   - `ACCEPTED_PROVISIONAL`: owner explicitly accepts a provisional value, labelled in outputs
   - `UNRESOLVED`: the default for every row below until the owner decides
2. The engine **refuses to apply an `UNRESOLVED` rule**. An event needing one becomes a **data-quality failure** for its range
   (blocks snapshots/evaluation of that range; ADR-013 A19). There is no fallback to a default behaviour.
3. Every run manifest lists the rule ids and statuses exercised. Gate A requires that no `UNRESOLVED` rule was needed in any evaluated period.
4. **Phase 1 applies no corporate-action rule.** It only parses and types actions, stores fields exactly as published (ex-date, record date, announcement date when present), and emits **review flags**, not blocks, for U6 checks. Knowledge-time policy (U1–U3) is not implemented in Phase 1. The contract suite checks as-of behaviour on ex-date and on announcement date when present, with **no fallback**. Snapshots store raw parsed actions plus parser version; no rule outcome is baked in.

| ID | Question | Why it matters | Evidence required | Affects backtest correctness? | Blocks Phase 1? |
|---|---|---|---|---|---|
| U1 (C3) | Do NSE corporate-action records carry an announcement/board-outcome date? | Determines when an action is knowable (look-ahead) | Field inspection of the CA data once access is permitted; or a permitted alternative source | **Yes** | No: the parser captures the field if present, else marks it absent |
| U2 (C4) | Is the minimum-notice fallback actually conservative (notice honoured; working days = sessions; same-day dissemination)? | A non-conservative fallback leaks future knowledge | Exchange vs bank holiday lists; a sample of announcements with both announcement and record dates | **Yes** | No |
| U3 (C4) | What record-date notice applied before Dec 2015 (Listing Agreement clause 16)? | Covers 2011–2015 of the research period | Archived Listing Agreement text (SEBI/exchange) | **Yes** | No |
| U4 (C5) | Adopt point-in-time adjustment (actions with ex-date ≤ D only)? | Prevents look-ahead in level-dependent features | Owner decision | **Yes** | No |
| U5 (C6) | Re-derive orders filling on an ex-date from target value? | Wrong quantities around splits/bonuses | Owner decision | **Yes** | No |
| U6 (C7) | Ratio-check tolerance ±20%; unexplained-move flag at 40%? Should a failed check block or only flag? | Detects wrong or missing actions | Measured distribution of ex-date moves once data exists; owner decision | Indirectly (data quality) | No: Phase 1 implements the checks with these values as **labelled provisional parameters** that emit **review flags only**; blocking behaviour waits for resolution |
| U7 | How are fractional entitlements (consolidations, bonuses) settled, and when? | Small cash/position errors | Company/exchange practice documents | Minor | No |
| U8 | Tax lot treatment of split shares (cost, holding period)? | Post-tax estimate | Income-tax Act provisions on sub-division | Post-tax only | No |
| U9 | Sell lag for pre-Oct-2024 bonus shares (proposed 10 sessions)? | Could allow selling shares not yet tradable | Board-approval and trading-start dates for a sample of bonuses | Minor | No |
| U10 | Could bonus shares be sold before credit? | Same as U9 | Exchange/depository rules | Minor (V1 forbids it) | No |
| U11 | Model bonus stripping (from 01.04.2023) in post-tax estimates? | Post-tax accuracy | Owner decision (rule itself VERIFIED) | Post-tax only | No |
| U12 | Dividend receivable at E; 30-day payment lag? | Cash timing | Payment dates from announcements; owner decision | Minor | No |
| U13 | Price-return vs total-return basis for features | Changes signals | Phase 5 strategy spec | **Yes** (strategy) | No |
| U14 | Merger: forced exit vs swap modelling | Forced exit creates taxable sales and misses post-merger returns | Owner decision; swap ratios parsable? | **Yes** | No |
| U15 | Demerger: forced exit, 20-session cool-off, open(E)/close(E−1) factor; does an ex-date price-discovery session exist? | Price discontinuity handling | Exchange circulars on special pre-open sessions; owner decision | **Yes** | No |
| U16 | Rights: ignore REs vs sell on first RE trading day; are RE prices in bhavcopy? | Forgone value | Bhavcopy series inspection (after access); owner decision | Minor | No |
| U17 | Buybacks: ignore? | Forgone tender gains | Owner decision | Minor | No |
| U18 | Source and completeness of the symbol/ISIN change mapping (esp. pre-ISIN legacy files) | Identity errors break histories | Symbol-change list access (ADR-001); cross-check with ISINs where present | **Yes** | No: Phase 1 implements mapping against a synthetic list and reports unmapped discontinuities |
| U19 | Delisting knowledge time and notice period | Exit feasibility | Exchange delisting circulars | **Yes** | No |
| U20 | Terminal events: STALE → ₹0 after 60 sessions; merger conversion when ratio known; delisting exit-price credit | Valuation of stuck positions | Owner decision | **Yes** | No |
| U21 (C1) | Use the exchange ex-date field rather than deriving it? | Wrong ex-dates around settlement holidays | Owner decision | **Yes** | No: Phase 1 stores the field as given, applies nothing |
| U22 | Split quantity × ratio and feature ÷ ratio | Share counts and adjusted prices | Owner decision | **Yes** | No |
| U23 | Bonus quantity `floor(qty × a/b)` and feature factor b/(a+b) | Same | Owner decision | **Yes** | No |
| U24 | Merger/demerger: block new buys from knowledge time | Avoids buying into unsupported events | Owner decision | **Yes** | No |
| U25 | Spun-off entity ignored until it joins the universe | Missed spin-off value | Owner decision | Minor | No |
| U26 | Rights: theoretical ex-rights feature adjustment, else 20-session cool-off | Feature discontinuity | Owner decision; rights ratio/price availability | Minor | No |
| U27 | Sudden suspension handling (STALE, sells re-issued, write-down) | Valuation | Owner decision (overlaps U20) | **Yes** | No |
| U28 | Unrecognised action types block new buys until classified | Safety | Consistent with ADR-001 D6; owner confirmation | **Yes** | No: Phase 1 flags unrecognised types in the data-quality report |

Already settled, not in the register: C2 entitlement definition (VERIFIED, secondary); bonus T+2 tradability from 01.10.2024
(VERIFIED); dividend and capital-gains tax rules (VERIFIED, ADR-008); RE tradability post-2020 (VERIFIED); delisting exit window
(VERIFIED); unrecognised action types are data-quality failures (follows from accepted ADR-001 D6).
C1 (use the exchange ex-date field) is proposed design. It is consistent with Phase 1, which stores the field as given.

**None of U1–U28 blocks Phase 1.** Each blocks Gate A for any period where it is needed, until resolved.

## Tax-law transition note
The Income-tax Act 2025 is in force from 01.04.2026 (s.1(3); s.536 repeals the 1961 Act with savings) (S5, VERIFIED).
Section numbers change (e.g. 111A → 196, 112A → 198, 194 → 393). Post-tax estimates are date-versioned; transfers before
01.04.2026 follow 1961-Act rules. ADR-008 carries the rate table.

## Consequences
- The owner reviews every NEEDS DESIGN DECISION row; approved rows become Accepted design.
- NEEDS SOURCE rows stay configurable, are labelled UNVERIFIED in outputs, and are listed in each data-quality report where they apply.
- Known biases are reported per evaluation: forced-exit taxable sales, forgone rights value, ignored buyback tenders, and pre-2015 actions without knowledge dates.
