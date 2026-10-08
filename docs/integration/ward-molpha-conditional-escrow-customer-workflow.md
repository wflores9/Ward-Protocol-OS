# Ward × Molpha — Conditional Escrow Release | Customer Workflow Review

> **Status: PROPOSED / FOR TECHNICAL AND CUSTOMER-DISCOVERY REVIEW (8 October 2026).**
> This is an illustrative customer journey, **not** a deployed integration, completed pilot, verified customer requirement, commercial agreement, or endorsement by Molpha. No production customer or integration is represented here.

## The customer and their problem

An illustrative institutional escrow operator (the **Customer**) administers an escrow agreement. Its terms permit release only after an authorized external source attests that a specified condition has occurred, applicable restrictions have cleared, and the Customer approves the action. Today those checks can be distributed across external evidence, operations, risk/legal approval, and execution systems.

The Customer wants a reproducible answer to **what evidence was accepted, which fixed policy was applied, why the proposed release passed or failed, who approved it, and whether execution subsequently succeeded**.

**Boundary:** Molpha provides signed external evidence; Ward evaluates a fixed customer-defined policy and produces an **unsigned** resolution receipt; the Customer (or its authorized signing provider) approves and signs; the supported execution rail settles. **Ward never signs, submits, custodies, holds keys, or independently certifies the real-world truth of an attestation.**

## Illustrative end-to-end customer journey

| Step | Customer-facing experience | Proposed system responsibility | Result |
| --- | --- | --- | --- |
| 1. Configure | Customer registers an escrow agreement, permitted condition, evidence sources, policy version, signer roles, and approval route. | Customer owns legal terms, source trust, rule approval, and signer permissions. | Versioned policy and case bindings. |
| 2. Request | An authorized operator opens a release request for a specific escrow/obligation. | Customer workflow opens a case; no settlement action is sent. | Pending case with escrow and beneficiary identifiers. |
| 3. Observe | The approved external source observes the release condition. | Source produces the underlying observation; Molpha attests the agreed fact as a signed tuple. | Original signed bytes, signature, verification inputs, observation time and source identity (subject to confirmed schema). |
| 4. Verify and normalize | Case displays provenance and evidence validation state. | Proposed Molpha→Ward adapter verifies the agreed signature and source bindings, preserves original bytes, and constructs an evidence snapshot. | Verifiable evidence reference or explicit failure. |
| 5. Evaluate | Operator sees a policy determination and reasons. | Ward runs a frozen rule bundle against a frozen snapshot; emits a replayable **unsigned** receipt. | Eligible for institutional review / not eligible / incomplete (illustrative UI labels). |
| 6. Approve | Authorized officer reviews evidence, reasons, and the requested action. | Customer's existing authorization workflow records approval or rejection. | Separate institutional authorization record. |
| 7. Sign and execute | Approved action is signed and submitted by the Customer's authorized systems. | Supported rail/custody/execution infrastructure executes, independently of Ward. | Transaction reference and actual outcome; **Ward does not settle**. |
| 8. Reconcile and audit | Customer reviews the full case timeline and can reproduce the determination. | Link receipt, frozen policy, evidence, approval, and execution outcome without rewriting the original decision. | Replayable decision history and separate execution record. |

### Customer screen-by-screen storyboard (proposed UX)

1. **Case setup** — Agreement, escrow identifier, authorized beneficiary, release condition, permitted evidence provider, approval owner. **CTA:** Create release request.
2. **Await evidence** — Status `WAITING_FOR_ATTESTATION`; shows expected source and freshness window. No implied release authorization.
3. **Evidence received** — Shows Molpha tuple reference, verification status, observation time, source, and evidence snapshot hash; invalid evidence remains visible as rejected.
4. **Policy evaluation** — Shows fixed policy identity/version, per-check pass/fail reasons, receipt hash, and `ward_signed=false`. **CTA:** Submit for institutional review (not "Release funds").
5. **Approval** — Authorized Customer officer sees evidence and determination, may approve, reject, or request updated evidence; institutional controls remain authoritative.
6. **Execution tracking** — Only after approval, the Customer's signing/execution system submits the permitted action; show pending, settled, or failed independently of Ward's decision.
7. **Audit/replay** — Export or inspect frozen evidence, policy artifact, receipt, source-verification limitations, approval record, and actual transaction outcome.

## Proposed signed-tuple → Ward evidence boundary

The existing public [QuorumVault verification boundary](quorumvault-two-tier-boundary.md) already identifies a **Molpha signed tuple and Schnorr signature** as a candidate independently verifiable source when the tuple, signature, and public verifier inputs are supplied. This customer workflow builds on that boundary; it does **not** claim the adapter has been implemented or that a final Molpha schema has been agreed.

**Illustrative adapter envelope, not a Molpha API contract:**

