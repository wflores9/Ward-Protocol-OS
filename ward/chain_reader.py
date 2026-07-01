"""
Ward Protocol — chain_reader.py

Read-only XRPL ledger and account queries.
Provides low-level access to account info, balances, ledger entries,
and escrow objects.

Note: This is an infrastructure helper. The caller is responsible for
managing the AsyncWebsocketClient lifecycle (pass it in via constructor).
For higher-level on-chain reads, use ward.validator or ward.pool directly.
"""

from dataclasses import dataclass

from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.models.requests import AccountInfo, AccountObjects, AccountTx

from ward.primitives import LedgerError


@dataclass
class AccountBalance:
    """Account balance result."""

    address: str
    balance_drops: int
    sequence: int

    @property
    def balance_xrp(self) -> float:
        return self.balance_drops / 1_000_000


@dataclass
class EscrowInfo:
    """Escrow object info."""

    sequence: int
    amount_drops: int
    destination: str
    finish_after: str
    cancel_after: str
    owner: str


class ChainReader:
    """
    Read-only XRPL chain access for Ward Protocol.

    Requires an AsyncWebsocketClient for queries.
    The caller manages the connection lifecycle.
    """

    def __init__(self, client: AsyncWebsocketClient) -> None:
        self.client = client

    async def get_account_balance(self, address: str) -> AccountBalance:
        """
        Get XRP balance and sequence for an address.

        Args:
            address: XRPL classic address

        Returns:
            AccountBalance with balance_drops and sequence

        Raises:
            LedgerError: if AccountInfo request fails
        """
        request = AccountInfo(account=address)
        response = await self.client.request(request)
        if not response.is_successful():
            raise LedgerError(f"AccountInfo failed for {address}: {response.result}")
        data = response.result["account_data"]
        return AccountBalance(
            address=address,
            balance_drops=int(data["Balance"]),
            sequence=data.get("Sequence", 0),
        )

    async def verify_account_exists(self, address: str) -> bool:
        """
        Check if an XRPL account exists (has been funded).

        Returns:
            True if account exists, False if unfunded
        """
        try:
            await self.get_account_balance(address)
            return True
        except LedgerError:
            return False

    async def get_account_objects(
        self,
        address: str,
        obj_type: str | None = None,
    ) -> list:
        """
        Get all objects owned by an account.

        Args:
            address:  XRPL classic address
            obj_type: optional ledger-object type filter (e.g. "escrow", "nft_page")

        Returns:
            List of raw ledger-object dicts

        Raises:
            LedgerError: if AccountObjects request fails
        """
        kwargs: dict = {"account": address}
        if obj_type:
            kwargs["type"] = obj_type
        request = AccountObjects(**kwargs)
        response = await self.client.request(request)
        if not response.is_successful():
            raise LedgerError(f"AccountObjects failed for {address}: {response.result}")
        return response.result.get("account_objects", [])

    async def get_escrows(self, address: str) -> list[EscrowInfo]:
        """
        Get all escrow objects for an account.

        Args:
            address: Owner address

        Returns:
            List of EscrowInfo
        """
        objs = await self.get_account_objects(address, obj_type="escrow")
        escrows = []
        for obj in objs:
            if obj.get("LedgerEntryType") != "Escrow":
                continue
            escrows.append(
                EscrowInfo(
                    sequence=obj.get("Sequence", 0),
                    amount_drops=int(obj.get("Amount", 0)),
                    destination=obj.get("Destination", ""),
                    finish_after=str(obj.get("FinishAfter", "")),
                    cancel_after=str(obj.get("CancelAfter", "")),
                    owner=obj.get("Account", address),
                )
            )
        return escrows

    async def get_account_transactions(
        self,
        address: str,
        limit: int = 20,
    ) -> list:
        """
        Get recent transactions for an account.

        Args:
            address: XRPL classic address
            limit:   max transactions to return (default 20)

        Returns:
            List of transaction dicts

        Raises:
            LedgerError: if AccountTx request fails
        """
        request = AccountTx(account=address, limit=limit)
        response = await self.client.request(request)
        if not response.is_successful():
            raise LedgerError(f"AccountTx failed for {address}: {response.result}")
        return response.result.get("transactions", [])
