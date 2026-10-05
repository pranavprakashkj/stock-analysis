# ADR-009: Paper runtime: Docker Compose locally, deployment-agnostic; replaceable AlertProvider

## Status
Accepted (owner, 2026-09-30). Continuous-deployment host deliberately not chosen yet.

## Date
2026-09-30

## Context
- Paper trading must eventually run every NSE trading day, including special sessions.
- The owner does not want to choose a paid cloud host yet.
- Alerts must not tie domain logic to a specific channel (Telegram, Slack, etc.).

## Decision
1. **Development:** run locally via **Docker Compose** (runner, API, dashboard as services; data and SQLite on named volumes).
2. **Deployment-agnostic runtime:** the runner is a CLI command, idempotent per trading date,
   configured only through environment variables and mounted config. No host-specific code.
   Any scheduler (cron, launchd, systemd timer, a container scheduler) can invoke it.
3. **Data readiness:** poll for the day's input with backoff until a deadline; if missing, raise a data-quality alert and exit without trading.
4. **Catch-up:** process unprocessed trading dates strictly in order; orders older than one session expire (ADR-003).
5. **Alerts:** an application-layer port

   ```python
   class AlertProvider(Protocol):
       def send(self, alert: Alert) -> None: ...   # Alert: severity, kind, message, trading_date, run_id
   ```

   Initial implementation: **`LogAlertProvider`**, which writes structured alert records to the log
   and to an alerts table the dashboard displays. Other channels are later adapters. Domain code
   never references an alert channel; it emits domain events that the application layer maps to alerts.
6. Alert kinds: run failure, data missing past deadline, data-quality failure, kill-switch trigger,
   stuck position, risk-blocked manual order, catch-up in progress.

## Alternatives Considered
| Option | Status |
|---|---|
| Laptop (launchd) | Acceptable for development; missed days are handled by catch-up and counted as incidents |
| Always-on home machine | Candidate for first continuous deployment (**open**) |
| Paid VPS | Deferred by owner |
| Managed cron (e.g. CI scheduler) | Poor fit for a stateful ledger |

## Rationale
An idempotent CLI plus ordered catch-up makes the runtime portable and robust to missed schedules.

## Consequences
- Log-only alerts are easy to miss. Until a push channel is added, a missed alert counts as an operational risk for Gate B.
- If later exposed beyond localhost, the API/dashboard need authentication and TLS first.
