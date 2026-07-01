# Wormhole NTT Integration — Ward Protocol

## Overview

Wormhole Native Token Transfers (NTT) is a standard for moving tokens across chains without wrapping. Unlike bridged assets, NTT transfers preserve the original token issuer's canonical representation on every connected chain.

Ward uses NTT to enable cross-chain RLUSD resolution — the same deterministic 9-check validation, applied to claims where the collateral lives on one chain and the payout is denominated in RLUSD on another.

**Key property**: No wrapped RLUSD. No synthetic representation. The RLUSD issuer retains full control.

## How Ward Uses Wormhole NTT

### The Problem

Standard Ward resolution is single-chain: the pool and the claimant are both on XRPL, and the escrow settles natively. When collateral is denominated in one asset (e.g. XRP) but the payout is owed in RLUSD on a destination chain (e.g. Ethereum), a cross-chain path is required.

### The Solution

`WormholeNTTAdapter` implements the `ChainAdapter` interface and adds three resolution-specific methods:

1. **`verify_vault()`** — Confirms vault state on the source chain. Reads default flag, outstanding loss, and pool balance directly from ledger state. No off-chain data is trusted.

2. **`get_ledger_state()`** — Returns a cross-chain state snapshot: source chain time, destination chain block, current Wormhole Guardian set index, and RLUSD pool balance.

3. **`build_resolution_tx()`** — Produces an unsigned NTT transfer payload. `ward_signed = False` always. The institution signs; Wormhole Guardians attest; the destination chain settles.

### Resolution Flow

```
Vault defaults on XRPL
        │
        ▼
verify_vault() ──► VaultState (is_defaulted, outstanding_drops, pool_balance)
        │
        ▼
get_ledger_state() ──► LedgerState (path_available, guardian_set_index, ...)
        │
        ▼
build_resolution_tx() ──► UnsignedTransaction (NTT payload, ward_signed=False)
        │
        ▼
Institution signs NTT transfer
        │
        ▼
Wormhole Guardians attest
        │
        ▼
Destination chain settles — RLUSD delivered, issuer control preserved
```

### Core Invariant

```python
ward_signed = False  # always
```

Ward never holds a signing key. Ward never submits a transaction. The adapter produces unsigned payloads — the institution signs on both the source chain and the destination chain.

## Integration Steps for Institutions

### 1. Instantiate the Adapter

```python
from ward.adapters import WormholeNTTAdapter

adapter = WormholeNTTAdapter(
    source_rpc_url="https://xrplcluster.com/",  # XRPL Mainnet
    dest_chain_id=2,                             # Wormhole chain ID: Ethereum
    dest_rpc_url="https://eth-mainnet.rpc.url",
    ntt_contract="0xYourNTTManagerContract",
)
```

### 2. Verify the Vault

```python
vault_state = await adapter.verify_vault(
    vault_address="rVaultAddress...",
    loan_id="A" * 64,
    pool_address="rPoolAddress...",
)

if not vault_state.is_defaulted:
    raise ValueError("Vault has not defaulted — no resolution required")
```

### 3. Check Cross-Chain State

```python
ledger_state = await adapter.get_ledger_state()

if not ledger_state.path_available:
    # Handle partial resolution — no liquid NTT path at current ledger close
    ...
```

### 4. Build and Sign the Resolution Transaction

```python
unsigned_tx = await adapter.build_resolution_tx(
    pool_address="rPoolAddress...",
    claimant_address="0xClaimantEVMAddress...",
    payout_drops=vault_state.outstanding_drops,
    dest_chain_id=2,
    nonce=ledger_state.dest_chain_block,
)

# ward_signed is always False — institution signs here
assert unsigned_tx.ward_signed is False
institution_wallet.sign_and_submit(unsigned_tx)
```

## Wormhole NTT Standard Reference

- NTT transfers do not wrap tokens — the canonical issuer representation is preserved
- Each transfer is attested by the Wormhole Guardian network (19-of-19 multisig)
- Replay protection: each transfer has a unique nonce; Guardians reject duplicates
- RLUSD Wormhole chain IDs: XRPL = 25, Ethereum = 2, Solana = 1

## Status

Implemented as `WormholeNTTAdapter` in `ward/adapters/wormhole.py`.
Mainnet deployment pending XLS-66 launch and Ripple RLUSD NTT contract publication.
