"""
XRPL AMM pool fetcher - pulls live data from the ledger.
Falls back to mock data if ledger is unreachable.
"""

import asyncio
import httpx
from datetime import datetime
from typing import List
from pydantic import BaseModel
from typing import Optional


class Pool(BaseModel):
    pool_id: str
    asset1: str
    asset2: str
    asset1_issuer: Optional[str] = None
    asset2_issuer: Optional[str] = None
    tvl: float
    volume_24h: float
    apr: float
    fee_rate: float
    created_at: datetime
    last_updated: datetime


class PoolListResponse(BaseModel):
    pools: List[Pool]
    total: int


# Known AMM pools to monitor
KNOWN_POOLS = [
    {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": "USD", "issuer": "rqL4w3MHBS6xsZmfmfZg4sDSFi5Dd3NSz"},
        "asset1_name": "XRP",
        "asset2_name": "USD",
        "asset1_issuer": None,
        "asset2_issuer": "rqL4w3MHBS6xsZmfmfZg4sDSFi5Dd3NSz",
    }
]

XRPL_RPC = "https://s.altnet.rippletest.net:51234"


async def fetch_amm_pool(pool_config: dict) -> Pool:
    """Fetch live AMM pool data from XRPL ledger."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(XRPL_RPC, json={
            "method": "amm_info",
            "params": [{"asset": pool_config["asset"], "asset2": pool_config["asset2"]}]
        })
        data = resp.json().get("result", {})

    amm = data.get("amm", {})
    if not amm:
        raise ValueError("AMM not found on ledger")

    # Parse reserves
    xrp_drops = int(amm.get("amount", 0))
    xrp_reserve = xrp_drops / 1_000_000

    usd_data = amm.get("amount2", {})
    usd_reserve = float(usd_data.get("value", 0)) if isinstance(usd_data, dict) else float(usd_data) / 1_000_000

    # TVL: XRP side + USD side (assuming ~1 XRP = $0.50 for testnet)
    xrp_price = 0.50
    tvl = (xrp_reserve * xrp_price) + usd_reserve

    fee_rate = amm.get("trading_fee", 300) / 1_000_000 * 100  # basis points to decimal... actually /1000
    fee_rate = amm.get("trading_fee", 300) / 100000  # 300 = 0.3%

    now = datetime.utcnow()

    return Pool(
        pool_id=f"AMM:{amm['account']}",
        asset1=pool_config["asset1_name"],
        asset2=pool_config["asset2_name"],
        asset1_issuer=pool_config["asset1_issuer"],
        asset2_issuer=pool_config["asset2_issuer"],
        tvl=round(tvl, 2),
        volume_24h=0.0,   # not available via amm_info, needs tx history
        apr=0.0,          # calculated from volume, placeholder for now
        fee_rate=fee_rate,
        created_at=now,
        last_updated=now,
    )


def get_all_pools() -> List[Pool]:
    """Fetch all known AMM pools. Falls back to mock data on error."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _fetch_all())
                return future.result(timeout=15)
        else:
            return loop.run_until_complete(_fetch_all())
    except Exception as e:
        print(f"⚠️  XRPL fetch failed ({e}), using mock data")
        return _mock_pools()


async def _fetch_all() -> List[Pool]:
    pools = []
    for config in KNOWN_POOLS:
        try:
            pool = await fetch_amm_pool(config)
            pools.append(pool)
        except Exception as e:
            print(f"⚠️  Failed to fetch pool {config['asset1_name']}/{config['asset2_name']}: {e}")
    return pools if pools else _mock_pools()


def _mock_pools() -> List[Pool]:
    now = datetime.utcnow()
    return [
        Pool(
            pool_id="AMM:1234567890ABCDEF",
            asset1="XRP", asset2="USD",
            asset1_issuer=None,
            asset2_issuer="rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq",
            tvl=1245678.45, volume_24h=456789.12,
            apr=12.34, fee_rate=0.003,
            created_at=now, last_updated=now,
        ),
        Pool(
            pool_id="AMM:ABCDEF1234567890",
            asset1="BTC", asset2="ETH",
            asset1_issuer="rBTCissuer...",
            asset2_issuer="rETHissuer...",
            tvl=987654.32, volume_24h=234567.89,
            apr=8.76, fee_rate=0.0025,
            created_at=now, last_updated=now,
        ),
    ]
