cat > docs/integration/quorumvault-two-tier-boundary.md <<'EOF'
# QuorumVault Verification Boundary

## Purpose

This document defines how QuorumVault should verify Ward outputs without trusting Ward as the source of truth.

Ward prepares evidence, evaluates fixed policy, and emits unsigned resolution receipts. Ward does not custody funds, hold signing keys, submit settlement transactions, or become the institutional authority.

QuorumVault should verify Ward outputs according to two levels:

1. Receipt and snapshot integrity.
2. Source re-derived decision verification.

The core rule is:

> Never trust a claimed status when the primitive source can be independently re-derived.

## Boundary Principle

Ward is not the authority over the underlying asset, ledger, escrow, or attestation source.

Ward is responsible for:

- normalizing evidence into Evidence Snapshots,
- applying a fixed rule bundle,
- producing an unsigned receipt,
- preserving the signer boundary,
- making replay possible.

QuorumVault is responsible for deciding how much of that output can be independently verified from primitive source material.

## Tier 1: Receipt And Snapshot Integrity

Use Tier 1 when the underlying source cannot be independently queried or re-derived by QuorumVault.

Examples:

- Netten Circles tax-reserve workflow without a public source API.
- Off-chain escrow state supplied as a snapshot.
- Private enterprise records supplied by a partner.
- Any workflow where the source locator is not independently resolvable.

Tier 1 verifies:

- receipt schema is valid,
- `ward_signed = false`,
- receipt hash recomputes from canonical payload,
- evidence snapshot hash recomputes,
- rule bundle is present,
- signer boundary is preserved,
- no key material or secret-like fields are present,
- replay from the supplied snapshot matches the receipt.

Tier 1 does **not** prove the external-world fact was true. It proves that Ward's decision record is intact, unsigned, and replayable from the supplied evidence snapshot.

## Tier 2: Source Re-Derived Verification

Use Tier 2 when the underlying source can be independently queried, recomputed, or cryptographically verified by QuorumVault.

Examples:

- XRPL ledger evidence with ledger index, ledger hash, transaction hash, and object ID.
- Solana evidence with slot, signature, program ID, account keys, and account-state hash.
- Molpha signed tuple where the verifier can validate the tuple and Schnorr signature against public verifier inputs.
- Any adapter that exposes a primitive locator and enough source material for independent re-derivation.

Tier 2 verifies:

- everything in Tier 1,
- primitive source evidence can be independently fetched or verified,
- normalized Evidence Snapshot matches the primitive source,
- rule bundle re-runs against independently reconstructed evidence,
- derived decision matches Ward's stated decision,
- derived receipt hash matches Ward's receipt hash.

Tier 2 proves more than receipt integrity. It proves the decision was justified against independently available source evidence.

## Required Inputs

A QuorumVault verification packet should include:

```json
{
  "ward_receipt": {
    "schema": "ward-resolution/v1",
    "receipt_hash": "8c211b2a...",
    "ward_signed": false,
    "decision": "approved",
    "rule_bundle": [],
    "evidence": []
  },
  "evidence_snapshots": [],
  "source_evidence": []
}
```

For ledger-verifiable workflows, `source_evidence` should include primitive locators.

Example XRPL source evidence:

```json
{
  "rail": "xrpl",
  "ledger_index": 105897321,
  "ledger_hash": "1D17F4...",
  "tx_hash": "A82F...",
  "object_id": "..."
}
```

Example Solana source evidence:

```json
{
  "rail": "solana",
  "slot": 291234567,
  "signature": "5h6...",
  "program_id": "Escrow111...",
  "account": "8x9...",
  "account_state_hash": "9f2..."
}
```

## Verification Algorithm

QuorumVault should:

1. Validate the receipt schema.
2. Confirm `ward_signed = false`.
3. Reject any receipt or snapshot containing private keys, seeds, mnemonics, signing keys, custody credentials, or settlement authority.
4. Recompute the receipt hash from the canonical payload excluding derived fields.
5. Recompute each Evidence Snapshot hash.
6. Determine whether source evidence is independently resolvable.
7. If source evidence is not independently resolvable, classify the result as Tier 1 only.
8. If source evidence is resolvable, fetch or verify the primitive source.
9. Normalize the primitive source into the same Evidence Snapshot shape.
10. Re-run the receipt rule bundle against the reconstructed evidence.
11. Compare the derived decision with Ward's stated decision.
12. Compare the derived receipt hash with Ward's receipt hash.
13. Emit verification result with explicit limitations.

## Output Shape

A verifier result should be explicit about level and limits:

```json
{
  "verification_level": "source_rederived",
  "matched": true,
  "decision": "approved",
  "ward_signed": false,
  "limitations": []
}
```

For off-chain workflows:

```json
{
  "verification_level": "receipt_snapshot_integrity",
  "matched": true,
  "decision": "approved",
  "ward_signed": false,
  "limitations": [
    "Source evidence was not independently queryable by the verifier."
  ]
}
```

## Workflow Examples

### XRPL Conditional Release

Expected level: Tier 2.

QuorumVault can use the ledger index, ledger hash, transaction hash, and object ID to re-fetch ledger evidence, reconstruct the Evidence Snapshot, re-run the rule bundle, and compare the derived decision to the Ward receipt.

### Netten Circles Tax Reserve

Expected level: Tier 1 unless Netten exposes independently queryable source evidence.

Ward can verify that the receipt and Evidence Snapshot are replayable. QuorumVault cannot independently prove the external Netten state unless Netten provides a source API, signed fact, ledger anchor, or another primitive locator.

### Molpha Finalized Fact

Expected level: Tier 2 when the signed tuple, public verifier inputs, and signature are included.

QuorumVault should verify the tuple and signature directly. It should not depend on a Molpha retrieval service or Ward's copy of the fact.

### Solana Evidence Adapter

Expected level: Tier 2 when the packet includes slot, signature, program ID, account keys, account-state hash, and enough source material to re-fetch or verify account state.

## Expected Output Artifact

An expected-output artifact may be useful for demos, fixtures, or developer onboarding, but it is not the verification primitive.

For source-verifiable workflows, QuorumVault should derive the output from:

- primitive source evidence,
- Evidence Snapshot normalization,
- fixed rule bundle,
- receipt schema.

The expected output can help explain the intended result, but correctness should come from re-derivation.
EOF

git diff --check
git add docs/integration/quorumvault-two-tier-boundary.md
git commit -m "Document QuorumVault verification boundary"
git push -u origin docs/quorumvault-two-tier-boundary

gh pr create \
  --base main \
  --head docs/quorumvault-two-tier-boundary \
  --title "Document QuorumVault verification boundary" \
  --body "Adds the two-tier QuorumVault verification model: receipt/snapshot integrity for off-chain workflows, and source re-derived verification for ledger or cryptographically verifiable workflows."
