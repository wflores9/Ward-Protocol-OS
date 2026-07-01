"""Ward Protocol Python SDK Client."""

import httpx
from pydantic import ValidationError
from ward_protocol_pkg.models import Pool, PoolsResponse


class WardClient:

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def aclose(self):
        await self.client.aclose()

    async def get_pools(self) -> PoolsResponse:
        response = await self.client.get(f"{self.base_url}/pools")
        response.raise_for_status()
        return PoolsResponse.model_validate(response.json())

    async def get_pool(self, pool_id: str) -> Pool:
        response = await self.client.get(f"{self.base_url}/pools/{pool_id}")
        response.raise_for_status()
        return Pool.model_validate(response.json())



    async def get_quote(self, asset_in: str, asset_out: str, amount_in: float):
        """Get a swap quote for a given input amount."""
        from ward_protocol_pkg.models import QuoteResponse
        params = {"asset_in": asset_in, "asset_out": asset_out, "amount_in": amount_in}
        response = await self.client.get(f"{self.base_url}/quote", params=params)
        response.raise_for_status()
        return QuoteResponse.model_validate(response.json())

    async def swap(self, asset_in: str, asset_out: str, amount_in: float,
                   min_amount_out: float, wallet: str):
        """Execute a swap with slippage protection."""
        from ward_protocol_pkg.models import SwapResponse
        params = {
            "asset_in": asset_in,
            "asset_out": asset_out,
            "amount_in": amount_in,
            "min_amount_out": min_amount_out,
            "wallet": wallet,
        }
        response = await self.client.post(f"{self.base_url}/swap", params=params)
        response.raise_for_status()
        return SwapResponse.model_validate(response.json())


class WardClientSync:

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def get_pools(self) -> PoolsResponse:
        response = self.client.get(f"{self.base_url}/pools")
        response.raise_for_status()
        return PoolsResponse.model_validate(response.json())

    def get_pool(self, pool_id: str) -> Pool:
        response = self.client.get(f"{self.base_url}/pools/{pool_id}")
        response.raise_for_status()
        return Pool.model_validate(response.json())

    def close(self):
        self.client.close()
