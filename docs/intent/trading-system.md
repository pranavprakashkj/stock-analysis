# Statement of Intent: NSE Systematic Trading System

Confirmed: 2026-09-30 (interview-me, explicit "yes" with one refinement)

- **Outcome:** A systematic, reproducible trading system for NSE equities whose strategies are
  judged against criteria justified and locked *before* final evaluation, that reports failure
  plainly instead of optimising until it passes, and that runs in paper trading as the first
  real-world deployment stage before any real-money use.
- **User:** The owner, as sole operator, eventually trading their own account.
- **Why now:** Evidence, not intuition or model hype, before committing capital. Laya and
  Claude must earn inclusion through ablation against a baseline.
- **Success:**
  - A strategy either passes or clearly fails the locked Backtest → Paper criteria
    (profitability, risk, consistency, robustness, realistic costs).
  - Paper trading runs reliably with two separately measured tracks: *algorithm-only* and
    *live paper* (algorithm + manual interventions).
  - The system reports whether the locked Paper → Real-money criteria are met.
- **Constraints:**
  - Free market data only during development and research, behind a replaceable adapter.
  - Starting capital is a configuration parameter, evaluated across several capital levels.
  - The core strategy works and is testable without Laya or Claude.
  - Strong typing; business logic separated from I/O; simple over clever.
- **Manual controls (paper trading only):** veto a generated trade, pause a stock, pause the
  strategy, emergency pause-all, manually close a position, optionally add a manual trade.
  - Every manual action is recorded separately from algorithmic decisions and is never
    attributed to the strategy.
  - The dashboard distinguishes: Algorithm decision → Manual intervention → Final paper order.
  - Manual actions never modify the strategy or backtest results.
- **Hard risk limits apply to everyone, including manual trades:** no leverage, no shorting,
  max per-stock position weight, max portfolio exposure, sufficient available cash, position
  and order size limits. Invalid or unsafe orders are **blocked, not warned**. Manual
  intervention may override the *strategy*, never the *portfolio risk controls*.
- **Out of scope (V1):** real-money execution and broker order placement; F&O, shorting,
  leverage, intraday; multiple users/auth; Claude or Laya deciding trades; optimise-until-pass
  workflows; full merger/demerger modelling (affected stocks are flagged and exited).
