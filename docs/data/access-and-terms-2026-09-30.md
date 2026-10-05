# Data Access & Terms-of-Use Review

Date: 2026-09-30 · Companion to [feasibility-2026-09-30.md](feasibility-2026-09-30.md) · Not legal advice: this summarises what the texts say.

Evidence levels: **VERIFIED** (page/file fetched and read) · **SNIPPET** (search-result text only) · **UNVERIFIED**.

## 1. Terms of use per source

| Source | What we would access | What the terms say | Evidence | Programmatic access position |
|---|---|---|---|---|
| nseindia.com / nsearchives | Bhavcopy archives, symbol-change lists, corporate actions | "User is prohibited to conduct any systematic or automated data collection activities (including scraping, data mining, data extraction and data harvesting)…"; content not to be "stored (either in hardcopy or in an electronic retrieval system)… without prior written permission of NSE" | VERIFIED (https://www.nseindia.com/static/nse-terms-of-use) | **Not permitted without written permission** |
| NSE permission route | Request for personal research use | NSE Data & Analytics, marketdata@nse.co.in, +91-22-26598385; paid data subscriptions exist (EOD, historical, corporate data) | SNIPPET (https://www.nseindia.com/static/nse-data-and-analytics/contact-us) | Owner to write (draft below) |
| niftyindices.com (NSE Indices) | Nifty 100 TRI, change press releases, methodology | Terms page could not be fetched (timeout). An index licence is needed "for creating a product based on or linked to an index"; data subscriptions are sold | SNIPPET (https://www.niftyindices.com/offerings/index-licensing) | **Unresolved**; treat as restricted until the terms are read; include in the NSE permission request |
| NSE corporate-action data | Corporate-action records 2010–2026 | Covered by nseindia.com terms (above) | VERIFIED | **Not permitted** programmatically without permission |
| RBI (rbi.org.in) | 91-day T-bill auction press releases | Disclaimer: "Caching and links to, and the framing of this Web Site or any of the contents are prohibited"; deep links need prior written permission; © RBI. No explicit clause on data reuse or automated access | VERIFIED (https://www.rbi.org.in/Scripts/Disclaimer.aspx) | **Ambiguous**; manual download of published statistics is the conservative route |
| DBIE (dbie.rbihub.in) | T-bill auction series | Appears to be operated by RBI Innovation Hub; code open-source; **no data terms found** | VERIFIED (partial) | **Ambiguous**; manual export only until clarified |
| data.gov.in | Possible T-bill data | Hosts some RBI datasets; no T-bill yield dataset found | SNIPPET | Not a source for now |
| FBIL | Daily T-bill benchmark | Data Fee Schedule FAQ: end-user licence and fees for uses incl. "Valuation of portfolio"; redistribution fee | VERIFIED (https://www.fbil.org.in/uploads/Data_Fee_Schedule_FAQ_repl_3576a15203.pdf) | **Licensed; excluded** (not even as a cross-check) |
| BSE | Corporate actions (fallback) | "No part of the information on BSE's website… may be reproduced or transmitted in any form by any means, without the express written consent of BSE" | SNIPPET (page returned 403) | **Not permitted** without consent |
| Upstox API | Historical daily candles; instrument files | General terms have no API clauses; developer terms shown only at app registration (UNVERIFIED). Official staff forum replies: no additional approval needed, stay within rate limits. Rate limits: 50/s, 500/min, 2,000/30 min | Forum + rate-limit docs VERIFIED (https://community.upstox.com/t/api-usage-clarification/13250, https://upstox.com/developer/api-documentation/rate-limiting/) | **Designed for programmatic use** with the owner's token; the owner must read the developer terms at registration; storage terms unverified |
| Angel One SmartAPI | Historical candles | Terms linked from sign-up; not read | SNIPPET | Unverified |

**Cross-cutting observation:** no source's terms found so far carve out personal or non-commercial use.

## 2. Broker source survivorship test (Upstox)

What was done: two requests to Upstox's **public** instrument files (no login). No candle or price endpoint was called.

| Case | ISIN | In active list | In suspended list | Evidence |
|---|---|---|---|---|
| HDFC Ltd (merged into HDFC Bank, 2023) | INE001A01036 | no | yes (EQ) | VERIFIED |
| Mindtree (merged into LTI → LTIMindtree, 2022) | INE018I01017 | no | yes (EQ) | VERIFIED |
| DHFL (delisted) | INE202B01012 | no | yes (EQ) | VERIFIED |
| Jet Airways (suspended) | INE802G01018 | no | yes (EQ) | VERIFIED |
| IDFC Ltd | INE043D01016 | no | yes (EQ) | VERIFIED |
| L&T Infotech → LTIMindtree → "LTM" (renamed, surviving ISIN) | INE214T01019 | yes | — | VERIFIED |
| Bharti Infratel → Indus Towers (renamed) | INE121J01017 | yes | — | VERIFIED |
| Cairn India (merged into Vedanta, 2017) | INE265A01028 (ISIN UNVERIFIED) | no | no | VERIFIED absence |

Findings:
- Historical candles require the owner's access token (VERIFIED, v3 docs). Daily data is "available from January, 2000" (SOURCE-CLAIMED). Instruments are keyed by ISIN.
- Identifiers for 2019–2023 exits are retained; **whether candles are returned is UNVERIFIED**.
- **Cairn India's absence suggests pre-~2019 exits may be missing entirely** (inference, UNVERIFIED).
- Renames keep the ISIN, so history should be continuous across renames (inference; verify).

### Owner-run test (with the owner's own Upstox token; ≤ 10 requests)
`GET https://api.upstox.com/v3/historical-candle/NSE_EQ%7C{ISIN}/days/1/2015-01-31/2015-01-01`
(headers `Authorization: Bearer <token>`, `Accept: application/json`) for: HDFC Ltd, Mindtree, DHFL, Jet Airways,
IDFC Ltd, Indus Towers, LTM, Cairn India, and control HDFC Bank (INE040A01034).

Interpretation:
- Candles returned for the merged, delisted and suspended cases → no survivorship bias from exits since ~2019.
- Empty or error for those while the control works → **survivorship bias**; source unusable as sole source.
- Cairn India alone failing → pre-~2019 exits missing; the 2011–2018 research period would be incomplete.
- Adjustment check: compare a known split in the returned series against a bhavcopy sample to see whether prices are raw.

## 3. Survivorship-bias assessment

- **Mechanism:** a momentum backtest that silently lacks price data for past members loses (a) collapses (e.g. insolvencies)
  that may have been held, which inflates returns and hides crash risk, and (b) takeover exits, which distort ranks.
- **Rule adopted in design (ADR-001 §Data-access plan 4):** every past member must have price data for its whole
  membership window; missing member-days are a data-quality failure; no silent drops; no silent date changes.
- **Measurement (Phase 1+ once data exists):** count past members and member-days without price data, per year, reported in the data-quality report.

## 4. Draft permission request to NSE (for the owner to review, edit and send; not sent)

> Subject: Request for permission: personal, non-commercial research use of NSE historical end-of-day data
>
> Dear NSE Data & Analytics team,
>
> I am an individual investor building a personal, non-commercial research tool to backtest a systematic equity
> strategy on NSE cash-market data. I would like to request written permission to download and store, for my own
> private research only, the historical CM bhavcopy files (2010 to present), the equity symbol/name-change lists,
> historical corporate-action records, and the Nifty 100 historical index values and index-change announcements
> published by NSE Indices.
>
> The data would not be redistributed, published, sold, or used for any commercial product. Downloads would be
> rate-limited and one-time, with occasional daily updates. If this use requires a paid subscription instead,
> I would be grateful for details of the most suitable product for an individual.
>
> Kind regards,
> [Name]

## 5. Items requiring the owner's own action
1. Send (or not) the NSE request; record the response in this file.
2. Register an Upstox developer app; read and record the developer terms; run the test in §2.
3. Read the niftyindices.com and BSE terms pages in a browser; record the relevant clauses here.
4. Decide the T-bill route: manual RBI download vs waiting for clarification (see feasibility review).
