# Stellar — Ward Protocol Integration Guide

## Overview

Stellar is a blockchain network optimized for payments and asset issuance, operated by the Stellar Development Foundation. Ward Protocol integrates Stellar via `StellarAdapter`, which reads account and trustline state via the Horizon API and builds unsigned Stellar payment operation XDR for RLUSD resolution settlements.

RLUSD on Stellar is a native Stellar asset (asset_code=RLUSD, asset_issuer=Ripple Stellar account). Pool accounts hold RLUSD via Stellar trustlines. Ward policy credentials are stored as Stellar account data entries (key-value pairs in account metadata).

## Stellar Key Facts

| Property | Value |
|---|---|
| Consensus | Stellar Consensus Protocol (SCP, federated BFT) |
| Native token | XLM |
| RLUSD | Stellar asset (issuer published at XLS-66 mainnet) |
| Finality | 3–5 seconds |
| Horizon (Mainnet) | `https://horizon.stellar.org` |
| Horizon (Testnet) | `https://horizon-testnet.stellar.org` |
| Explorer | `https://stellar.expert` |
| Amount precision | 7 decimal places (1 stroops = 0.0000001 XLM/asset) |

## StellarAdapter Architecture

`StellarAdapter` extends `ChainAdapter` and targets the Stellar Horizon REST API.

```python
from ward.adapters import StellarAdapter

adapter = StellarAdapter(
    horizon_url="https://horizon.stellar.org",
    rlusd_asset_code="RLUSD",
    rlusd_issuer="G<Ripple Stellar issuer account>",
    network_passphrase="Public Global Stellar Network ; September 2015",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read account data entries + RLUSD trustline balance |
| `get_ledger_state()` | Fetch ledger sequence + close time |
| `build_resolution_tx()` | Produce unsigned Stellar payment operation |

### Stellar Payment (unsigned)

```python
# Fetch latest ledger for sequence number
ledger = await adapter.get_ledger_state()

tx = await adapter.build_resolution_tx(
    pool_address="G<pool Stellar account>",
    claimant_address="G<claimant Stellar account>",
    payout_amount=5_000_000,  # 0.5 RLUSD = 5,000,000 stroops
    sequence_number=ledger.ledger_sequence,
    fee_stroops=100,
    memo="ward:resolution:claim-001",
)
assert tx.ward_signed is False  # invariant

payload = tx.send_max
assert payload["payment_type"] == "STELLAR_PAYMENT"
assert payload["asset_code"] == "RLUSD"
assert payload["ward_signed"] is False
```

## Resolution Flow

```
1. Ward oracle reads XRPL ledger state (vault default, pool balance)
        │
        ▼
2. Oracle writes verified state to Ward Stellar account data entries
   (ward:policy:<nftId>, ward:default:<loanId>, ward:pool:<poolId>)
        │
        ▼
3. Institution queries Horizon for account data, runs nine checks
        │
        ▼
4. Unsigned payment operation XDR returned
   (ward_signed = false always)
        │
        ▼
5. Institution signs XDR envelope with their keypair
        │
        ▼
6. Stellar network settles — RLUSD transferred via trustline
```

## Claimable Balance for Dispute Window

Ward uses Stellar claimable balances to enforce a dispute window:

```python
escrow = await adapter.build_unsigned_escrow_create(
    pool_address="G<pool>",
    claimant_address="G<claimant>",
    amount=5_000_000,
    condition_hex="ABCDEF",
)
# escrow["TransactionType"] == "EscrowCreate"
# escrow["asset_code"] == "RLUSD"
# escrow["ward_signed"] is False
```

Stellar claimable balances support time-based predicates (`ClaimPredicateBeforeRelativeTime`) that enforce the dispute window before RLUSD is claimable.

## Trustline Requirements

Before resolution, the claimant account must hold a RLUSD trustline:

```
ChangeTrust operation: asset=RLUSD, issuer=<Ripple Stellar issuer>, limit=<max>
```

Ward validates trustline existence in Step 6 (pool coverage check). Pool accounts must also hold the RLUSD trustline with sufficient balance × 1.5 coverage ratio.

## Security Notes

- `ward_signed = False` — institution signs XDR with their Ed25519 keypair
- Stellar ledger sequence required for transaction validity — always fetch fresh
- Trustline limits enforced at the network level — no double-spend possible
- Ward policy data entries are read-only during resolution (institutional signing required to update)
- Network passphrase must match the target network — prevents replay across networks

## Status

Implemented in `ward/adapters/stellar.py`. Stellar RLUSD issuer account pending Ripple deployment.
