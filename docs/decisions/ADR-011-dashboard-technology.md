# ADR-011: Dashboard: React + TypeScript + Vite, an operational interface over the validated API

## Status
Accepted (owner, 2026-09-30)

## Date
2026-09-30

## Context
- The dashboard monitors the paper portfolio and strategy and hosts manual controls (ADR-014).
- Manual controls make it a write path that must be validated and risk-checked.

## Decision
1. **React + TypeScript + Vite.**
2. The dashboard is an **operational interface, not the location of business logic**. It holds no
   rules about risk, sizing, eligibility or P&L. It displays what the API returns and submits commands.
3. It communicates **only through the validated API**: query endpoints for reads; command endpoints
   (→ `interventions` → `risk`) for controls. It has no direct access to storage or files.
4. API request/response types are generated from the FastAPI OpenAPI schema, so the TypeScript contract cannot drift from the backend.
5. It displays, per trade: **Algorithm decision → Manual intervention → Final paper order**, and shows
   risk-block reasons returned by the API verbatim.
6. The emergency pause is also available as a CLI command, so it works if the UI is down.

## Alternatives Considered
- **Streamlit:** fastest, but weak for multi-step command flows and typed contracts.
- **Server-rendered HTML + htmx:** simple, but weaker typing and charting.

## Rationale
Typed, generated contracts plus logic-free UI keep all enforcement in the domain.

## Consequences
- A Node toolchain is added in the dashboard phase only.
- Browser testing and accessibility constraints activate in that phase (CONSTRAINTS deferred dimensions).
