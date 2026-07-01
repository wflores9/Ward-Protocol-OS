# Ward Protocol — Security Notes

_Last updated: 2026-03-01_

This document catalogues every attack vector identified during design and implementation of the Ward Protocol SDK, and specifies the XRPL-native or code-level mitigation applied.

---

## Table of Contents
1. [Threat Model](#1-threat-model)
2. [Attack Vectors and Mitigations](#2-attack-vectors-and-mitigations)
   - 2.1 Policy forgery / fake claim injection
   - 2.2 Policy double-spend (replay attack)
   - 2.3 Policy transfer and stolen claim
   - 2.4 Vault operator default signal manipulation
   - 2.5 Clock manipulation / expiry bypass
   - 2.6 Front-running the escrow release
   - 2.7 Ward monitoring module spoofing
   - 2.8 Pool drainage via inflated loss calculation
   - 2.9 Coverage ratio manipulation
   - 2.10 Address injection / transaction crafting
   - 2.11 Key exfiltration
   - 2.12 Rate limiting bypass / DoS
   - 2.13 NFT taxon spoofing
   - 2.14 XRP / drops unit confusion
   - 2.15 Silent network failure
3. [Residual Risks](#3-residual-risks)
4. [XLS-66 / XRPL Protocol Assumptions](#4-xls-66--xrpl-protocol-assumptions)

---

## 1. Threat Model

### Principals
| Actor | Trust Level | Notes |
|---|---|---|
| XRPL Ledger | Fully trusted | Ground truth for all state |
| Ward Protocol code | Trusted-but-verify | Open source; should be auditable by institutions |
| Institution (pool operator) | Trusted for operations | Controls pool wallet; runs monitoring infra |
| Depositor (claimant) | Untrusted | Assumed adversarial for claim validation |
| Vault operator | Untrusted | Assumed capable of manipulating default signals |
| Ward's API server | Intentionally irrelevant | Protocol survives Ward server going offline |

### Assets to Protect
1. Pool funds (XRP held in pool wallet)
2. Integrity of the claim process (only valid claims trigger payouts)
3. NFT policy certificates (must be non-forgeable and non-reusable)

---

## 2. Attack Vectors and Mitigations

### 2.1 Policy Forgery / Fake Claim Injection

**Scenario:** An attacker creates a fake policy NFT outside the Ward protocol and attempts to file a claim.

**Attack path:**
1. Attacker self-mints an NFT with WARD_POLICY_TAXON and arbitrary URI metadata.
2. Attacker calls `ClaimValidator.validate_claim()` pointing at a real defaulted vault.

**Mitigation:**
- `ClaimValidator` Step 1 verifies the NFT exists in the claimant's `account_nfts` **and** that `NFTokenTaxon == WARD_POLICY_TAXON` (281).
- The NFT URI metadata must contain a valid premium payment transaction hash. The validator does not currently check the premium tx exists on-chain — this is a **known gap** (see §3).
- Ward issues policies from a known Ward Protocol wallet (future: permissioned domain verification via XLS-80).

**XRPL primitive used:** `account_nfts` RPC, `NFTokenTaxon` field

---

### 2.2 Policy Double-Spend (Replay Attack)

**Scenario:** A claimant files a claim, receives a payout, then tries to claim again using the same policy NFT.

**Attack path:**
1. Claim approved, escrow created.
2. Attacker finishes escrow.
3. Attacker immediately submits another `validate_claim` call before the NFT burn lands.

**Mitigations:**
- `EscrowSettlement.finish_escrow()` burns the NFT **immediately after** releasing the payout (sequential, not atomic).
- Once burned, the NFT disappears from `account_nfts`. Step 1 of any subsequent claim attempt rejects it.
- In-memory rate limiter caps attempts to `RATE_LIMIT_ATTEMPTS` (3) per `RATE_LIMIT_WINDOW_S` (5 minutes) per NFT token ID.

**Residual TOCTOU gap:** There is a small window between EscrowFinish landing and NFTokenBurn confirming during which a second validation could theoretically pass (the NFT still shows in `account_nfts` for ~1–3 ledger closes). See §3.

**XRPL primitive used:** `NFTokenBurn`, `account_nfts`

---

### 2.3 Policy Transfer and Stolen Claim

**Scenario:** An attacker obtains or steals a policy NFT (e.g., via a marketplace) and attempts to claim on behalf of someone else's vault deposit.

**Attack path:**
1. Attacker acquires NFT (legitimate or stolen).
2. Attacker claims payout by controlling the address holding the NFT.

**Mitigation:**
- `NFTokenMint` is called with `flags = TF_BURNABLE (0x1)` — **deliberately omitting `tfTransferable (0x8)`**.
- Without `tfTransferable`, XRPL prevents ANY transfer of the NFT after initial minting. The policy is permanently bound to the minting account.
- `ClaimValidator` Step 8 explicitly documents that claimant == NFT holder verification is performed in Step 1 (by querying `account_nfts` for the claimant's address).

**XRPL primitive used:** NFTokenMint flags — absence of `tfTransferable`

---

### 2.4 Vault Operator Default Signal Manipulation

**Scenario:** A malicious vault operator floods the XRPL with fake `LoanManage/tfLoanDefault` transactions to trigger repeated payouts.

**Attack paths:**
- Rapid fire: many defaults in a short window to drain the pool.
- Spurious default: single fake default for a loan that isn't actually defaulted.

**Mitigations:**
- `VaultMonitor` implements **anomaly detection**: ≥5 default signals from the same vault in a 5-minute window trigger an alert callback.
- `VaultMonitor` requires **3 ledger confirmations** before emitting a verified default event. This prevents acting on unconfirmed (rolled-back) transactions.
- After 3 confirms, `_verify_default_on_chain()` independently re-fetches the `Loan` ledger object and re-reads `lsfLoanDefault`. Even if the event was real, the current ledger state is the authority.
- `ClaimValidator` Step 4 independently verifies the `lsfLoanDefault` flag on the actual `Loan` ledger object, not relying on event data.

**XRPL primitive used:** `LedgerEntry(loan=...)`, ledger stream confirmation counting

---

### 2.5 Clock Manipulation / Expiry Bypass

**Scenario:** An attacker manipulates the local system clock to make an expired policy appear valid.

**Mitigation:**
- `ClaimValidator` Step 2 calls `get_ledger_time()` which fetches `ServerInfo.validated_ledger.close_time` from XRPL — **never** from `time.time()` or `asyncio.get_event_loop().time()`.
- Policy expiry is stored in the NFT metadata as `expiry_ledger_time` (Ripple epoch seconds).
- `EscrowSettlement.finish_escrow()` and `cancel_escrow()` also verify timing against XRPL ledger time.

**Bug fixed [1]:** `asyncio.get_event_loop().time()` in original prototype replaced with XRPL ledger time.

---

### 2.6 Front-Running the Escrow Release

**Scenario:** An attacker monitoring the XRPL mempool/ledger stream sees that an escrow's `FinishAfter` window has opened and races to call `EscrowFinish` before the legitimate claimant.

**Mitigation:**
- `EscrowCreate` sets **both** a time condition (`finish_after`) **and** a crypto condition (`condition`) using PREIMAGE-SHA-256.
- The condition is a SHA-256 hash of a secret preimage held exclusively by the claimant.
- `EscrowFinish` requires the `fulfillment` (the preimage in DER encoding). Without it, the transaction fails with `tecCRYPTO_CONDITION_FAILURE`.
- An attacker who knows the timing cannot finish the escrow without the preimage.
- Even Ward itself cannot front-run the payout — it only receives the `condition` (hash), never the `fulfillment` (preimage).

**XRPL primitive used:** PREIMAGE-SHA-256 crypto-conditions (ASN.1 DER encoding, RFC draft-thomas-crypto-conditions)

---

### 2.7 Ward Monitoring Module Spoofing

**Scenario:** An attacker compromises or spoofs Ward's monitoring infrastructure to inject fake default events.

**Mitigation:**
- `VaultMonitor` treats all incoming WebSocket events as **hints only**.
- Every potential default event is independently cross-validated against the live XRPL ledger via `LedgerEntry` before being emitted.
- The validator is designed for institutions to run on their own infrastructure. Ward provides code, not servers.
- No sensitive state is stored locally. On restart, all state is re-derived from the ledger.

---

### 2.8 Pool Drainage via Inflated Loss Calculation

**Scenario:** An attacker manipulates the loss calculation inputs to inflate the payout amount.

**Mitigation:**
- `ClaimValidator` Step 5 fetches `Loan` and `LoanBroker` ledger objects **directly from XRPL**.
- XLS-66 loss formula uses only on-chain fields: `PrincipalOutstanding`, `InterestOutstanding`, `DebtTotal`, `CoverAvailable`, `CoverRateMinimum`, `CoverRateLiquidation`.
- No local variables or off-chain inputs affect the loss calculation.
- `ClaimValidator` Step 9 verifies the pool has sufficient balance to cover the payout **before** creating the escrow.

---

### 2.9 Coverage Ratio Manipulation

**Scenario:** A vault operator inflates reported TVL or deflates outstanding loans to pass the coverage check.

**Mitigation:**
- Step 6 reads `AssetsTotal` and `LossUnrealized` from the XRPL `Vault` ledger object.
- `TotalValueOutstanding` is read from the `Loan` ledger object.
- All values are from authoritative on-chain ledger entries — no off-chain input.
- `calculate_coverage_ratio()` raises `ValidationError` if ratio < 200%, which causes Step 6 to reject the claim if the breach isn't proven.

---

### 2.10 Address Injection / Transaction Crafting

**Scenario:** Malicious input to SDK functions containing crafted XRPL addresses or large integers designed to cause incorrect transaction routing.

**Mitigations:**
- Every address parameter is validated with `validate_xrpl_address()` which calls `xrpl.core.addresscodec.is_valid_classic_address()`. This performs base58check validation — fake addresses with correct format but wrong checksum are rejected.
- Every drops amount is validated with `validate_drops_amount()` which enforces positive integer, 64-bit bound checks.
- NFT token IDs are validated with `validate_nft_id()` (64 hex characters).

**Bug fixed [6]:** Original prototype had no address validation at all.

---

### 2.11 Key Exfiltration

**Scenario:** Ward's code stores or logs private keys.

**Mitigation:**
- No Ward function stores a `Wallet` object beyond the duration of a single function call.
- Wallet objects are passed as parameters and not assigned to instance attributes (`self.wallet`).
- `purchase_coverage`, `create_claim_escrow`, `finish_escrow`, and `cancel_escrow` all accept wallets as arguments and release them on return.
- Logs never include private key material — only public addresses and transaction hashes.

**Architecture constraint:** Ward sells software. Institutions hold keys. Ward's servers are irrelevant to the protocol's survival.

---

### 2.12 Rate Limiting Bypass / DoS

**Scenario:** An attacker submits thousands of claim validation requests to exhaust pool reserves or crash the validator.

**Mitigations:**
- `ClaimValidator` maintains an in-memory rate limiter: `RATE_LIMIT_ATTEMPTS = 3` per `RATE_LIMIT_WINDOW_S = 300` seconds per NFT token ID.
- Input validation runs before any XRPL network call — malformed inputs are rejected cheaply.
- `VaultMonitor` anomaly detection flags rapid default signals from the same vault.

**Limitation:** The rate limiter is per-process in-memory. A distributed deployment needs a shared rate limit store (Redis etc.). Note in production deployment guide.

---

### 2.13 NFT Taxon Spoofing

**Scenario:** An attacker mints an NFT with a forged URI that mimics a Ward policy but uses a different taxon.

**Mitigation:**
- Step 1 verifies `NFTokenTaxon == WARD_POLICY_TAXON (281)`.
- An NFT with the correct taxon minted by a non-Ward issuer won't have a valid premium payment transaction in its metadata (future: cross-check premium tx on-chain).

---

### 2.14 XRP / Drops Unit Confusion

**Scenario:** Passing XRP values where drops are expected causes premium or payout to be 1,000,000× too large or too small.

**Mitigation:**
- All internal amounts throughout `ward_client.py` are exclusively in **drops**.
- Function parameters named `*_drops` make the unit explicit.
- `validate_drops_amount()` enforces integer type — fractional XRP values (floats) are rejected.
- `calculate_coverage_ratio()` takes and returns drops consistently.

**Bug fixed [4]:** Original prototype mixed XRP and drops by calling `xrp_to_drops()` on an already-XRP-denominated premium.

---

### 2.15 Silent Network Failure

**Scenario:** XRPL RPC or WebSocket calls silently fail or return empty/partial data, causing the validator to approve a claim it shouldn't.

**Mitigations:**
- All `response.is_successful()` checks raise `LedgerError` on failure.
- None of the validation steps assume a missing field is "OK" — missing fields cause rejection.
- `_step4_verify_default_flag()` returns `None` (→ rejection) if the `LedgerEntry` call fails.
- `_step5_calculate_loss()` returns an error string if the `LoanBroker` fetch fails.

**Bug fixed [7]:** Original prototype had no error handling — failures were silently swallowed.

---

## 3. Residual Risks

| Risk | Severity | Notes |
|---|---|---|
| NFT burn ↔ escrow finish TOCTOU | Medium | ~1–3 ledger close window. Mitigated by rate limiter. Full fix requires XRPL Hooks or atomic multi-tx. |
| Premium payment not verified on-chain | RESOLVED in v0.2.6 | Validator now scans `account_tx` on the pool address and requires a matching premium `Payment` from the claimant with the `ward/policy-premium` memo for the policy NFT and coverage amount before approving any claim. Documented by `TestPremiumVerificationGap::test_fake_nft_without_premium_is_rejected`. |
| In-memory rate limiter not distributed | Low | Single-process only. Multi-process deployments need shared state. |
| LoanManage transaction type not in xrpl-py standard | Low | XLS-66 is a draft standard. `LedgerEntry(loan=...)` may not be available in all xrpl-py versions. Test on target network before production. |
| Anomaly detection threshold is static | Low | Fixed 5/5min threshold may miss slow-drip attacks. Consider adaptive thresholds. |
| Coverage tracking — RESOLVED in v0.2.3 | — | Active coverage is now derived from on-chain Payment transactions with `ward/policy-premium` memos via `ward/coverage.py`. Reading directly from XRPL ledger state — restart-safe and fully auditable. The in-memory `_coverage_registry` cache remains for session performance (NFT ID filter for burned/settled policies) but is no longer the authoritative source. |

---

## 4. XLS-66 / XRPL Protocol Assumptions

- XLS-66 (`LoanManage`, `lsfLoanDefault`, `Loan`, `LoanBroker`, `Vault` ledger entries) is assumed to be live on the target network.
- XRPL Hooks are NOT assumed — all automation is client-side.
- XRPL Checks are a viable alternative payout mechanism (claimant cashes, not Ward pushes) but not yet implemented.
- XRPL multi-sig on pool disbursements is recommended for large payouts (>10% of pool). Not yet implemented — add M-of-N `SignerList` to pool account and require multi-sig for EscrowCreate above threshold.
- XRPL `asfRequireDest` on the pool account prevents accidental fund loss from transfers without destination tags.

## TOCTOU: EscrowFinish → NFTokenBurn

**Status:** Mitigated via Redis settlement lock. Residual risk documented.

**Gap:** `finish_escrow()` builds unsigned EscrowFinish and unsigned NFTokenBurn as separate transactions. XRPL does not support atomic multi-transaction batches today.

**Mitigations implemented:**
- Redis settlement lock: `ward:settlement:{claim_id}` set atomically (NX) when EscrowFinish is built. Duplicate settlement attempts rejected with ValidationError.
- Rate limit: max 3 claims per NFT per 300 seconds (Step 9) — Redis-backed, distributed-safe
- NFT burn-on-settlement enforced at Step 7 on next claim attempt
- Ward never holds keys — cannot exploit the gap itself

**Residual risk:** If institution submits EscrowFinish but fails to submit NFTokenBurn, the settlement lock prevents retry. Institution must contact Ward to release the lock. This is acceptable — it prevents double settlement at the cost of requiring manual intervention on partial failures.

**Planned full fix:** Atomic multi-transaction batch when XRPL protocol supports it.

**ward_signed = False throughout — Ward cannot exploit this gap.**

## Rate Limiting

**Status:** Redis-backed sliding window — production ready.

**Implementation:** `check_rate_limit()` in `ward/primitives.py` uses Redis sorted sets for distributed, persistent rate limiting. Configure via `WARD_REDIS_URL` env var (default: `redis://localhost:6379/0`).

**Fallback:** In-memory fallback if Redis is unavailable — for dev/test only. Not distributed-safe. Production deployments must have Redis configured.

**Guarantee:** Max 3 claims per NFT per 300 seconds, enforced across all instances.

## Rejection Reasons On-Chain

**Status:** Implemented via memo hex encoding.

**Implementation:** `ValidationResult.rejection_memo_hex` contains the rejection reason hex-encoded for inclusion in an on-chain transaction memo. The API returns this field on every `/validate` response. Institutions include this memo when submitting any rejection acknowledgment transaction, creating a permanent on-chain audit trail.

**Format:** JSON `{"ward_reject": true, "step": N, "reason": "..."}` hex-encoded as UTF-8, suitable for XRPL Memo field.

**ward_signed = False — Ward never submits the rejection memo. Institution signs and submits.**
