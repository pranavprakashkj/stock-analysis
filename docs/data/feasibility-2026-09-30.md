# Data Feasibility Review: free sources for 2010 → Jun 2026

Date: 2026-09-30 · Method: desk research plus **single-file sample fetches only** (no bulk download). Evidence levels:
**VERIFIED** (fetched and seen), **SOURCE-CLAIMED** (a page states it; data not accessed), **UNVERIFIED** (inference).

Disclosure: the research made a small number of scripted single-file requests to NSE and niftyindices.com
(a few bhavcopy zips, two PDFs, a handful of JSON calls) to confirm reachability. The samples are kept outside the
repository, in the session scratchpad. Given the NSE terms below, **no further scripted access** will be made without owner approval.

## Summary

| Data | Coverage 2010–Jun 2026 | Verdict | Main caveat |
|---|---|---|---|
| Daily unadjusted prices (bhavcopy) | Legacy format 2010 → 5 Jul 2024; UDiFF 1 Jan 2024 → present (VERIFIED samples) | **Coverage feasible; access method BLOCKED pending decision** | NSE Terms of Use prohibit systematic/automated data collection |
| Corporate actions | NSE records back to 2010 (VERIFIED sample via JSON endpoint) | **Feasible with caveats** | Ratios are free text; the JSON endpoint is automated access (terms); CSV export for old ranges UNVERIFIED |
| Nifty 100 membership history | Change notices back to 1998 on niftyindices.com (VERIFIED); no historical snapshot files | **Feasible with caveats** | Manual reconstruction from ~16 years of PDF notices; a 2010 seed list is needed; old index names (CNX 100, CNX Nifty Junior) |
| Nifty 100 TRI | 2010 → 30 Jun 2026 (VERIFIED values at both ends) | **Feasible** | 1-year window per request (~17 requests); niftyindices.com terms UNVERIFIED |
| 91-day T-bill yield | RBI weekly auction cut-off yields, current to Sep 2026 (VERIFIED page) | **Feasible with caveats** | Export back to 2010 UNVERIFIED on RBI itself (a third-party mirror claims 1993+); FBIL daily only from Aug 2017 |

**Dates:** no source showed a coverage gap that would force a change to the ADR-006 dates.
The binding constraint is **terms of access**, not coverage. Dates are unchanged.

## 1. Daily prices

- Legacy CM bhavcopy: `nsearchives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip`.
  HTTP 200 for 04-Jan-2010, 03-Jan-2011 and 05-Jul-2024; **404 from 08-Jul-2024 onward**, so the legacy format ends 5 Jul 2024 (VERIFIED).
  The 2011 sample: 1,471 rows (1,404 EQ, 44 BE; other series present); columns SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP; **no ISIN** (VERIFIED).
