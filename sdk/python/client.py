"""Ward Protocol Python SDK Client."""

import httpx
from models import Pool, PoolsResponse


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
