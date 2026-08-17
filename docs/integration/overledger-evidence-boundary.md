# Overledger Evidence Boundary

ward_signed = False — always.

## What Overledger Provides

Overledger exposes attested state from connected networks including
XRPL, Ethereum, Solana, Hedera, Stellar, XDC, and others. For each
query, Overledger returns:

- The queried network and resource identifier
- The attested state at a canonical point in time
- A transaction or block reference anchoring the attestation
- The Overledger request ID and API version

## Evidence Snapshot Schema

Ward normalizes Overledger output into a `ward-evidence-snapshot/v1`
object:

```json
{
  "schema": "ward-evidence-snapshot/v1",
  "kind": "source_attestation",
  "label": "Overledger cross-chain state attestation",
  "source": "Overledger",
  "captured_at": "<ISO8601 timestamp>",
  "sourceEvidence": {
    "rail": "<network — xrpl | ethereum | solana | hedera | stellar | xdc>",
    "sourceType": "overledger_attestation",
    "sourceAdapter": "overledger/v1",
    "requestId": "<Overledger request ID>",
    "apiVersion": "<Overledger API version>",
    "resourceLocator": "<network-specific resource identifier>",
    "blockReference": "<block hash or ledger index>",
    "transactionReference": "<transaction hash if applicable>"
  },
  "data": {
    "attestedState": "<normalized state value>",
    "canonicalTimestamp": "<ISO8601 timestamp of attested state>"
  },
  "limits": [
    "Overledger attests state at the queried point in time. Ward evaluates fixed policy from that state.",
    "Ward policy conclusions are not Overledger-attested facts.",
    "Signing, custody, settlement, and institution acceptance remain outside Ward.",
    "On-chain anchor is optional — verification is stateless where Overledger exposes a public verifier."
  ]
}
```

## Replay

Ward supports three replay levels:

**Level 1 — Receipt integrity**: recompute the receipt hash from the
canonical receipt payload. Confirms the record was not altered after
production.

**Level 2 — Snapshot replay**: re-run Ward policy against the frozen
Evidence Snapshot. Confirms the decision follows from the supplied
evidence.

**Level 3 — Source re-derivation**: re-fetch the attested state from
the originating network using the block reference and resource locator,
re-normalize into an Evidence Snapshot, re-run policy, and compare
the derived decision to Ward's stated decision.

Level 3 is available where the originating network is publicly
queryable. For private or permissioned networks reachable only through
Overledger, Level 2 is the practical ceiling.

## Multi-Chain Workflows

A single Ward case may incorporate Evidence Snapshots from multiple
networks via Overledger. Each snapshot is independently attested and
independently replayable. Ward correlates snapshots within a case by
case ID and policy evaluation window.

Ward does not attest that snapshots from different networks were
captured simultaneously. The correlation window is a Ward policy
assumption, not an Overledger-attested fact.

## Honesty Section

- Overledger's attestation is the source of truth for cross-chain
  state. Ward does not independently verify network state.
- Ward policy conclusions derived from Overledger attestations are
  Ward's conclusions, not Overledger's.
- On-chain anchoring is optional. A verified fact may leave no
  on-chain trace if `submit_data_update` was not called.
- For permissioned or private networks, an independent reviewer
  cannot re-derive state without Overledger access. Level 2 replay
  (snapshot integrity) applies in those cases.
- ward_signed = False — always.

## Integration Path

1. Overledger queries the target network and returns attested state
2. Ward Evidence Adapter normalizes the response into an Evidence Snapshot
3. Ward Policy Engine evaluates the snapshot against the agreed rule bundle
4. Ward produces an unsigned resolution record with the Evidence Snapshot attached
5. The institution reviews the record, signs if approved, and settles through its own infrastructure
