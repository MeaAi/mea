# Binance USD-M Futures Research Pilot

This branch contains a **public-data-only** acquisition and QA workflow. It does not use API keys, private endpoints, account data, or place orders.

## Run

1. Open the repository's **Actions** tab.
2. Select **Binance public-data research pilot**.
3. Choose **Run workflow** on branch `research/binance-data-pipeline`.
4. Keep the first run at `2024-01` / `2024-01` / `BTCUSDT`.
5. Download the `binance-orderflow-pilot` artifact after the run finishes.

The pilot is intentionally limited to at most two months and three symbols per run. Expand only after verifying the first artifact.

## Data

- Official Binance Vision USD-M monthly 1-minute klines
- Official Binance Vision USD-M monthly aggTrades
- SHA-256 checksum validation for each archive
- Per-minute aggressive buy/sell base and quote volume, trade counts, and configurable large-trade notional buckets
- Missing-minute and timestamp-unit QA

## Important limitations

- `isBuyerMaker=true` means the buyer was maker; the seller was taker (aggressive sell). `false` is classified as aggressive buy.
- Large trade threshold is a notional proxy per aggregate trade, not wallet/investor identity.
- This pilot is **data acquisition + feature construction + QA only**. It does not claim strategy profitability.
- It does not reconstruct historical L2 queue position or certify maker limit fills.
- Never add API keys or secrets; none are required.
