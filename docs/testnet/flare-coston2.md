# Ward Protocol — Flare Coston2 Testnet Deployment

## Network

| Property | Value |
|---|---|
| Network | Flare Coston2 (testnet) |
| Chain ID | 114 |
| RPC | `https://coston2-api.flare.network/ext/C/rpc` |
| Explorer | `https://coston2-explorer.flare.network` |
| Faucet | `https://coston2-faucet.towolabs.com` |

## Deployment

> **To deploy:** set `DEPLOYER_PRIVATE_KEY` in `.env`, ensure account is funded with C2FLR, then run:
> ```bash
> npm install  # install Hardhat deps if not already done
> npx hardhat run scripts/deploy-flare.js --network coston2
> ```

| Field | Value |
|---|---|
| Contract Address | _(set after deployment)_ |
| Deploy Transaction | _(set after deployment)_ |
| Block Number | _(set after deployment)_ |
| Deployer | _(set after deployment)_ |
| Date | _(set after deployment)_ |

## E2E Verification

> **To run E2E:** after deployment, set `WARD_RESOLVER=0x<address>` and run:
> ```bash
> WARD_RESOLVER=0x<address> npx hardhat run scripts/test-flare-e2e.js --network coston2
> ```

| Step | Transaction | Status |
|---|---|---|
| registerPolicy | _(set after E2E run)_ | — |
| recordDefault | _(set after E2E run)_ | — |
| setPoolBalance | _(set after E2E run)_ | — |
| resolveClaimUnsigned | view call (no tx) | — |
| buildUnsignedEscrow | view call (no tx) | — |

## Invariant Verification

| Check | Result |
|---|---|
| `wardSigned` on `ResolutionResult` | _(verified after E2E)_ |
| `wardSigned` on `UnsignedEscrowPayload` | _(verified after E2E)_ |
| Steps passed | _(verified after E2E — expected 9/9)_ |
| Payout amount | _(verified after E2E)_ |

## How to Run

### Prerequisites

```bash
# 1. Install Hardhat and toolbox
npm install

# 2. Create .env with deployer private key
echo "DEPLOYER_PRIVATE_KEY=0x<your-key>" > .env

# 3. Fund deployer account with C2FLR from faucet
#    https://coston2-faucet.towolabs.com

# 4. (Optional) Set RLUSD placeholder address
echo "RLUSD_ADDRESS=0x0000000000000000000000000000000000000001" >> .env
```

### Deploy

```bash
npx hardhat run scripts/deploy-flare.js --network coston2
```

Expected output:
```
═══════════════════════════════════════════════════════
  Ward Protocol — WardResolver Deployment
═══════════════════════════════════════════════════════
  Network:   coston2 (chain ID 114)
  Deployer:  0x<your address>
  Balance:   <balance> FLR
  RLUSD:     0x0000000000000000000000000000000000000001
───────────────────────────────────────────────────────

  Deploying WardResolver...

  ✓ WardResolver deployed
    Address:   0x<contract address>
    Tx Hash:   0x<deploy tx hash>
    Block:     <block number>

  Verifying on-chain constants...
    WARD_POLICY_TAXON:    281  (expected 281)
    LSF_LOAN_DEFAULT:    0x00010000  (expected 0x00010000)
    CLAIM_RATE_LIMIT_MAX: 3  (expected 3)
    CLAIM_RATE_LIMIT_WINDOW: 300s  (expected 300)
  ✓ All constants verified

  ✓ ward_signed = false verified on-chain
```

### Run E2E

```bash
WARD_RESOLVER=0x<contract address> npx hardhat run scripts/test-flare-e2e.js --network coston2
```

Expected output:
```
  E2E PASSED — All assertions green

  On-chain transactions:
    registerPolicy:  https://coston2-explorer.flare.network/tx/0x<hash>
    recordDefault:   https://coston2-explorer.flare.network/tx/0x<hash>
    setPoolBalance:  https://coston2-explorer.flare.network/tx/0x<hash>

    STEPS_PASSED=9
    PAYOUT=500.0 RLUSD
    WARD_SIGNED=false
```

### Run Unit Tests (local Hardhat node — no testnet required)

```bash
npx hardhat test test/WardResolver.test.js
```

## Security Notes

- `WardResolver.resolveClaimUnsigned()` is `view` — it cannot transfer funds or modify state
- `wardSigned = false` enforced at the Solidity struct level — not settable by any caller
- State management functions (`registerPolicy`, `recordDefault`, `setPoolBalance`) will be access-controlled in production (Ward oracle only)
- This testnet deployment uses open access for verification purposes — production deployment gates all writes to the authorized Ward oracle address

## Status

Scripts ready. Deployment pending — run `deploy-flare.js` then fill in addresses above.
