# Korean portfolio inputs

GitHub Actions `refresh-korea-portfolio.yml` collects and validates these inputs.
`current.json` points to an immutable, SHA-256-verified snapshot and provider receipts.
The deployed API reads the files copied into its image; it never collects prices.

Prices use the existing 23 Korean stock/ETF universe and Yahoo adjusted closes.
Risk factors use KRX VKOSPI and ECOS Korea Treasury 10Y. Nothing is filled. A KRX
session where Yahoo lacks a listed asset's close is excluded from prices.csv and listed
in `collection.excluded_price_sessions`; publication stops if over 5% of sessions or the
latest session are affected. Missing factor days stay blank. Price and risk observation
dates are separate.
The GitHub source is this repository's `main`, under `data/portfolio-kr`.
