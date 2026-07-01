# Ward Protocol — Adversarial Testing Report

## Overview

Every adapter and core module was tested against deliberate failure scenarios before release. This documents what was tested, what failed, and how it was fixed.

Day 5 added 45 adversarial tests across the XRPL core, Wormhole NTT, and all six chain adapters (Flare, Axelar, Solana, Hedera, Stellar, XDC). All tests pass. No attack path causes Ward to sign a transaction or produce a payout.

## Why This Matters

Ward is default resolution infrastructure. Institutions depend on it working correctly when things go wrong. We test the wrong paths as hard as the happy paths. An incorrect approval under adversarial conditions — a forged default, a drained pool, a replayed NFT — would represent a direct financial loss.

The core invariant must hold everywhere, not just on the happy path:

> `ward_signed = False — always. No attack path changes this.`

---

## Test Categories

### Replay Attacks

**Scenario**: A previously settled claim's NFT is presented again after being burned.

**Test**: `test_adversarial_burned_nft_rejected_at_step1`, `test_adversarial_burned_nft_ward_signed_never_set`

**Result**: Rejected at Check 1 (Policy NFT). Burned NFT is absent from `AccountNFTs`; the validator returns `approved=False`, `claim_payout_drops=0`. No `UnsignedTransaction` is produced.

**Mechanism**: XRPL NFToken burn removes the token from the ledger permanently. Step 1 queries `AccountNFTs` — absent token = immediate rejection. In `WardResolver.sol`, `_burnedNFTs[nftTokenId]` is set `true` at settlement and checked before all nine steps.

---

### Expired Credentials

**Scenario**: A policy NFT with a past expiry timestamp is presented.

**Test**: `test_adversarial_expired_policy_rejected_at_step2`

**Result**: Rejected at Check 2 (Policy Expiry). `block.timestamp > cert.expiry` evaluates true; `rejection_reason` contains "expired". `steps_passed < 3`.

**Mechanism**: Policy expiry is read from the NFT URI metadata (XRPL) or `_policies[nftTokenId].expiry` (EVM). The ledger close timestamp is used — never the server clock.

---

### Identity Spoofing

**Scenario 1**: Claim submitted with a different vault address than the one bound in the policy NFT (cross-vault claim).

**Test**: `test_adversarial_vault_mismatch_rejected_at_step3`

**Result**: Rejected at Check 3 (Vault Binding). `cert.vaultAddress != defaultedVault`. `steps_passed < 4`.

**Mechanism**: The policy NFT URI stores `vault_address` at mint time. Any mismatch between the NFT-bound vault and the claim's `defaultedVault` fails the binding check. In Solidity: `"Cross-vault claim: NFT vault mismatch"`.

**Scenario 2**: Attacker presents their own address instead of the legitimate claimant.

**Check 8** (Claimant Holds NFT) verifies `_nftHolders[nftTokenId] == claimant`. An attacker who doesn't hold the NFT fails this check.

---

### Default Flag Manipulation

**Scenario**: Claim submitted for a loan that has not defaulted (LSF_LOAN_DEFAULT not set).

**Test**: `test_adversarial_no_default_flag_rejected_at_step4`

**Result**: Rejected at Check 4 (Default Flag). `_loanFlags[loanId] & LSF_LOAN_DEFAULT == 0`. `steps_passed < 5`.

**Mechanism**: The XLS-66 default flag is a bitmask set by the on-chain lending protocol, not by Ward. Ward reads it via `LedgerEntry`; it cannot be forged by a claimant.

---

### Pool Exhaustion

**Scenario 1**: Pool balance is zero at claim time.

**Test**: `test_adversarial_insolvent_pool_rejected`

**Result**: Rejected at Check 6 or 9. `rejection_reason` contains "insolvent". `approved=False`.

**Scenario 2**: Pool balance is positive but below the 1.5× minimum coverage ratio.

**Test**: `test_adversarial_pool_below_coverage_ratio`

**Result**: Rejected at Check 9 (Pool Solvency). Coverage ratio check: `usable >= payout * 150 / 100`.

**Mechanism**: Checks 6 and 9 both verify pool balance. Check 6 verifies `usable >= loss`. Check 9 adds the 1.5× solvency requirement. A pool drained between Check 6 and Check 9 is still caught.

---

### Rate Limit Exceeded

**Scenario**: More than `CLAIM_RATE_LIMIT_MAX` (3) claims attempted on the same NFT within a 300-second window.

**Test**: `test_adversarial_rate_limit_exceeded`, `test_adversarial_rate_limit_ward_signed_not_affected`

**Result**: `ValidationError("Rate limit exceeded")` raised on the 4th attempt. No payout produced.

**Mechanism**: `ward.primitives.check_rate_limit()` maintains a sliding window of timestamps per NFT token ID. The 4th call within the window raises `ValidationError`. Ward never signs anything as a result of the exception.

---

### Partial Resolution

**Scenario**: No liquid XRPL pathfinding path exists between collateral asset and payout asset at ledger close.

**Tests**: `test_adversarial_no_pathfinder_path_partial_resolution`, `test_adversarial_pathfinder_rpc_failure_partial_resolution`

