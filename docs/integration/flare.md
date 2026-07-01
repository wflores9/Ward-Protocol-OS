# Flare Network — Ward Protocol Integration Guide

## Overview

Flare Network is a fully EVM-compatible Layer 1 blockchain with a native State Connector and FTSO (Flare Time Series Oracle) for trustless off-chain data. Ward Protocol deploys `WardResolver.sol` on Flare unchanged — the same nine-check deterministic resolution logic runs on Flare's EVM.

The FTSO provides chain-native RLUSD price data without external oracle dependency, making Flare a strong settlement layer for RLUSD-denominated insurance claims.

## Flare Network Key Facts

| Property | Value |
|---|---|
| Chain ID (Mainnet) | 14 |
| Chain ID (Coston2 Testnet) | 114 |
| Native token | FLR |
| EVM compatibility | Full (Solidity 0.8.x) |
| RPC (Mainnet) | `https://flare-api.flare.network/ext/C/rpc` |
| RPC (Testnet) | `https://coston2-api.flare.network/ext/C/rpc` |
| Explorer | `https://flare-explorer.flare.network` |
| FTSO | Native price oracle — no external dependency |

## FlareAdapter Architecture

`FlareAdapter` extends `ChainAdapter` and deploys the same `WardResolver.sol` used on XRPL EVM Sidechain.

```python
from ward.adapters import FlareAdapter

adapter = FlareAdapter(
    rpc_url="https://flare-api.flare.network/ext/C/rpc",
    chain_id=14,
    ward_resolver="0x<WardResolver address on Flare>",
)
```

### Ward-Specific Methods

| Method | Purpose |
|---|---|
| `verify_vault()` | Read WardResolver state on Flare EVM |
| `get_ledger_state()` | Fetch block + FTSO epoch snapshot |
| `build_resolution_tx()` | Produce unsigned EVM call payload |

### FTSO Price Anchoring

```python
state = await adapter.get_ledger_state()
# state.rlusd_price_usd — 5-decimal fixed point FTSO price
# e.g. 100000 = $1.00 RLUSD/USD
```

FTSO prices are finalized every epoch (~90 seconds) with Schelling-point aggregation across 100+ independent price providers. No single provider can manipulate the price.

## Deployment Steps

### 1. Deploy WardResolver on Flare

```javascript
// hardhat.config.js — add Flare networks
networks: {
  flareMainnet: {
    url: "https://flare-api.flare.network/ext/C/rpc",
    chainId: 14,
    accounts: [process.env.DEPLOYER_PRIVATE_KEY],
  },
  coston2: {
    url: "https://coston2-api.flare.network/ext/C/rpc",
    chainId: 114,
    accounts: [process.env.DEPLOYER_PRIVATE_KEY],
  },
}
```

```bash
npx hardhat run scripts/deploy.js --network coston2
```

### 2. Configure FlareAdapter

```python
adapter = FlareAdapter(
    rpc_url="https://coston2-api.flare.network/ext/C/rpc",
    chain_id=114,
    ward_resolver="0x<deployed address>",
)
```

### 3. Resolution Flow

```
1. Ward oracle reads XRPL ledger state (vault default, pool balance)
        │
        ▼
2. Oracle writes verified state to WardResolver on Flare
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
5. Institution signs the UnsignedEscrowPayload — RLUSD transferred on Flare
```

## Security Notes

- `wardSigned = false` — invariant enforced at the Solidity struct level
- FTSO prices use Schelling-point aggregation — manipulation-resistant
- `resolveClaimUnsigned()` is `view` — cannot modify state or transfer funds
- Cross-vault claims rejected at Step 3 (vault binding check)

## Status

Implemented in `ward/adapters/flare.py`. Deployment pending Flare RLUSD bridge publication.
