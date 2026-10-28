# Alpha Sight — Public Strategy Performance

Streamlit dashboard for normalized live-strategy performance versus Nasdaq 100.

- Formal trading starts on **2026-10-13**.
- The **2026-10-12 close** is the opening baseline, so the first formal trading day's return is included.
- Earlier small-capital trading is excluded from every return and risk metric.
- Historical strategy performance uses official IBKR TWR. Broker API estimates are explicitly marked and can be hidden.
- Public data contains only dates, normalized strategy/index values, and source-quality flags. No account balances, holdings, executions, personal identifiers, or access credentials are published.

## Run locally

```sh
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy

Deploy `streamlit_app.py` from the `main` branch through Streamlit Community Cloud. No secrets are required; the app reads a public, allowlisted performance endpoint. The local collector now reads the existing TradingView IBKR account panel; official daily performance/cash/execution history uses IBKR Flex HTTPS. TWS and Gateway are not required. TradingView NDX reference prices may be delayed; completed daily bars prefer the official MCP cache with an explicitly labelled Yahoo backup for missing dates. Account uploads stop on stale/incomplete reads and resume after fresh complete reads. Public data continues to exclude private account details.
