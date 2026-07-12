# Ward Semantic Check Rules

This document publishes the Ward-side rules behind the nine claim validation
checks. It is meant for design partners and independent reviewers who want to
separate:

- ledger-derived facts they can recompute directly from XRPL object state, and
- Ward-semantic checks that depend on Ward's published policy rules.

This is not a mainnet-readiness claim. The current lifecycle evidence is XRPL
Devnet/pre-mainnet evidence, and Ward preserves `ward_signed = False`: Ward
reads state and returns validation evidence; the institution signs any
settlement action.

## Eligibility Pre-Gates

XLS-70 credentials and XLS-80 permissioned-domain membership are opt-in
eligibility pre-gates controlled by environment configuration. They are not part
of the nine conformance checks unless explicitly enabled for a deployment.

When enabled, the credential/domain gate must pass before Step 1 begins. When
disabled, the nine-step flow below is unchanged.

## Constants

| Constant | Current value | Meaning |
| --- | ---: | --- |
| `WARD_POLICY_TAXON` | `281` | Canonical Ward policy NFT taxon |
| `CLAIM_RATE_LIMIT_MAX` | `3` | Maximum otherwise-valid claim attempts per policy NFT |
| `CLAIM_RATE_LIMIT_WINDOW_SECONDS` | `300` | Rate-limit window in seconds |
| `MIN_COVERAGE_RATIO` | `1.5` | Minimum usable pool balance divided by payout |
| `XRPL_BASE_RESERVE_DROPS` | `20_000_000` | XRPL base account reserve used in pool solvency |
| `XRPL_OWNER_RESERVE_DROPS` | `2_000_000` | XRPL owner reserve per owned object |

## Nine Checks

Canonical evidence labels:

| Step | Label |
| ---: | --- |
| 1 | Policy NFT located |
| 2 | Coverage and premium confirmed |
| 3 | Vault binding verified |
| 4 | Default signal verified |
| 5 | Loss math bounded |
| 6 | Coverage pool solvent |
| 7 | Policy still live |
| 8 | Claimant ownership proven |
| 9 | Pool solvency and rate limits |

### 1. Policy NFT Located

Purpose: prove the claimant currently presents a Ward policy NFT with the
canonical policy taxon.

Inputs:

- `claimant_address`
- `nft_token_id`
- claimant `AccountNFTs`

Rule:

Scan the claimant account's NFTs for the submitted policy NFT ID and require
`NFTokenTaxon == 281`.

Reject when the NFT is missing or has a non-Ward taxon.

### 2. Coverage and Premium Confirmed

Purpose: bind policy coverage to immutable NFT URI data and prove the premium
memo reached the pool.

Inputs:

- policy NFT URI
- `claimant_address`
- `pool_address`
- pool `AccountTx`

Rule:

Decode the NFT URI, require a live expiry, derive `coverage_drops` from compact
field `c` or legacy field `coverage_drops`, and find a matching
`ward/policy-premium` payment memo for claimant, pool, policy NFT, and coverage.

Reject on missing or expired metadata, non-positive coverage, or missing premium
memo.

### 3. Vault Binding Verified

Purpose: prevent cross-vault claims.

Inputs:

- policy NFT URI
- `defaulted_vault`

Rule:

Require the policy vault field `v` or `vault_address` to equal the submitted
`defaulted_vault`.

Reject when the policy covers a different vault.

### 4. Default Signal Verified

Purpose: derive default readiness and net depositor loss from the loan and
broker ledger objects.

Inputs:

- `loan_id`
- `Loan` ledger object
- `LoanBroker` ledger object
- ledger close time

Rule:

Accept an on-chain `lsfLoanDefault` flag. Before the default-resolution
transaction is submitted, accept default readiness only when:

```text
ledger_time >= NextPaymentDueDate + GracePeriod
```

and the loan still has positive outstanding value. Net depositor loss is derived
as gross loan value minus first-loss capital absorbed by the `LoanBroker` cover
rules.

Reject when the default flag/readiness is absent or the derived net loss is zero.

### 5. Loss Math Bounded

Purpose: keep payout bounded by actual loss and policy coverage.

Inputs:

- `net_depositor_loss`
- `coverage_drops`

Rule:

Require positive net depositor loss and compute:

```text
payout = min(net_depositor_loss, coverage_drops)
```

Reject when loss is not positive. Ward must never approve payout above loss or
coverage.

### 6. Coverage Pool Solvent

Purpose: prove the pool has enough usable balance before a claim can proceed.

Inputs:

- pool `AccountInfo`
- `OwnerCount`
- `net_depositor_loss`

Rule:

Compute:

```text
usable_drops = Balance - (20_000_000 + OwnerCount * 2_000_000)
```

Require `usable_drops >= net_depositor_loss`.

Reject when pool `AccountInfo` is unavailable, usable balance is negative, or
usable balance is below the loss.

### 7. Policy Still Live

Purpose: prevent replay with a burned or unavailable policy NFT.

Inputs:

- claimant `AccountNFTs`
- `nft_token_id`

Rule:

Reuse the Step 1 NFT read and require the policy NFT still exists.

Reject when the NFT is missing or taxon-mismatched at validation time.

### 8. Claimant Ownership Proven

Purpose: prove the claimant still controls the policy NFT used for the claim.

Inputs:

- claimant `AccountNFTs`
- `claimant_address`
- `nft_token_id`

Rule:

Require the claimant account's NFT set to contain the policy NFT at validation
time.

Reject when the claimant does not currently hold the NFT.

### 9. Pool Solvency and Rate Limits

Purpose: avoid repeated claim-window consumption and enforce the final solvency
ratio.

Inputs:

- `nft_token_id`
- pool `AccountInfo`
- `payout`

Rule:

Allow at most 3 otherwise-valid claim attempts per policy NFT per 300 seconds.
Then compute usable pool balance using the same reserve formula as Step 6 and
require:

```text
usable_drops / max(payout, 1) >= 1.5
```

Reject when the rate limit is exceeded, pool data is unavailable, usable balance
is below payout, or the coverage ratio is too low.

## Independent Verification Boundary

An unaffiliated verifier can currently recompute the Devnet lifecycle facts from
raw object state:

- lifecycle transaction success
- policy NFT ID and taxon
- policy URI coverage and pool binding
- premium memo binding
- vault, broker, and loan linkage
- claimant equals borrower
- default-ready ledger time
- payout equals `min(loss, coverage)`
- pool balance covers payout
- `ward_signed = False`

The next verification upgrade is to map each independent check directly to the
rules above and attach the rule version/hash to the evidence bundle.
