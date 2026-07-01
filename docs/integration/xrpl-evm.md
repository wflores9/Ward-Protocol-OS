# XRPL EVM Sidechain — Ward Protocol Deployment Guide

## Overview

The XRPL EVM Sidechain is a fully EVM-compatible chain that settles to the XRPL ledger. It enables Solidity smart contracts to interact with XRPL assets — including RLUSD — without leaving the XRPL ecosystem.

Ward Protocol's Solidity port (`WardResolver.sol`) deploys the same nine-check deterministic resolution logic to the EVM layer. The contract is RLUSD-native, uses EVM-compatible types for all state, and enforces `ward_signed = false` at the contract level.

## XRPL EVM Sidechain Key Facts

| Property | Value |
|---|---|
| Chain ID (Testnet) | 1440002 |
| Chain ID (Mainnet) | 1440001 |
| Native token | XRP |
| RLUSD | ERC-20 at canonical address (published at XLS-66 mainnet launch) |
| RPC (Testnet) | `https://rpc-evm-sidechain.xrpl.org` |
| Explorer | `https://evm-sidechain.xrpl.org` |
| Bridge | XRPL ↔ EVM via Axelar cross-chain messaging |

## WardResolver Contract Architecture

`WardResolver.sol` implements the same nine checks as the Python SDK, adapted for EVM:

| Check | Python SDK | Solidity |
|---|---|---|
| 1. Policy NFT | `AccountNFTs` RPC | `_nftHolders` mapping + `_policies` registry |
| 2. Policy expiry | `get_ledger_close_time` | `block.timestamp` (EVM tracks XRPL ledger time) |
| 3. Vault binding | NFT URI metadata | `_policies[nftTokenId].vaultAddress` |
| 4. Default flag | `LedgerEntry` LSF_LOAN_DEFAULT | `_loanFlags[loanId] & LSF_LOAN_DEFAULT` |
| 5. Vault loss > 0 | `TotalValueOutstanding` | `_loanOutstanding[loanId]` |
| 6. Pool coverage | `AccountInfo` balance | `_poolBalances[poolAddress]` |
| 7. NFT live | `AccountNFTs` re-check | `!_burnedNFTs[nftTokenId]` |
| 8. Claimant holds NFT | `AccountNFTs` claimant | `_nftHolders[nftTokenId] == claimant` |
| 9. Pool solvency | Coverage ratio ≥ 1.5× | `usable >= payout * 150 / 100` |

### Core Invariant

```solidity
result.wardSigned = false; // invariant — never changes
```

`WardResolver` never calls `transfer()`, never holds a private key, never acts as a counterparty. `resolveClaimUnsigned()` is a `view` function — it cannot modify state or move funds.

## Deployment Steps

### 1. Prerequisites

```bash
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox
```

### 2. Configure Hardhat for XRPL EVM

```javascript
// hardhat.config.js
module.exports = {
  solidity: "0.8.20",
  networks: {
    xrplEvmTestnet: {
      url: "https://rpc-evm-sidechain.xrpl.org",
      chainId: 1440002,
      accounts: [process.env.DEPLOYER_PRIVATE_KEY],
    },
  },
};
```

### 3. Deploy WardResolver

```javascript
const WardResolver = await ethers.getContractFactory("WardResolver");
const resolver = await WardResolver.deploy(RLUSD_CONTRACT_ADDRESS);
await resolver.waitForDeployment();
console.log("WardResolver deployed at:", await resolver.getAddress());
```

### 4. Run Tests

```bash
npx hardhat test test/WardResolver.test.js
```

## How It Connects to XRPL Mainnet

Ward's resolution flow with XRPL EVM:

```
1. Vault defaults on XRPL mainnet (XLS-66 default flag set)
        │
        ▼
2. Ward oracle reads XRPL ledger state
   (AccountNFTs, LedgerEntry, AccountInfo)
        │
        ▼
3. Oracle writes verified state to WardResolver on XRPL EVM
   (registerPolicy, recordDefault, setPoolBalance)
        │
        ▼
4. Institution calls resolveClaimUnsigned() — view function, no gas for state
        │
        ▼
5. WardResolver runs nine on-chain checks, returns ResolutionResult
   (wardSigned = false always)
        │
        ▼
6. Institution signs the UnsignedEscrowPayload
        │
        ▼
7. RLUSD transferred on XRPL EVM — policy NFT burned for replay protection
```

## Security Notes

- `resolveClaimUnsigned()` is `view` — it cannot call `transfer()` or modify state
- `wardSigned` in `ResolutionResult` and `UnsignedEscrowPayload` is always `false`; it is not a constructor or function parameter — enforced at the type level
- Cross-vault claims are rejected at step 3 (vault binding check)
- Replay attacks are blocked at step 7 (NFT burn tracking)
- Rate limiting (step 9) is enforced per NFT token ID

## Status

Implemented in `contracts/WardResolver.sol`. Deployment pending XLS-66 mainnet launch and Ripple RLUSD ERC-20 publication on XRPL EVM.
