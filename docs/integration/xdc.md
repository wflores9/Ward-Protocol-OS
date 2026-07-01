# XDC Network — Ward Protocol Integration Guide

## Overview

XDC Network (XinFin) is an enterprise-grade EVM-compatible blockchain optimized for trade finance and cross-border payments. Ward Protocol deploys `WardResolver.sol` on XDC unchanged — the same nine-check deterministic resolution logic runs on XDC's EVM.

XDC uses a dual-address format: the same underlying bytes are displayed with an `xdc` prefix (rather than `0x`). Ward's adapter normalizes addresses internally for RPC calls.

## XDC Network Key Facts

| Property | Value |
|---|---|
| Chain ID (Mainnet) | 50 |
| Chain ID (Apothem Testnet) | 51 |
| Native token | XDC |
| EVM compatibility | Full (Solidity 0.8.x) |
| Address prefix | `xdc` (instead of `0x`) |
| RPC (Mainnet) | `https://rpc.xdc.org` |
| RPC (Testnet) | `https://erpc.apothem.network` |
| Explorer | `https://xdcscan.io` |
| RLUSD | ERC-20 via XinFin bridge from XRPL |

## XDCAdapter Architecture

`XDCAdapter` extends `ChainAdapter` and deploys the same `WardResolver.sol` used on XRPL EVM Sidechain and Flare.

```python
from ward.adapters import XDCAdapter

adapter = XDCAdapter(
    rpc_url="https://rpc.xdc.org",
    chain_id=50,
    ward_resolver="xdc<WardResolver address on XDC>",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read WardResolver state on XDC EVM |
| `get_ledger_state()` | Fetch block number and timestamp |
| `build_resolution_tx()` | Produce unsigned EVM call payload |

### XDC Resolution (unsigned)

```python
tx = await adapter.build_resolution_tx(
    pool_address="xdc<pool address>",
    claimant_address="xdc<claimant address>",
    payout_amount=500_000_000_000_000_000,  # 0.5 RLUSD in wei
    nonce=0,
)
assert tx.ward_signed is False  # invariant

payload = tx.send_max
assert payload["call_type"] == "XDC_EVM_CALL"
assert payload["chain_id"] == 50
assert payload["ward_signed"] is False
```

## Deployment Steps

### 1. Configure Hardhat for XDC

```javascript
// hardhat.config.js
networks: {
  xdcMainnet: {
    url: "https://rpc.xdc.org",
    chainId: 50,
    accounts: [process.env.DEPLOYER_PRIVATE_KEY],
  },
  apothem: {
    url: "https://erpc.apothem.network",
    chainId: 51,
    accounts: [process.env.DEPLOYER_PRIVATE_KEY],
  },
}
```

### 2. Deploy WardResolver

```bash
npx hardhat run scripts/deploy.js --network apothem
```

### 3. Resolution Flow

```
1. Ward oracle reads XRPL ledger state (vault default, pool balance)
        │
        ▼
2. Oracle writes verified state to WardResolver on XDC
   (registerPolicy, recordDefault, setPoolBalance)
        │
        ▼
3. Institution calls resolveClaimUnsigned() — view function
        │
        ▼
4. WardResolver runs nine on-chain checks, returns ResolutionResult
   (wardSigned = false always)
        │
        ▼
5. Institution signs the UnsignedEscrowPayload — RLUSD transferred on XDC
```

## XDC Address Normalization

XDC addresses use `xdc` prefix instead of `0x`. When calling XDC JSON-RPC:

```python
def normalize_xdc_address(addr: str) -> str:
    """Convert xdc-prefix to 0x-prefix for JSON-RPC calls."""
    if addr.startswith("xdc"):
        return "0x" + addr[3:]
    return addr
```

XDCAdapter handles this internally — callers may pass either format.

## Security Notes

- `wardSigned = false` — invariant enforced at the Solidity struct level
- `resolveClaimUnsigned()` is `view` — cannot modify state or transfer funds
- XDC address prefix is cosmetic — the underlying 20-byte address is identical to EVM
- Cross-vault claims rejected at Step 3 (vault binding check)
- Replay protection: NFT burn tracked in `_burnedNFTs` mapping

## Status

Implemented in `ward/adapters/xdc.py`. Deployment pending XLS-66 mainnet launch and XinFin RLUSD bridge publication.
