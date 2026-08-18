# Signed-Tuple Evidence Adapter Specification

This specification describes the Ward adapter boundary for a threshold Schnorr signed-tuple attestation protocol. The specific protocol implementation is referenced generically pending its mainnet release.

## Purpose

Signed-tuple finalized facts enter Ward as canonical Evidence Snapshots before deterministic policy evaluation. The signed-tuple provider is treated as an evidence adapter, not as Ward's policy engine, signer, custodian, settlement actor, or institution reviewer.

The primitive signed-tuple artifact is not an opaque `sourceHash`, a `signed-tuple://` locator, or a Ward-asserted `validated: true` flag. The primitive is the signed tuple and threshold Schnorr signature that a reviewer can verify independently:

```text
Signed tuple + Schnorr signature
  -> Ward Evidence Snapshot
  -> Ward policy evaluation
  -> unsigned ward-resolution/v1 receipt
  -> replay / institution review / trust asset
```

## Boundary Model

The attesting network may provide:

- `DataUpdate { value, sourceId, registryVersion, signaturesRequired, canonicalTimestamp }`
- `SchnorrSignature { signature, commitment, signersBitmap }`
- optional chain anchor where the attestation was submitted or referenced
- registry data needed to reconstruct the signer set at `registryVersion`

Ward may normalize the signed tuple, reject malformed or secret-bearing payloads, preserve primitive verification fields, evaluate fixed policy, generate an unsigned receipt, replay the decision, and export a review packet.

Ward must not:

- collapse the signed-tuple primitive into only `sourceHash` plus opaque metadata
- require a `signed-tuple://` retrieval service for verification
- identify the signed-tuple provider as the attestor when the attestor is the signer coalition
- put Ward's policy conclusion, institution acceptance, or release approval inside the signed tuple
- hold keys, seeds, credentials, or signing material
- sign, submit, release, custody, settle, or execute assets
- treat signed-tuple attestation as institutional acceptance

## Trust Boundaries

| Boundary | Authority |
| --- | --- |
| Fact source | Named source encoded into the signed-tuple provider `apiConfig` |
| Attestor | Signer coalition identified by `signersBitmap` at `registryVersion` |
| Snapshot normalization | Ward adapter contract |
| Policy definition | Partner / institution |
| Deterministic evaluation | Ward engine |
| Signing and execution | External signer / institution / rail |
| Acceptance | Institution reviewer |

## Canonical Signed-Tuple Fact Input

```json
{
  "schema": "signed-tuple/v1",
  "dataUpdate": {
    "value": "0x0000000000000000000000000000000000000000000000000000000000000001",
    "sourceId": "0x5f3a0b37d8b8c6d66a9c2b29fefab7fb0c7df33d3f2dbd3ed8272fdd2f8f6c4e",
    "registryVersion": 42,
    "signaturesRequired": 3,
    "canonicalTimestamp": 1786221000
  },
  "schnorrSignature": {
    "signature": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "commitment": "0xcccccccccccccccccccccccccccccccccccccccc",
    "signersBitmap": "0x0000000000000000000000000000000000000000000000000000000000000017"
  },
  "anchor": {
    "rail": "xrpl",
    "txHash": "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "ledgerIndex": 105897321,
    "ledgerHash": "1D17F4E24C46C11BA7C454CEB246E24D6EC8977DE5BBB4DB3E1FF7572721B0E4"
  }
}
```

The signed preimage is:

```text
keccak256(
  keccak256("SIGNED_TUPLE_MESSAGE_V1"),
  value,
  sourceId,
  registryVersion,
  signaturesRequired,
  canonicalTimestamp,
  signersBitmap,
)
```

`keccak256("SIGNED_TUPLE_MESSAGE_V1")` is the bytes32 hash of the domain string. `signersBitmap` binds the signature to one exact signer coalition; a reviewer cannot reconstruct the message without it.

In the next signed-tuple provider release, `feedId` is replaced by `sourceId` as a breaking protocol change:

```text
sourceId = keccak256(JCS(apiConfig))
```

`JCS` means JSON Canonicalization Scheme (RFC 8785). The raw `apiConfig` is canonicalized before hashing so key order and whitespace do not change the source identity. This line carries Ward's same-subject correlation argument: a reviewer re-derives `sourceId` from `JCS(apiConfig)` and confirms that separate feeds refer to the same business subject. `owner` drops out of the protocol entirely.

`value` is a 32-byte word and represents the complete attested payload. Larger payloads should use `value = keccak256(rawPayload)`, with the raw payload delivered out of band and checked against the commitment by the consumer. Ward policy conclusions, release approvals, and acceptance statements are derived later by Ward or the institution; they are not signed-tuple source facts.

## Next Signed-Tuple Provider Release Breaking Change

Pending signed-tuple provider release — final form to be confirmed when `sourceId` ships. The signed-tuple provider is replacing `feedId` with `sourceId`. The new canonical payload is `value`, `sourceId`, `registryVersion`, `signaturesRequired`, `canonicalTimestamp`, and `signersBitmap`. `sourceId = keccak256(JCS(apiConfig))`, so the canonical `apiConfig` hash becomes the source identity directly. `owner` drops out of the protocol entirely.

## Ward Evidence Snapshot Output

Ward stores the primitive fields needed for independent verification. The snapshot may include a canonical hash of the snapshot itself, but that hash is not a replacement for signed-tuple primitive verification.

