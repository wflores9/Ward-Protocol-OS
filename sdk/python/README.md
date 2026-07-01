# Ward Protocol Python SDK

Official Python SDK for [Ward Protocol](https://github.com/ward-protocol) — XRPL AMM DeFi.

Query live AMM pools, get swap quotes, and execute trades on the XRP Ledger.

## Installation
```bash
pip install -e .
```

## Quick Start
```python
import asyncio
from ward_protocol_pkg.client import WardClient

async def main():
    async with WardClient() as client:

        # List all AMM pools
        pools = await client.get_pools()
        for pool in pools.pools:
            print(f"{pool.asset1}/{pool.asset2}  TVL=${pool.tvl:,.2f}  APR={pool.apr}%")

        # Get a swap quote
        quote = await client.get_quote("XRP", "USD", amount_in=100)
        print(f"100 XRP → {quote.amount_out} USD  (rate={quote.rate}, impact={quote.price_impact}%)")

        # Execute a swap
        result = await client.swap(
            asset_in="XRP",
            asset_out="USD",
            amount_in=100,
            min_amount_out=95,   # slippage tolerance
            wallet="rYourWalletAddress"
        )
        print(f"Swap {result.status}: tx={result.tx_hash}")

asyncio.run(main())
```

## API Reference

### `WardClient(base_url, timeout)`

Async HTTP client for the Ward Protocol API.

| Method | Description |
|--------|-------------|
| `get_pools()` | Returns all active AMM liquidity pools |
| `get_pool(pool_id)` | Returns a single pool by ID |
| `get_quote(asset_in, asset_out, amount_in)` | Returns a swap quote using x*y=k formula |
| `swap(asset_in, asset_out, amount_in, min_amount_out, wallet)` | Executes a swap with slippage protection |

## REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/pools` | List all AMM pools |
| GET | `/pools/{pool_id}` | Get pool by ID |
| GET | `/quote?asset_in=XRP&asset_out=USD&amount_in=100` | Get swap quote |
| POST | `/swap?asset_in=XRP&asset_out=USD&amount_in=100&min_amount_out=95&wallet=r...` | Execute swap |

## Example Responses

### GET /pools
```json
{
  "pools": [
    {
      "pool_id": "AMM:rGrbBvT3rEJKP65pvZK55Hy5zzPgQZV8e3",
      "asset1": "XRP",
      "asset2": "USD",
      "tvl": 1025.00,
      "fee_rate": 0.003,
      "apr": 0.0
    }
  ],
  "total": 1
}
```

### GET /quote
```json
{
  "asset_in": "XRP",
  "asset_out": "USD",
  "amount_in": 10.0,
  "amount_out": 9.779748,
  "fee": 0.03,
  "fee_rate": 0.003,
  "price_impact": 1.9512,
  "pool_id": "AMM:rGrbBvT3rEJKP65pvZK55Hy5zzPgQZV8e3",
  "rate": 0.977975
}
```

## XRPL Integration

The SDK connects to the XRP Ledger testnet by default:

- **Network:** XRPL Testnet (`s.altnet.rippletest.net`)
- **Live pool:** `AMM:rGrbBvT3rEJKP65pvZK55Hy5zzPgQZV8e3` (XRP/USD)
- **Data source:** Real-time `amm_info` ledger queries
- **Fallback:** Mock data if ledger is unreachable

To use mainnet, set the `XRPL_WEBSOCKET_URL` in your `.env`:
```bash
XRPL_WEBSOCKET_URL=wss://xrplcluster.com
```

## Development
```bash
# Clone and install
git clone https://github.com/ward-protocol/ward-protocol
cd ward-protocol/sdk/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the API server
python3 -m uvicorn sdk.python.main:app --reload --port 8000

# Run tests
pytest
```

## Requirements

- Python 3.10+
- httpx >= 0.25.0
- pydantic >= 2.5.0
- xrpl-py >= 4.0.0

## License

MIT — see [LICENSE](LICENSE)