```json
{
  "case_id": "example-escrow-041",
  "agreement_id": "example-agreement-041",
  "escrow_id": "example-escrow-017",
  "source_identity": "approved-source-A",
  "attested_condition": "INSPECTION_PASSED",
  "observed_at": "2026-10-08T14:00:00Z",
  "molpha_signed_tuple_original": "<original signed bytes / encoded tuple>",
  "signature": "<signature bytes>",
  "public_verifier_inputs": "<verification inputs>",
  "primitive_source_hash": "<hash of original signed material>"
}
```

The adapter must retain the **exact signed material**. Normalization must not change what the signature is claimed to cover. The policy must separately evaluate source authorization, agreement/escrow binding, observation freshness, condition satisfaction, and any on-ledger restrictions. A cryptographically valid signature demonstrates integrity and the configured signing identity, **not the factual truth of the observation**.

Where a policy contains both ledger-derivable and off-chain judgment rules, keep verification scopes separate as required by the existing QuorumVault document; do not label a mixed, non-re-derivable receipt as fully source-rederived.

## Illustrative policy and unsigned receipt

**Example policy:** `ESCROW_CONDITION_RELEASE_V1` (fictional). Checks: correct agreement and escrow; approved attestor; valid signature; correct condition; freshness; release limit; no blocking hold; current institutional approval required **after** Ward's evaluation.

**Illustrative conceptual receipt (not an existing API response):**

```json
{
  "case_id": "example-escrow-041",
  "policy_id": "ESCROW_CONDITION_RELEASE_V1",
  "policy_version": "1.0.0",
  "policy_artifact_hash": "<hash>",
  "evidence_snapshot_hash": "<hash>",
  "determination": "ELIGIBLE_FOR_INSTITUTIONAL_REVIEW",
  "reason_codes": ["REQUIRED_EVIDENCE_AND_POLICY_CHECKS_PASSED"],
  "receipt_hash": "<hash>",
  "ward_signed": false
}
```

The actual receipt schema and canonical hash rules must follow the repository's `ward-resolution/v1` and evidence snapshot definitions; the snippet above is **explanatory only**. An eligible determination is **not** approval or execution.

## Exception handling

| Condition | Required behavior |
| --- | --- |
| Signature invalid / wrong key | Reject evidence for evaluation; do not authorize release. |
| Evidence stale or missing | Return incomplete or ineligible under fixed policy; request new evidence. |
| Wrong agreement, escrow, or beneficiary | Fail binding check; stop the release path. |
| Condition not satisfied / conflicting source | Fail or escalate according to explicit institutional policy; no silent override. |
| Rule artifact or evidence changed | Create a new evaluation with a new frozen snapshot/version; preserve earlier receipts. |
| Institutional approval withheld or expired | No signing or execution, regardless of Ward determination. |
| Transaction rejected or rail unavailable | Record failed execution separately; preserve the original Ward determination. |
| External claim disputed | Escalate source-trust and factual dispute to Customer/source; signature validity alone does not resolve it. |

## Responsibility and commercial boundaries

| Responsibility | Customer | Molpha | Ward |
| --- | :---: | :---: | :---: |
| Agreement, approved sources, rule ownership, approvals | ✓ | | |
| Signed attestation of agreed external fact | | ✓ | |
| Evidence adapter, deterministic policy evaluation, unsigned receipt | | | ✓ |
| Institutional signing and authorized execution arrangement | ✓ | | |
| Actual ledger settlement | Customer's authorized execution rail | | **Never Ward** |

Commercial options discussed **without agreement or selection**: (1) Customer contracts Molpha directly and connects credentials; (2) Ward bundles purchased Molpha service; (3) wholesale/resale arrangement. Customer economics, liability, support, data access, and pricing remain open.

## Review questions for Molpha (Vitalii / James / Jeremy)

1. Does conditional escrow release accurately represent the customer-facing workflow Vitalii had in mind?
2. What are the **exact** signed tuple, Schnorr verification, key identity, serialization, timestamp, revocation/correction, and public verifier-input requirements?
3. Which party defines and vouches for the authorized external source and the meaning of the attested condition?
4. Can an independent verifier retain and validate the signed source material later without depending on a live Molpha retrieval endpoint?
5. How should source errors, disputes, corrections, or conflicting attestations be represented?
6. Which billing/integration arrangement is most practical for a first **hypothetical** customer walkthrough, without assuming an agreed partnership?

## Next validation gate

This document is intended to prompt **technical review and customer discovery**. A real integration requires confirmation of Molpha's actual data contract, source-trust responsibilities, Ward adapter tests and independent replay, institutional approval controls, execution-rail capabilities, and a genuine customer-owned workflow. **Do not represent this example as deployed or commercially validated.**

**Related public references:** [Ward core README](../../README.md) · [QuorumVault verification boundary](quorumvault-two-tier-boundary.md) · [Conditional release example](../../examples/conditional-release-input.json) · [Receipt schema](../../schemas/ward-resolution-receipt-v1.schema.json).