The output must preserve:

- `sourceEvidence.sourceType = signed_tuple`
- `sourceEvidence.sourceAdapter = signed-tuple/v1`
- `sourceEvidence.preimageAlgorithm = keccak256:SIGNED_TUPLE_MESSAGE_V1`
- `sourceEvidence.signatureScheme = schnorr`
- `data.dataUpdate`
- `data.schnorrSignature`
- optional native chain anchor

## Verification Levels

| Level | Name | What a verifier can prove |
| --- | --- | --- |
| Level 1 | Receipt integrity | The Ward receipt is schema-valid, unsigned, and hash-replayable. |
| Level 2 | Snapshot replay | The same Evidence Snapshot and policy replay to the same Ward decision. |
| Level 3 | Primitive-source verification | The verifier checks the primitive source directly, then replays Ward from the verified evidence. |

For signed-tuple attestations, Level 3 means signed-tuple verification. A reviewer verifies the `DataUpdate` and `SchnorrSignature` against the signer coalition at `registryVersion`, checks the optional chain anchor when present, then re-runs Ward policy evaluation from the verified tuple.

## Freshness And Finality Gate

Pilot-eligible signed-tuple facts must be based on independent nodes converging on a byte-identical value for a named source and round. The round either produces a valid threshold signature over that value or produces no fact.

Mutable endpoints are not sufficient by themselves. Live `current status` endpoints, drifting server-side timestamps, or values not keyed by an explicit identifier and timestamp may be useful context, but they do not satisfy the signed-tuple primitive verification model.

For default or dispute workflows, the correct fact is a finalized servicer or source record for a stated period, not a transient current-state response.

## Policy Boundary

Ward policy may ask whether a valid signer coalition attested a source fact, whether the tuple corresponds to the expected source and registry version, whether the value matches the required condition, whether the timestamp is inside the allowed review window, and whether the optional anchor matches the expected rail, transaction, ledger, or block.

Ward policy must assert a minimum `signaturesRequired` floor greater than 1. A threshold of 1 passes verification but provides no meaningful quorum guarantee. The minimum acceptable value for a governed workflow is 2.

Ward policy must not ask the signed-tuple provider to determine whether Ward should approve or reject the workflow, whether an institution accepts the outcome, or whether funds should be signed, released, settled, or transferred.

## Security Requirements

- Reject any payload containing private keys, wallet seeds, mnemonics, bearer tokens, API keys, passwords, or signing material.
- Reject payloads that exceed the configured adapter size limit.
- Preserve signature and tuple fields exactly; do not reorder or lossy-convert primitive material before verification.
- Record source adapter, source type, registry version, signer bitmap, captured time, and optional anchor in audit output.
- Do not use the signed-tuple provider as a secret transport. Placeholder secrets, not secrets, are what get hashed into the tuple.
- Keep Institution acceptance, signer identity, and settlement authorization outside the signed tuple unless the institution explicitly defines those as separate signed source facts.

## Pilot Contract

1. Receive one signed tuple and signature.
2. Normalize it into a Ward Evidence Snapshot without dropping primitive verification material.
3. Evaluate one fixed Ward policy against the snapshot.
4. Generate an unsigned Ward receipt.
5. Replay the Ward decision from the same snapshot.
6. Verify the signed tuple independently from the signed preimage, signer coalition, and optional anchor.
7. Preserve the signer boundary: the attesting network attests; Ward evaluates; the institution accepts/signs outside Ward.

## Open Questions

- Which public verifier and registry view should be referenced for reconstructing signer sets at `registryVersion`?
- Which rails will commonly provide anchors, and which fields are stable enough for long-term audit?
- How should raw out-of-band payloads be packaged when `value = keccak256(rawPayload)`?
- What minimum finality window should be required for each source system?

## apiConfig Correlation Boundary

The signed-tuple provider does not add a standalone `subject` field to the signed tuple. In the next signed-tuple provider release, a fact is identified by `sourceId`, where `sourceId = keccak256(JCS(apiConfig))`.

For Ward packets, the adapter must carry the reviewer-visible `apiConfig` alongside `sourceId`. The reviewer canonicalizes `apiConfig` with JCS, hashes that canonical form, and confirms that the path or params bind the same business subject, such as `/loans/L-4471/status` and `/loans/L-4471/dpd`.

If a workflow needs status, days-past-due, and balance, Ward should model them as separate signed-tuple source facts unless the partner intentionally supplies one hashed composite payload out of band. Separate source facts preserve signature granularity. Ward may correlate those facts under a policy window, but that window is a Ward policy assumption; the signed-tuple provider does not attest that all attributes were read at the same moment.


## Honesty And Limits

- Signed-tuple verification is not stable over time. Compromised signers may be discounted from the threshold after the fact.
- A receipt that verifies today may fail verification later if signer standing changes at the relevant `registryVersion` or under the signed-tuple provider's verifier rules.
- Ward receipts should record the verification inputs used at evaluation time, but reviewers must still re-check signer standing during later audits.


## Anchor Boundary

Signed-tuple verification is stateless. `signed-tuple verifier` verifies the signed tuple directly on each supported VM, including Solana. `submit_data_update` is an optional permissionless write and is not part of the trust path. A verified fact may have no chain anchor. Ward packets must not imply on-chain anchoring unless a chain, transaction, slot, or ledger locator is actually present.
