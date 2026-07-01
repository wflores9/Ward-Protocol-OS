from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class Pool(BaseModel):
    """Represents an XRPL-based AMM liquidity pool in Ward Protocol."""
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

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "pool_id": "AMM:1234567890ABCDEF",
                "asset1": "XRP",
                "asset2": "USD",
                "asset1_issuer": None,
                "asset2_issuer": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq",
                "tvl": 1245678.45,
                "volume_24h": 456789.12,
                "apr": 12.34,
                "fee_rate": 0.003,
                "created_at": "2026-02-25T03:49:17.997687",
                "last_updated": "2026-02-25T03:49:17.997691"
            }
        }
    )


class PoolsResponse(BaseModel):
    """Response model for the /pools endpoint."""
    pools: List[Pool]
    total: int
    timestamp: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "pools": [
                    {
                        "pool_id": "AMM:1234567890ABCDEF",
                        "asset1": "XRP",
                        "asset2": "USD",
                        "asset1_issuer": None,
                        "asset2_issuer": "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq",
                        "tvl": 1245678.45,
                        "volume_24h": 456789.12,
                        "apr": 12.34,
                        "fee_rate": 0.003,
                        "created_at": "2026-02-25T03:52:29.981923",
                        "last_updated": "2026-02-25T03:52:29.981928"
                    }
                ],
                "total": 2,
                "timestamp": "2026-02-25T03:52:29.983553"
            }
        }
    )


class QuoteResponse(BaseModel):
    asset_in: str
    asset_out: str
    amount_in: float
    amount_out: float
    fee: float
    fee_rate: float
    price_impact: float
    pool_id: str
    rate: float


class SwapResponse(BaseModel):
    status: str
    tx_hash: str
    wallet: str
    asset_in: str
    asset_out: str
    amount_in: float
    amount_out: float
    fee: float
    price_impact: float
    pool_id: str
    executed_at: str
