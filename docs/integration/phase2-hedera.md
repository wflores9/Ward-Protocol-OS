# Phase 2 — Ward Protocol on Hedera

**Chain:** Hedera (EVM + HCS + HTS)  
**Priority:** High  
**Grant:** Hedera Foundation — hedera.org/grants  
**Status:** Planning

---

## Overview

Hedera provides three primitives that map directly to Ward Protocol's architecture:

| Ward (XRPL) | Hedera Equivalent |
|---|---|
| XLS-20 NFT (policy) | HTS Non-Fungible Token |
| XLS-66 loan vault | EVM smart contract (Solidity) |
| XRPL escrow | Solidity PREIMAGE-SHA-256 contract |
| VaultMonitor WebSocket | HCS mirror node topic subscription |
| `ClaimValidator` (Python) | Solidity `WardClaimValidator` contract |

---

## Prerequisites

- Hedera testnet account + HBAR for gas
- Hedera SDK: `@hashgraph/sdk` (TypeScript) or `hedera-sdk-py` (Python)
- Solidity ≥ 0.8.20
- Hardhat or Foundry for contract development
- Access to HCS mirror node: `hcs.mainnet.mirrornode.hedera.com`
- Ward Protocol SDK v0.2.5 (reference implementation)

---

## Architecture

```
Institution (signing key)
        |
        v
  WardClient (Hedera)
  ┌─────────────────────────────────────────┐
  │  1. purchaseCoverage()                  │
  │     - HTS NFT mint (non-transferable)   │
  │     - Premium payment (HBAR or USDC)    │
  │                                         │
  │  2. VaultMonitor (HCS)                  │
  │     - Subscribe to HCS topic            │
  │     - Mirror node stream                │
  │     - 3-block confirmation              │
  │                                         │
  │  3. WardClaimValidator (Solidity)       │
  │     - 9-step validation on-chain        │
  │     - All state from Hedera ledger      │
  │                                         │
  │  4. EscrowSettlement (Solidity)         │
  │     - PREIMAGE-SHA-256 contract         │
  │     - Claimant holds preimage           │
  │     - ward_signed = false — always      │
  └─────────────────────────────────────────┘
        |
        v
   Hedera Consensus Service / EVM
```

---

## Step-by-Step Porting Guide

### Step 1 — Port `ward/constants.py`

Create `contracts/WardConstants.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

library WardConstants {
    // Policy NFT serial number range (replaces XLS-20 taxon 281)
    uint64 constant WARD_POLICY_SERIAL_MIN = 1;

    // Coverage ratio (×10 to avoid floats)
    uint256 constant MIN_COVERAGE_RATIO_X10 = 15; // 1.5×

    // Rate limiting
    uint256 constant CLAIM_RATE_LIMIT_MAX = 3;
    uint256 constant CLAIM_RATE_LIMIT_WINDOW = 300; // seconds

    // Escrow timing
    uint256 constant ESCROW_DISPUTE_HOURS = 48;
    uint256 constant ESCROW_CANCEL_HOURS  = 72;

    // Confirmation count
    uint256 constant DEFAULT_CONFIRM_COUNT = 3;
}
```

Chain-agnostic constants (`MIN_COVERAGE_RATIO`, `CLAIM_RATE_LIMIT_MAX`, `ESCROW_DISPUTE_HOURS`) port verbatim. XRPL-specific constants (`WARD_POLICY_TAXON`, `TF_BURNABLE`, `LSF_LOAN_DEFAULT`, `XRPL_BASE_RESERVE_DROPS`) are replaced with Hedera/EVM equivalents.

---

### Step 2 — Port `ward/primitives.py` → `contracts/WardPrimitives.sol`

Fully chain-agnostic functions that port verbatim (logic only, not Python syntax):

- `make_preimage_condition()` → `sha256(preimage)` in Solidity — identical math
- `generate_claim_preimage()` → `bytes32 preimage = keccak256(abi.encode(block.timestamp, msg.sender, nonce))`
- `check_rate_limit()` → Solidity mapping with sliding window

XRPL-specific functions to replace:
- `validate_xrpl_address()` → `require(addr != address(0))` + EVM address checksum
- `get_ledger_close_time()` → `block.timestamp`
- `submit_with_retry()` → not needed (EVM transactions are synchronous)

```solidity
library WardPrimitives {
    function verifyPreimage(bytes32 preimage, bytes32 condition)
        internal pure returns (bool)
    {
        return sha256(abi.encodePacked(preimage)) == condition;
    }
}
```

---

### Step 3 — Port `ward/validator.py` → `contracts/WardClaimValidator.sol`

Each of the 9 steps maps to an on-chain Solidity check:

