# ADR-001: Free market data for development, behind `MarketDataProvider`

## Status
Accepted (owner, 2026-09-30), with one proposed sub-decision (file-based ingestion, §Decision 3) awaiting confirmation.

## Date
2026-09-30

## Context
- The owner will not pay for market data during development and research.
- The provider must be replaceable (paid vendor or broker API) without changing trading logic.
- The owner requires that the system is **not built around direct NSE scraping**, and that the
  applicable terms and availability are verified before any bulk automated download from NSE archives.
- Backtests need **unadjusted** daily OHLCV (fills and valuation), corporate actions (adjustment
  and ledger effects), and point-in-time index membership (ADR-002).

## Decision
1. **Port:** `MarketDataProvider` (application-layer port) answers, by knowledge time (ADR-018/ADR-019):
   unadjusted bars of **all series** (amended 2026-10-05 by ADR-019; previously "EQ-series"), corporate
   actions, universe membership, and typed absences. Instruments are keyed by `InstrumentId`. Trading
   logic depends only on the domain value objects it returns, never on a provider.
2. **Development-only source:** NSE end-of-day equity bhavcopy (both the legacy format and the
   UDiFF format introduced in 2024) and NSE corporate-action data. Selected for development and
   research only; not a production commitment.
3. **Proposed (confirm): ingestion is file-based.** The V1 adapter reads bhavcopy/corporate-action
   files from a local import directory. *How* files are obtained (manual download, a permitted
   automated download, or a broker API export) is a separate, replaceable acquisition step, so the
   system does not depend on scraping. No automated NSE download is built until the terms check (5) passes.
4. **Snapshots:** validated data is written to immutable, content-hashed Parquet snapshots; the
   engine reads snapshots only, never the network.
5. **Terms and availability check:** done 2026-09-30; see
   [docs/data/feasibility-2026-09-30.md](../data/feasibility-2026-09-30.md) and the finding below. Automated
   NSE access is **not** permitted under the stated terms; the acquisition route is an open owner decision. The port is unaffected.
6. **Data quality is a failure, not a warning:** missing sessions vs the calendar, stale files,
   OHLC inconsistencies, zero/negative prices, duplicates, unmapped symbol discontinuities,
   unexplained or unsourced absences, and gaps in historical coverage are reported as **data-quality failures** that block snapshot
   creation (or mark the affected range as unusable) until resolved. An owner may record an acceptance so that
   **exploratory research runs** can proceed on a labelled range, but **an accepted failure never satisfies ADR-013 A19**.
   Missing member-days and survivorship gaps can never be waived for a Gate A verdict.
   **Not failures** (ADR-019 §3, amended 2026-10-05): sourced series changes, suspensions, delistings and
   not-yet-listed periods are typed legitimate absences; renamed symbols mapped by the dated identity map.
7. Every provider adapter must pass one shared contract-test suite.

## Alternatives Considered
### yfinance
- Unofficial, breaks without notice, opaque adjusted series, no delisted symbols. Rejected as a
  source of record; acceptable only for ad-hoc sanity checks.
### Free broker APIs (e.g. Upstox, Angel One SmartAPI)
- No fee but needs an account and access token; delisted coverage unverified (see data-access plan). Candidate route B.
### Paid vendors / Kite Connect historical
- Out of scope during research by owner decision; later drop-in via the port.
### Automated NSE scraper as the core ingestion path
- Rejected by owner: fragile, and terms unverified.

## Rationale
Separating *acquisition* from *ingestion* keeps the pipeline independent of how files are fetched,
which is the part most likely to break or be disallowed.

## Feasibility finding (2026-09-30): blocking decision for the owner
See [docs/data/feasibility-2026-09-30.md](../data/feasibility-2026-09-30.md).
- **Disclosure:** during Phase 0 research, a small number of scripted single-file requests were made to NSE and niftyindices.com
  (a few bhavcopy files, two PDFs, a few JSON calls) to test reachability, before the terms were read. They are listed in the
  feasibility review. No further requests are made without approval.
- Sample dates were reachable across 2010 → Jun 2026 (legacy bhavcopy up to 5 Jul 2024; UDiFF from 1 Jan 2024). This is **VERIFIED on sampled dates only**;
  complete coverage is UNVERIFIED until full ingestion. "~4,000 files" is an estimate (≈ 250 sessions × 16 years).
- **NSE's Terms of Use prohibit "any systematic or automated data collection activities"** and restrict storage in
  electronic retrieval systems without written permission. A scripted bulk download is therefore not an acceptable
  acquisition route under the stated terms. The file-based ingestion design (Decision 3) is unaffected, but **how the
  ~4,000 historical files are obtained is unresolved**. Options (owner decision; not a legal opinion):

  | Option | Cost | Terms position | Data risk |
  |---|---|---|---|
  | A. Request written permission from NSE for personal, non-redistributed research use | Free | Clean if granted | None beyond format issues; timeline unknown |
  | B. Free broker API (e.g. Upstox) under the broker's API terms | Free (account) | Designed for programmatic use | Delisted/merged coverage **unverified** → survivorship risk; must verify before adoption |
  | C. Manual browser downloads by the owner | Free | Individual downloads of downloadable content; grey area at this volume | Impractical at ~4,000 files; error-prone |
  | D. Paid licensed data | Paid | Clean | Excluded by the current free-data constraint |

  **Owner position (2026-09-30):** no scripted access to NSE without permission; pursue **A**; investigate **B** in parallel.
  Phase 1 code proceeds on a handful of sample files; **full historical ingestion waits** for the decision.

## Data-access plan (owner position 2026-09-30; details in the [access & terms review](../data/access-and-terms-2026-09-30.md))
1. **No further automated requests** to NSE, niftyindices.com, BSE or FBIL without owner approval.
2. **Option A:** the owner writes to NSE Data & Analytics (marketdata@nse.co.in, contact route found via search snippet, UNVERIFIED)
   requesting written permission for personal, non-commercial, non-redistributed research use of archive bhavcopies and corporate-action data.
3. **Option B (Upstox):** historical candles need the owner's access token (VERIFIED from docs). Public instrument files still
   list ISINs of merged/delisted/suspended companies (HDFC Ltd, Mindtree, DHFL, Jet Airways, IDFC). This is VERIFIED from the files,
   but whether **candles** are returned for them is **UNVERIFIED**. Cairn India (merged 2017) is absent from both files, so
   pre-~2019 exits may be missing. The owner-run test procedure is in the access review.
4. **Survivorship rule (design choice):** every security that was a Nifty 100 member on any evaluated date must have
   price data for its whole membership window. **Missing member-days are a data-quality failure (ADR-013 A19)**, never silently dropped.
   A period with unresolved missing members cannot support a Gate A verdict. It is flagged to the owner, and dates are not silently changed.
5. A mixed-source build is allowed only if the sources pass the same contract suite **and** a cross-source reconciliation on overlapping dates.

## Consequences
- Manual acquisition may be needed initially; that is slower but compliant.
- The data-quality report is a Phase 1 deliverable and gates everything downstream.
- **Split-date feasibility (ADR-006) is verified after full ingestion**, which waits for the access decision; it is not a Phase 1 task. Limitations are flagged; dates are not silently changed.
- **Storage caution:** NSE terms restrict storing content "in an electronic retrieval system" without written permission. Until permission (or the owner's explicit decision), Phase 1 uses **synthetic fixtures only**, and no NSE files are ingested into snapshots.
- Membership reconciliation against published index levels (SPEC §9.2) depends on niftyindices.com data, which falls under the same access question.
