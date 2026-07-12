# XRPL Devnet Independent Verification Packet — 2026-07-12

This packet records the first unaffiliated independent verification pass over a
Ward Protocol XRPL Devnet lifecycle artifact.

It is intentionally scoped:

- XRPL Devnet only, not production or mainnet.
- Pre-resolution lifecycle evidence only.
- Not a security audit, investment endorsement, or statement about off-chain
  economic design.
- `ward_signed = False` throughout; Ward did not sign or submit settlement.

## Why this matters

Ward's thesis is not that Ward can claim its own validator passed. The standard
is that an independent reviewer can re-derive the result from public ledger
state and state exactly what was verified, what failed, and what remains out of
scope.

This run is the first design-partner proof of that review surface.

## Subject

| Field | Value |
| --- | --- |
| Protocol | Ward Protocol |
| Evidence type | XRPL Devnet lifecycle evidence, pre-resolution |
| Network | XRPL Devnet |
| Ledger index | `3,576,434` |
| Ledger close | `2026-07-11T19:05:40Z` |
| Certificate | Kairo Vault Technologies `KV-IV-2026-0712-001` |
| Certificate issue date | `2026-07-12` |
| Certificate status | Public demonstration, XRPL Devnet |

## Ledger Objects

| Object | Identifier |
| --- | --- |
| Policy NFT | `0001000036F849904DD7C2CD380C28491B5A6B33F120778FCE170ED600369234` |
| Vault | `D534C33D154CC9DC9365DEFA91636BFF7A88E82BE6E4745C7FF29E1D63B3E498` |
| LoanBroker | `751E7382FA9E61643541165D1A1B4476ECAD0D5478AB5955045008A15A6D91B0` |
| Loan | `EA35EBE2E57B8954988E252EA30D2A37C8695EDC44940D3247A77AD1A3529CD7` |
| Ward pool | `r44wBzcBbBj4Rjg4tEUZ838ztpRKu5GTFm` |
| Borrower / claimant | `rarevCgXgy7pmYgaGedycaLwDG4GBvSzV4` |
| Defaulted vault owner | `rMTdBsFt7bqP4bCe225eesjPnwvmCcZz5z` |

## Lifecycle Transactions

All listed lifecycle transactions returned `tesSUCCESS`.

| Step | Transaction hash |
| --- | --- |
| VaultCreate | `8109F9AF2F6425FCF71AFA6A8001B5B71BB95FB72671D1ED60DED92EA43EC5B8` |
| VaultDeposit | `B0FBA64020E989B70ADFD05591329ABDBCF23A6A444FA7697AF7BC903915B10E` |
| WardPolicyNFTokenMint | `EBC8DF5EC3F8CD7C820BE02029A6C26FDAABB4BA62530C974501B2C20994278D` |
| WardPolicyPremiumPayment | `A610078AC76BC781FDD14695B4FF3A6EF4DDBD8C3610160044C9B57EC2227C92` |
| LoanBrokerSet | `25F6A76E3074D7AF0346EE5DAF8624E4AE55AD819E0F41E505D8FA5D98FFAB14` |
| LoanBrokerCoverDeposit | `67F8F4793425E52E8522975F6EE9E339F6557AAC8926A7B9BA83B06E7E7D1093` |
| LoanSet | `E0DC8A820FB19AD76E1BA53FC67FF5786C0E64C398BEE8318EB20336BB74616A` |

## Ward Result

Ward's canonical Devnet evidence bundle reported:

- `approved = true`
- `steps_passed = 9`
- `ward_signed = false`
- `claim_payout_drops = 1,000,001`
- `vault_loss_drops = 1,000,001`
- `policy_coverage_drops = 2,000,000`
- settlement packet unsigned by Ward

The nine Ward-semantic check rules are published in
`docs/pilots/ward-semantic-check-rules.md`.

## Ward-Side Independent Reproduction

Ward's local independent verifier does not trust the checklist labels inside the
Ward evidence bundle. It re-derives the critical facts from the lifecycle and
Ward evidence artifacts:

```bash
python scripts/verify_devnet_evidence_independent.py \
  evidence/devnet/phase1-devnet-pre-resolution.json \
  evidence/devnet/ward-evidence-pre-resolution.json \
  --out evidence/devnet/independent-verification-pre-resolution.json
```

Current output:

- `approved_by_ward = true`
- `independently_verified = true`
- `ward_signed = false`
- `failures = []`
- `claim_payout_drops = min(1,000,001 loss, 2,000,000 coverage) = 1,000,001`
- `pool_balance_after_premium = 100,000,001`
- `default_ready_threshold = 837111912`
- `default_ready_ledger_time = 837111940`

The Ward-side independent verifier currently reports 12 derived checks:

1. all lifecycle transactions successful
2. default resolution not submitted
3. policy NFT matches artifact
4. policy URI binds vault, coverage, and pool
5. policy taxon and owner match
6. premium payment matches policy
7. vault, broker, and loan binding
8. claimant is borrower
9. pre-resolution default-ready timing
10. loss math bounded
11. pool solvent for claim
12. Ward never signed

## Unaffiliated Certificate

Kairo Vault Technologies independently re-derived the on-chain facts from raw
XRPL Devnet state without trusting Ward's validator output.

Their certificate states that 15 in-scope checks reconciled with zero failures,
including:

- all 7 lifecycle transactions validated with `tesSUCCESS`
- Vault, LoanBroker, and Loan objects exist on-ledger
- payout math recomputed as `min(loss 1,000,001, coverage 2,000,000) = 1,000,001`
- loss remains within coverage
- coverage pool solvency verified
- borrower owns the policy NFT
- default-ready timing independently satisfied

The certificate also states the correct limitations:

- XRPL Devnet, not production or mainnet.
- `ward_signed = false`.
- Not a security audit.
- Not a fitness, investment, off-chain logic, or economic-design endorsement.

## Addendum Requested

After this certificate, Ward published the public semantic rule surface in
`docs/pilots/ward-semantic-check-rules.md`. The next request to Kairo Vault is
an addendum or second pass that maps the four previously out-of-scope
Ward-semantic checks against those public rules:

- premium sufficiency
- policy-to-vault binding rule
- policy liveness
- rate limits and pool solvency rule

That second pass should bind the certificate to a Ward rules commit hash and
state whether each semantic check was independently recomputed, accepted under
the published Ward rule, or left out of scope.

## Public Claim Boundary

Acceptable public language:

> XRPL Devnet lifecycle independently recomputed from raw ledger state by an
> unaffiliated verifier.

Do not call this:

- a mainnet certification
- a production audit
- a statement that XLS-66 is live on mainnet
- proof that Ward can sign, custody, or override outcomes

The invariant remains:

> `ward_signed = False` — always.
