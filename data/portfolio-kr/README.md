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

When KRX refuses a request (HTTP 401/403), the run checks the key on a session KRX has always
served (2010-01-04). If that succeeds, only the new day is refused: the run keeps the verified
VKOSPI history, warns, and collects the day on a later schedule. If that is refused too, the key
itself is refused: prices still publish while VKOSPI lags at most three sessions, and the run
fails after publishing with the provider's status and message and the key fingerprint. KRX's
message names the fix: `Unauthorized Key` means KRX does not know the value (replace the secret);
`Unauthorized API Call` means KRX knows the key but refuses the service (check the approval on
openapi.krx.co.kr; the secret stays). KRX supplies only indices here (VKOSPI, and KOSPI200 for the
V1 score); prices come from Yahoo. Set the repository variable
`KRX_API_KEY_EXPIRES` (YYYY-MM-DD, from openapi.krx.co.kr) to fail the run 14 days before expiry.
