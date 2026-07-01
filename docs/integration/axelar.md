# Axelar GMP — Ward Protocol Integration Guide

## Overview

Axelar General Message Passing (GMP) is a cross-chain communication protocol secured by a decentralized validator network. Ward Protocol uses Axelar GMP as a transport layer to relay verified resolution payloads from the XRPL EVM Sidechain (or Flare) to any Axelar-connected chain.

No token wrapping occurs — RLUSD remains canonical on the source chain. The GMP message instructs a Ward-deployed `IAxelarExecutable` contract on the destination chain to execute the settlement.

## Axelar GMP Key Facts

| Property | Value |
|---|---|
| Security model | Proof-of-stake validator set (75+ validators) |
| Connected chains | 50+ EVM and non-EVM chains |
| Transport | `callContract` / `callContractWithToken` |
| Fee model | Gas paid on source chain in source native token |
| RLUSD handling | Source-chain canonical — no wrapping |

## AxelarAdapter Architecture

`AxelarAdapter` extends `ChainAdapter` and manages two RPC endpoints:

- **Source chain**: XRPL EVM Sidechain or Flare (where WardResolver.sol lives)
- **Destination chain**: Any Axelar-connected chain (Ethereum, Polygon, etc.)

```python
from ward.adapters import AxelarAdapter

adapter = AxelarAdapter(
    source_rpc_url="https://rpc-evm-sidechain.xrpl.org",
    source_chain="xrpl-evm",
    dest_chain="ethereum",
    gateway_address="0x<Axelar Gateway on XRPL EVM>",
    dest_contract="0x<Ward IAxelarExecutable on Ethereum>",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read WardResolver on source chain |
| `get_ledger_state()` | Fetch cross-chain state + Axelar fee estimate |
| `build_resolution_tx()` | Produce unsigned Gateway.callContract payload |
| `send_resolution_message()` | Serialise GMP payload dict for institution dispatch |

## Resolution Flow

```
1. Ward oracle writes verified state to WardResolver on XRPL EVM
        │
        ▼
2. Institution calls resolveClaimUnsigned() — nine checks pass
        │
        ▼
3. Institution signs Gateway.callContract(destChain, destContract, payload)
   (ward_signed = false — Ward never signs)
        │
        ▼
4. Axelar Validators relay the GMP message cross-chain
        │
        ▼
5. Destination IAxelarExecutable.execute() called — RLUSD settlement
```

## Building a GMP Message

```python
# 1. Verify claim on source chain
vault_state = await adapter.verify_vault(
    vault_address="0x<vault>",
    loan_id="0x<loan>",
    pool_address="0x<pool>",
)

# 2. Build unsigned GMP tx
tx = await adapter.build_resolution_tx(
    pool_address="0x<pool>",
    claimant_address="0x<claimant>",
    payout_amount=500_000_000_000_000_000,  # 0.5 RLUSD in wei
    dest_chain="ethereum",
    nonce=42,
)
assert tx.ward_signed is False  # invariant

# 3. Get serialised GMP payload for institution dispatch
gmp_msg = await adapter.send_resolution_message(
    pool_address="0x<pool>",
    claimant_address="0x<claimant>",
    payout_amount=500_000_000_000_000_000,
    nonce=42,
)
# Institution ABI-encodes and calls Gateway.callContract(gmp_msg)
```

## IAxelarExecutable Contract

Ward deploys a minimal `IAxelarExecutable` on each destination chain:

```solidity
contract WardAxelarExecutable is IAxelarExecutable {
    function _execute(
        string calldata sourceChain,
        string calldata sourceAddress,
        bytes calldata payload
    ) internal override {
        // Decode Ward resolution payload
        // Transfer RLUSD to claimant
        // ward_signed is never set — institution signed the Gateway call
    }
}
```

## Security Notes

- `ward_signed = False` — only the institution signs the Gateway call
- Axelar Validators provide independent attestation — Ward is not the sole trust anchor
- Cross-chain replay protection: GMP nonce + NFT burn on source chain
- Fee must be paid on source chain; zero-fee messages are rejected by Gateway

## Status

Implemented in `ward/adapters/axelar.py`. Deployment pending XLS-66 mainnet launch and Axelar XRPL EVM integration.
