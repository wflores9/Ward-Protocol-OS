# Phase 2 (1.5) — Ward Protocol on Flare

**Chain:** Flare EVM + Flare Data Connector (FDC)  
**Priority:** HIGHEST — runs parallel to XRPL mainnet  
**Grant:** Flare Grants + Google Cloud credits up to $200K — flare.network/grants  
**Status:** Planning

---

## Why Flare First

Flare is the highest-priority expansion target because:

1. **Flare Data Connector (FDC)** can read and verify XRPL ledger state from within Flare EVM — Ward's 9-step validation can reference XRPL vaults without a full XRPL re-implementation
2. **FXRP** (Flare-wrapped XRP) enables XRP-denominated lending vaults on EVM
3. Flare's native EVM runtime means Ward's Solidity contracts (built for Hedera) require minimal changes
4. Institutional DeFi on Flare (SparkDEX, Cyclo) already targets the same XLS-66 market Ward serves

---

## How Flare Data Connector Enables XRPL State Verification

The Flare Data Connector is a decentralized attestation layer that allows Flare smart contracts to read and verify state from external blockchains including XRPL. This is the critical bridge:

```
XRPL Ledger                    Flare EVM
─────────────                  ──────────────────────────────
XLS-66 Vault Object            FDC Attestation Request
  - loan_id                 →    attestationType: XRPL_STATE
  - Flags (LSF_LOAN_DEFAULT)     sourceId: XRPL
  - PrincipalOutstanding         requestBody: { loanId, ledgerIndex }
  - CollateralAmount
                               FDC Response (on-chain proof)
                            →    merkleProof + stateData
                                 available to any Flare contract
```

Ward's `ClaimValidator` Step 4 (`LSF_LOAN_DEFAULT` check) and Step 5 (vault loss) can be satisfied by an FDC attestation of the XRPL ledger state, without running a separate XRPL node.

---

## Architecture

```
Institution (signing key)
        |
        v
  WardClient (Flare EVM)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  WardPolicyNFT (ERC-721, non-transferable)          │
  │    - mint() on coverage purchase                    │
  │    - burn() on settlement (replay protection)       │
  │                                                     │
  │  VaultMonitor (Flare)                               │
  │    Option A: Flare event logs (for Flare vaults)    │
  │    Option B: FDC attestation (for XRPL vaults)      │
  │    3-block confirmation window                      │
  │                                                     │
  │  WardClaimValidator (Solidity)                      │
  │    Steps 1-3, 6-9: Flare/EVM state                  │
  │    Steps 4-5: FDC attestation of XRPL state         │
  │              OR Flare vault contract state           │
  │                                                     │
  │  WardEscrow (Solidity, PREIMAGE-SHA-256)             │
  │    pool → claimant, condition = sha256(preimage)    │
  │    ward_signed = false — always                     │
  │                                                     │
  └─────────────────────────────────────────────────────┘
        |
        v
  Flare Consensus / EVM state
  (+ FDC proofs of XRPL state where needed)
```

---

## FXRP Lending Vault Architecture

For Flare-native lending vaults using FXRP:

```
Borrower                 Vault (Solidity)              Ward
   |                          |                          |
   |─── deposit collateral ──>|                          |
   |<── receive FXRP loan ────|                          |
   |                          |                          |
   | (health ratio drops)     |                          |
   |                          |── emit VaultDefaulted ──>|
   |                          |    event (EVM log)        |
   |                          |                          |
   |                          |   VaultMonitor sees log  |
   |                          |   3-block confirmation   |
   |                          |   VerifiedDefault fires  |
   |                          |                          |
   |          Claimant ───────────── validateClaim() ──>|
   |                          |   9 steps, on-chain      |
   |                          |   EscrowCreate           |
   |          Claimant ───────────── finishEscrow() ──>  |
   |                          |   (with preimage)        |
   |                          |   NFT burned             |
```

---

## Step-by-Step Porting Guide

### Step 1 — Policy NFT: ERC-721 Non-Transferable

Port `NFTokenMint` (XLS-20, TF_BURNABLE, taxon 281) → ERC-721 with transfer lock:

```solidity
contract WardPolicyNFT is ERC721 {
    // Soulbound: non-transferable (attack vector 2.3)
    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256)
        internal override
    {
        require(from == address(0) || to == address(0),
            "WardPolicy: non-transferable");
    }

    struct PolicyMetadata {
        address vaultAddress;   // replaces NFT URI "v" field
        uint256 coverageWei;    // replaces "c" field (drops → wei for FXRP)
        uint256 expiry;         // replaces "e" (block.timestamp)
        address poolAddress;    // replaces "pa"
        string  licenseTier;
    }

    mapping(uint256 => PolicyMetadata) public policies;

    function mint(address to, PolicyMetadata calldata meta)
        external onlyWard returns (uint256 tokenId)
    {
        // ward_signed = false: Ward contract mints, institution pays gas
        tokenId = _nextTokenId++;
        _mint(to, tokenId);
        policies[tokenId] = meta;
    }
}
```

### Step 2 — ClaimValidator: Mixed Flare + FDC

For XRPL-sourced vaults, Steps 4 and 5 use FDC attestation:

```solidity
interface IFDCAttestation {
    struct XRPLStateResponse {
        bytes32 loanId;
        uint256 flags;
        uint256 outstandingAmount;
        uint256 collateralAmount;
        uint64  ledgerIndex;
    }

    function verifyXRPLState(bytes calldata proof)
        external view returns (XRPLStateResponse memory);
}

contract WardClaimValidator {
    IFDCAttestation public fdc;

    // Steps 4+5 for XRPL-sourced vaults
    function _verifyXRPLDefault(bytes calldata fdcProof, bytes32 loanId)
        internal view returns (bool defaulted, uint256 vaultLoss)
    {
        IFDCAttestation.XRPLStateResponse memory state = fdc.verifyXRPLState(fdcProof);
        require(state.loanId == loanId, "Loan ID mismatch");
        defaulted = (state.flags & LSF_LOAN_DEFAULT) != 0;
        vaultLoss = state.outstandingAmount;
    }
}
```

For Flare-native vaults, Steps 4 and 5 read the vault contract directly — no FDC needed.

### Step 3 — VaultMonitor: Two Modes

**Mode A — Flare-native vaults (event logs):**
```typescript
const provider = new ethers.providers.WebSocketProvider(FLARE_WS_URL);
const vault = new ethers.Contract(vaultAddress, VAULT_ABI, provider);

vault.on("VaultDefaulted", async (loanId, outstandingAmount, event) => {
  confirmations[loanId] = (confirmations[loanId] ?? 0) + 1;
  if (confirmations[loanId] >= DEFAULT_CONFIRM_COUNT) {
    await onVerifiedDefault({ loanId, outstandingAmount });
  }
});
```

**Mode B — XRPL vaults via FDC:**
Keep existing `VaultMonitor` (XRPL WebSocket) running alongside. On `VerifiedDefault`, request FDC attestation for the proof that Flare contracts will accept.

### Step 4 — EscrowSettlement: Solidity Contract

Identical to Hedera implementation — see `phase2-hedera.md` Step 4. PREIMAGE-SHA-256 math is chain-agnostic. Only difference: amounts in wei (FXRP) instead of drops (XRP).

```solidity
contract WardEscrow {
    // finishEscrow verifies: sha256(preimage) == condition
    function finishEscrow(bytes32 claimId, bytes32 preimage) external {
        Escrow storage e = escrows[claimId];
        require(sha256(abi.encodePacked(preimage)) == e.condition, "Bad preimage");
        require(block.timestamp >= e.finishAfter, "Dispute window open");
        require(block.timestamp < e.cancelAfter, "Escrow expired");
        e.settled = true;
        IERC20(FXRP).transfer(e.claimant, e.amount);
        emit EscrowFinished(claimId, e.claimant, e.amount);
    }
}
```

---

## FDC Cross-Chain Data Flow

```
Ward Python SDK (XRPL)              Flare EVM
─────────────────────               ─────────────────────────
1. Detect default via              4. FDC attestation request
   VaultMonitor (XRPL WS)             submitted to FDC layer

2. Build FDC attestation           5. FDC attestors reach
   request payload:                   consensus on XRPL state
   { loanId, ledgerIndex,
     requiredFlags }               6. Merkle proof available
                                      on-chain in Flare EVM
3. Submit to FDC relay
                                   7. WardClaimValidator.validateClaim()
                                      called with FDC proof
                                      → Steps 4+5 verified
```

---

## Test Plan

- [ ] Unit: All 9 steps in `WardClaimValidator` with mock FDC and vault contracts
- [ ] Unit: `WardEscrow` — correct/wrong preimage, timing windows
- [ ] Unit: `WardPolicyNFT` non-transferability (transfer reverts, burn succeeds)
- [ ] Unit: Rate limiting (3 pass, 4th reverts)
- [ ] Integration: FDC attestation round-trip on Flare Coston2 testnet
- [ ] Integration: Full claim lifecycle with FXRP mock token
- [ ] Integration: VaultMonitor Mode A (event logs) + Mode B (FDC)
- [ ] Invariant: Ward contract holds no ETH/FXRP, no signing keys

---

## Estimated Timeline

| Milestone | Effort |
|---|---|
| Solidity constants + primitives | 3 days |
| `WardPolicyNFT.sol` (ERC-721 soulbound) | 3 days |
| `WardClaimValidator.sol` (9 steps, dual mode) | 2 weeks |
| FDC integration + attestation flow | 1 week |
| `WardEscrow.sol` | 1 week |
| VaultMonitor (Flare event logs + FDC mode) | 1 week |
| TypeScript SDK wrapper | 1 week |
| Integration tests (Coston2 testnet) | 1 week |
| **Total** | **~7 weeks** |

---

## Grant Reference

**Flare Grants:** flare.network/grants  
**Google Cloud credits:** Up to $200K for qualifying Web3 projects on Flare  
Application framing: "Ward Protocol brings auditable default resolution to Flare institutional lending. The Flare Data Connector allows Ward to verify XRPL vault defaults directly from Flare EVM — bridging XRPL institutional lending to EVM-native DeFi without trust assumptions."