- UDiFF: `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip`; 200 for 2024-01-01 → 2026-06-01; 404 for 2023 and earlier (VERIFIED). Includes ISIN; series in `SctySrs`.
- `archives.nseindia.com` (old host) returns 403; `www.nseindia.com` returns 403 to non-browser clients (VERIFIED).
- **NSE Terms of Use** (https://www.nseindia.com/static/nse-terms-of-use, VERIFIED text):
  - "User is prohibited to conduct any systematic or automated data collection activities (including scraping, data mining, data extraction and data harvesting) on or in relation to our Website / Mobile Application."
  - Content "shall not be copied, … stored (either in hardcopy or in an electronic retrieval system) … distributed … without prior written permission of NSE. Unless the information or Content is available for download, not to aggregate, copy or duplicate…"
  - robots.txt allows crawling, but the terms explicitly prohibit automated collection.
- Implication: scripted download of ~4,000 daily files is **not permitted** under the stated terms. This is not a legal opinion; the owner decides the route.
- Delisted stocks appear in bhavcopy up to their last trading day (VERIFIED via series presence), which is good for survivorship.
- Symbol/name change lists exist: `symbolchange.csv` (~1,064 rows), `namechange.csv`, `EQUITY_L.csv` (VERIFIED reachable). Needed because pre-UDiFF files have no ISIN.

## 2. Corporate actions
- NSE corporate-actions JSON returned 2010 records with symbol, series, ISIN, ex-date, record date and a free-text subject, e.g. "Fv Split Rs.10 To Re.1" (VERIFIED). **Ratios must be parsed from free text**, which is why ADR-007's discontinuity check exists.
- The page's CSV export for historical ranges: UNVERIFIED (needs a browser check). BSE corporate actions export: UNVERIFIED.

## 3. Nifty 100 membership
- Current list only: `niftyindices.com/IndexConstituent/ind_nifty100list.csv` (VERIFIED).
- Press-release archive, 1998–2026, 1,506 items (2010: 18, 2011: 25, 2012: 15) (VERIFIED). A 2010 notice (effective 1 Oct 2010) lists Nifty, Nifty Junior and CNX 100 changes (VERIFIED).
- Reconstitution is semi-annual with **varying effective dates** (e.g. 8 Apr 2010, 1 Oct 2010, 27 Apr 2012, 28 Sep 2012, 30 Sep 2025, 30 Mar 2026), plus event-driven replacements (VERIFIED).
- Methodology (Sept 2026 edition): Nifty 100 is selected first from Nifty 500 and Nifty 50 chosen within it (VERIFIED). Historically CNX 100 = Nifty + Junior (UNVERIFIED). Membership = Nifty 50 ∪ Next 50 in both cases.
- Third-party GitHub datasets: mostly Nifty 50, survivor-biased; **not reliable as a primary source** (UNVERIFIED).
- Work required: a seed list for early 2010 plus replaying ~16 years of change notices, curated by hand with a source per change.

## 4. Nifty 100 TRI
- `niftyindices.com/BackPage/getTotalReturnIndexString` (POST) returned 15-Jan-2010 = 5,865.63 and 30-Jun-2026 = 34,459.42 (VERIFIED). Price index history is also available.
- Limited to 1-year ranges per request. niftyindices.com terms of use: UNVERIFIED (NSE group company; similar restrictions are plausible).

## 5. T-bill
- RBI DBIE Treasury-bill auction page with 91-day implicit yield at cut-off (VERIFIED page, latest auction 23-Sep-2026). Earliest export date and export format UNVERIFIED on RBI directly.
- Third-party mirror (dataful.in) claims 1993–2026 (SOURCE-CLAIMED); usable only as a cross-check.
- FBIL daily 3-month T-bill benchmark from 23 Aug 2017 (VERIFIED press statement). **Excluded:** FBIL data is licensed (see the [access review](access-and-terms-2026-09-30.md)).
- FRED has no India T-bill series (VERIFIED); the call money rate is a fallback, but not a T-bill rate.
- Point-in-time handling: effective at the auction result date; as-of forward-fill onto trading days.

## 6. Broker APIs (alternative price route)
- Upstox v3: daily candles "from January 2000", ≤ 10 years per request, reportedly unadjusted (SOURCE-CLAIMED); free with an account.
- Dhan: paid data API (₹499/month + taxes, SOURCE-CLAIMED); excluded by the free-data constraint.
- Angel SmartAPI / Fyers: request-size limits; history depth undocumented (SOURCE-CLAIMED).
- **Delisted-symbol coverage undocumented for all** (UNVERIFIED). A broker API is survivorship-risky unless verified on known delisted or merged symbols (e.g. a stock that left via merger in 2023).

## Human checks required (browser)
1. NSE corporate-actions CSV export for 2010-era date ranges; BSE export as a fallback.
2. Spot-check legacy bhavcopy gaps (random dates, holidays, header change around ISIN introduction).
3. niftyindices.com terms of use for historical data and press releases.
4. Early-2010 Nifty 100 (CNX 100) seed list source (factsheet or monthly constituents PDF).
5. RBI DBIE T-bill export: start date and format.
6. TRI values against an independent source on 2–3 dates.
7. Upstox (or another free broker) returns candles for a known delisted/merged symbol.