| Step | XRPL Implementation | Hedera (EVM) Implementation |
|---|---|---|
| 1 | `AccountNFTs` query → taxon 281 | `IHTS.getNFTInfo(tokenId)` → `metadata.policyType == WARD_POLICY` |
| 2 | `get_ledger_close_time()` vs expiry | `block.timestamp > expiry` |
| 3 | NFT URI metadata vault binding | `nftMetadata.vaultAddress == defaultedVault` |
| 4 | `LedgerEntry(loan_id)` → `LSF_LOAN_DEFAULT` | `IVault(vaultAddr).isDefaulted(loanId)` |
| 5 | `vault_loss > 0` | `IVault(vaultAddr).outstandingAmount(loanId) > 0` |
| 6 | Pool `AccountInfo` balance − reserve | `IERC20(pool).balanceOf(address) >= vaultLoss` |
| 7 | `AccountNFTs` re-check (not burned) | `IHTS.getNFTInfo(tokenId).ownedBy != address(0)` |
| 8 | Claimant holds NFT | `IHTS.getNFTInfo(tokenId).owner == claimant` |
| 9 | Rate limit + solvency ratio | Solidity mapping rate limit + `poolBalance / payout >= 15` (÷10) |

```solidity
contract WardClaimValidator {
    function validateClaim(
        address claimant,
        uint256 nftSerial,
        address defaultedVault,
        bytes32 loanId,
        address poolAddress
    ) external view returns (bool approved, uint256 payoutAmount, string memory reason) {
        // Steps 1–9 as require() + return tuple
    }
}
```

---

### Step 4 — Port `ward/tx_builder.py` + `ward/settlement.py` → `contracts/WardEscrow.sol`

XRPL's native escrow (EscrowCreate/EscrowFinish) is replaced with a Solidity contract:

```solidity
contract WardEscrow {
    struct Escrow {
        address pool;
        address claimant;
        uint256 amount;
        bytes32 condition;   // sha256(preimage)
        uint256 finishAfter; // block.timestamp + 48h
        uint256 cancelAfter; // block.timestamp + 72h
        bool    settled;
    }

    mapping(bytes32 => Escrow) public escrows; // claimId => Escrow

    // Pool calls this (unsigned tx pattern: pool signs, Ward never does)
    function createEscrow(bytes32 claimId, address claimant,
                          bytes32 condition, uint256 amount) external payable;

    // Claimant calls with preimage
    function finishEscrow(bytes32 claimId, bytes32 preimage) external;

    // Pool calls after cancelAfter if claimant never finished
    function cancelEscrow(bytes32 claimId) external;
}
```

`ward_signed = false` is enforced architecturally: the Ward contract never holds HBAR or signing keys. Pool institutions call `createEscrow()` directly.

---

### Step 5 — Port `ward/vault_monitor.py` → HCS Mirror Node Subscription

Replace XRPL WebSocket with Hedera Consensus Service mirror stream:

```typescript
// TypeScript (hedera-sdk HCS subscription)
const client = Client.forTestnet();
const topicId = TopicId.fromString(VAULT_TOPIC_ID);

new TopicMessageQuery()
  .setTopicId(topicId)
  .subscribe(client, null, async (message) => {
    const payload = JSON.parse(Buffer.from(message.contents).toString());
    await verifyDefaultOnChain(payload.loanId); // independent RPC call
    confirmationCount[payload.loanId] = (confirmationCount[payload.loanId] ?? 0) + 1;
    if (confirmationCount[payload.loanId] >= DEFAULT_CONFIRM_COUNT) {
      await onVerifiedDefault(payload);
    }
  });
```

3-ledger confirmation → 3-consensus-round confirmation. Heartbeat timeout (60s) and exponential backoff reconnect logic port verbatim.

---

### Step 6 — Port `ward/client.py` → `WardClient` (TypeScript SDK)

```typescript
class WardClient {
  async purchaseCoverage(params: CoverageParams): Promise<CoverageResult> {
    // 1. Mint HTS NFT (non-transferable, burnable)
    const mintTx = new TokenMintTransaction()
      .setTokenId(WARD_POLICY_TOKEN_ID)
      .setMetadata([policyMetadata])
      .freezeWith(client);
    // institution signs, Ward never does

    // 2. Pay premium (HBAR or USDC)
    const premiumTx = new TransferTransaction()
      .addHbarTransfer(wallet, -premiumAmount)
      .addHbarTransfer(poolAddress, premiumAmount);
    // ward_signed = false
  }
}
```

---

## Test Plan

- [ ] Unit: All 9 validator steps in Solidity with mock vault/pool contracts
- [ ] Unit: `WardEscrow` — create, finish (correct preimage), finish (wrong preimage), cancel (before/after window)
- [ ] Unit: Rate limiting mapping — 3 attempts pass, 4th reverts
- [ ] Unit: HTS NFT non-transferability enforcement
- [ ] Integration: Full claim lifecycle on Hedera testnet
- [ ] Integration: VaultMonitor HCS subscription → verified default callback
- [ ] Invariant: `ward_signed = false` — Ward contract holds no HBAR, no signing keys

---

## Estimated Timeline

| Milestone | Effort |
|---|---|
| Constants + Primitives ported to Solidity | 1 week |
| `WardClaimValidator.sol` (9 steps) | 2 weeks |
| `WardEscrow.sol` (create/finish/cancel) | 1 week |
| HTS NFT policy mint + TypeScript SDK | 1 week |
| VaultMonitor HCS subscription | 1 week |
| Integration tests (Hedera testnet) | 1 week |
| **Total** | **~7 weeks** |

---

## Grant Reference

**Hedera Foundation Grants:** hedera.org/grants  
Application framing: "Ward Protocol brings deterministic default resolution to Hedera institutional lending — the same 9-step on-chain validation that governs XLS-66 vaults, now available to HTS-based lending protocols."
