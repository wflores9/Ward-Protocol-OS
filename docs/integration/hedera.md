# Hedera — Ward Protocol Integration Guide

## Overview

Hedera is an enterprise-grade distributed ledger using Hashgraph consensus. Ward Protocol integrates Hedera via `HederaAdapter`, which reads Hedera Token Service (HTS) state via the Mirror Node REST API and builds unsigned TokenTransfer transactions for RLUSD resolution settlements.

Ward policy NFTs on Hedera are HTS non-fungible tokens. Pool accounts are Hedera accounts with RLUSD HTS token associations. Hedera's deterministic finality (~3–5 seconds) makes it well-suited for enterprise insurance settlement.

## Hedera Key Facts

| Property | Value |
|---|---|
| Consensus | Hashgraph (asynchronous Byzantine fault tolerant) |
| Native token | HBAR |
| RLUSD | HTS token (token ID published at XLS-66 mainnet) |
| Finality | ~3–5 seconds (deterministic) |
| Mirror Node (Mainnet) | `https://mainnet-public.mirrornode.hedera.com` |
| Mirror Node (Testnet) | `https://testnet.mirrornode.hedera.com` |
| Explorer | `https://hashscan.io` |

## HederaAdapter Architecture

`HederaAdapter` extends `ChainAdapter` and targets the Hedera Mirror Node REST API.

```python
from ward.adapters import HederaAdapter

adapter = HederaAdapter(
    mirror_node_url="https://mainnet-public.mirrornode.hedera.com",
    rlusd_token_id="0.0.<RLUSD token ID>",
    network="mainnet",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read HTS NFT metadata + pool token balance |
| `get_ledger_state()` | Fetch consensus timestamp + network state |
| `build_resolution_tx()` | Produce unsigned TokenTransfer payload |

### HTS TokenTransfer (unsigned)

```python
tx = await adapter.build_resolution_tx(
    pool_address="0.0.123456",
    claimant_address="0.0.789012",
    payout_amount=500_000_000,  # in HTS base units
    nonce=0,
)
assert tx.ward_signed is False  # invariant

payload = tx.send_max
assert payload["transfer_type"] == "HEDERA_CRYPTO_TRANSFER"
assert payload["ward_signed"] is False
```

## Resolution Flow

```
1. Ward oracle reads XRPL ledger state (vault default, pool balance)
        │
        ▼
2. Oracle writes verified state to Ward HTS contract on Hedera
   (registerPolicy, recordDefault, setPoolBalance via contract memo)
        │
        ▼
3. Institution calls Ward contract checkClaim — nine checks via Mirror Node
        │
        ▼
4. Unsigned TokenTransfer returned
   (ward_signed = false always)
        │
        ▼
5. Institution signs transaction with their ED25519/ECDSA keypair
        │
        ▼
6. Hedera consensus settles — RLUSD transferred, NFT burned for replay protection
```

## Hedera ScheduleCreate for Dispute Window

Ward uses Hedera's `ScheduleCreate` to enforce a dispute window:

```python
escrow = await adapter.build_unsigned_escrow_create(
    pool_address="0.0.123456",
    claimant_address="0.0.789012",
    amount=500_000_000,
    condition_hex="ABCDEF",
)
# escrow["TransactionType"] == "EscrowCreate"
# escrow["ward_signed"] is False
```

The institution submits `ScheduleCreate`; after the dispute window, `ScheduleSign` releases RLUSD.

## Security Notes

- `ward_signed = False` — institution signs with their ED25519/ECDSA keypair
- Hedera requires token association before transfer — pool must pre-associate RLUSD
- HTS NFTs are non-transferable Ward policies (isTransferable = false)
- Consensus timestamp used for Step 2 (policy expiry) — never system clock

## Status

Implemented in `ward/adapters/hedera.py`. Hedera RLUSD HTS token pending Ripple deployment.