**Result**: `partial_resolution=True` set on `UnsignedTransaction`. `ward_signed=False`. `paths=None`, `send_max=None`. The caller must decide how to proceed — Ward never forces a swap into an illiquid market.

**Mechanism**: `Resolver._ripple_path_find()` queries `ripple_path_find`. If `alternatives` is empty or the RPC fails, `paths=None` is returned and `partial_resolution=True` is set. No exception is raised — the flag signals the condition without panicking.

---

### Cross-Chain Attack Surface

**Wormhole NTT — Issuer control violation attempt**

**Test**: `test_adversarial_rlusd_issuer_control_preserved`

**Result**: `source_token` in the NTT payload is hardcoded to the canonical RLUSD hex (`"524C555344000000000000000000000000000000"`). An attacker cannot inject a different token via the adapter constructor — it is a module-level constant. `ward_signed=False` maintained.

**Wormhole NTT — ward_signed field immutability**

**Test**: `test_adversarial_ntt_payload_ward_signed_immutable`

**Result**: `NTTTransferPayload.ward_signed` is declared `field(default=False, init=False)`. It cannot be passed to the constructor. Any object crafted with attacker-controlled fields still has `ward_signed=False`.

**Axelar GMP — Message delivery failure**

**Test**: `test_adversarial_message_delivery_failure_ward_signed_false`

**Result**: Even with an unknown destination chain, `build_resolution_tx()` returns `ward_signed=False`. The payload is returned unsigned; Gateway delivery failure is an institution-layer concern, not a Ward-layer concern.

**Axelar GMP — Cross-chain resolution rejected at source**

**Test**: `test_adversarial_cross_chain_resolution_rejected_not_signed`

**Result**: When `verify_vault()` returns `is_defaulted=False` (no default confirmed), no payload is built. No signing occurs.

---

### Adapter-Specific Edge Cases

| Adapter | Scenario | Result |
|---|---|---|
| Flare | Chain ID override by attacker | Passed through; `ward_signed=False` |
| Flare | Zero payout | `ward_signed=False` |
| Solana | Stale/empty blockhash | `ward_signed=False`; blockhash preserved in payload |
| Solana | Zero payout | `ward_signed=False` |
| Hedera | Attacker-injected token ID | Payload reflects configured ID; `ward_signed=False` |
| Hedera | Zero payout | `ward_signed=False` |
| Stellar | Wrong network passphrase | Passphrase is institution-only; Ward never uses it to sign |
| Stellar | Attacker-injected issuer | Payload reflects configured issuer; `ward_signed=False` |
| Stellar | Minimum stroop (1) | Amount string = "0.0000001"; no rounding exploit |
| XDC | Mainnet chain ID override | Passed through; `ward_signed=False` |
| XDC | Zero payout | `ward_signed=False` |

---

## Core Invariant Under All Conditions

`ward_signed = False` — no attack path causes Ward to sign or hold keys. Verified across all seven adapters and all failure scenarios via:

- `test_invariant_all_adapters_build_resolution_tx_ward_signed_false` — all seven adapters, single test
- `test_invariant_all_adapters_send_max_ward_signed_false` — all seven adapter payloads
- `test_invariant_all_adapters_escrow_create_ward_signed_false` — all seven adapters' escrow create

The `ward_signed` field is declared `field(default=False, init=False)` on every payload dataclass. This is a structural guarantee — the Python `dataclasses` module prevents `ward_signed` from appearing as a constructor parameter. No caller can pass `ward_signed=True`.

---

## Fixes Applied During Day 5

| Issue | Fix |
|---|---|
| `ValidationResult.payout_amount` does not exist | Changed assertion to `claim_payout_drops == 0` (correct attribute name) |

---

## Test Count

| Layer | Tests | Status |
|---|---|---|
| Python SDK (`test_ward.py`) | 435 | All passing |
| Rust SDK | 40 | All passing |
| TypeScript SDK | 45 | All passing |
| Hardhat (Solidity) | Pending `npx hardhat test` | Requires Hardhat install |
| **Total** | **520+** | |

Python breakdown by category:
- XRPL core + adversarial: ~300 tests
- Resolver + Pathfinder: 7 tests
- Wormhole NTT: 9 + 4 adversarial = 13 tests
- Flare: 9 + 4 adversarial = 13 tests
- Axelar: 9 + 5 adversarial = 14 tests
- Solana: 8 + 4 adversarial = 12 tests
- Hedera: 7 + 4 adversarial = 11 tests
- Stellar: 8 + 5 adversarial = 13 tests
- XDC: 8 + 5 adversarial = 13 tests
- Cross-adapter invariant: 3 tests

---

## Methodology

Every adversarial test follows the same pattern:

1. **Construct the attack**: Create a validator or adapter with deliberately invalid or degenerate inputs
2. **Run the resolution path**: Call the same function the attacker would call
3. **Assert rejection**: Verify `approved=False` or exception raised
4. **Assert no signing**: Verify `ward_signed=False` (or `claim_payout_drops=0`) on all outputs

Tests are deterministic (no live RPC), fast (< 4 seconds for 435 tests), and run in CI on every push.
