# Ward Review Packet - Netten Circles Tax Reserve Synthetic Pilot

## Scope

This packet maps the Netten Circles tax-reserve workflow Jermaine described into Ward's controlled pilot shape. It is synthetic and non-sensitive: no live customer funds, no production private data, and no signing authority is held by Ward.

## Workflow Map

- Workflow: Netten Circles tax reserve release review
- Scenario: freelancer or agency completes a $1,500 job and reserves 50% ($750) for tax season.
- Review window: 72 hours after client-side review begins.
- Parties: freelancer/agency, client, Netten/Circles release authority.
- Trigger: job completed, reserve created, review window closed, and no client disapproval of assets.
- Expected output: ward-resolution/v1 receipt plus an unsigned 
etten.circle_release_review action.

## Evidence Bundle

- Authoritative state: Netten Circles tax-reserve state for circle-tax-reserve-001.
- Policy artifact: ward.netten-circles-tax-reserve@1.0.0.
- Trigger evidence: circle-job-completed-001 with 72-hour review window closed.
- Evidence locator: xrpl:netten-circle/circle-tax-reserve-001/circle-job-completed-001.

## Deterministic Evaluation

- Job completed: true
- Reserve created: true
- Reserve amount matches policy: true (1500 * 50% = 750)
- Review window closed: true
- Client disapproved assets: false
- Signer remains external: true

## Receipt Artifact

- Receipt schema: ward-resolution/v1
- Receipt id: $(@{assumptions=System.Object[]; case=; checks=System.Object[]; decision=approved; engine_version=0.2.10; evidence=System.Object[]; observed_at=1700000300; receipt_hash=74c264b4a87d9a71da618823815994db1bff32b67201c51c0cc925ac56b2752e; receipt_id=wr_74c264b4a87d9a71da618823; rule_bundle=; schema_version=ward-resolution/v1; unsigned_actions=System.Object[]; ward_signed=False}.receipt_id)
- Receipt hash: $(@{assumptions=System.Object[]; case=; checks=System.Object[]; decision=approved; engine_version=0.2.10; evidence=System.Object[]; observed_at=1700000300; receipt_hash=74c264b4a87d9a71da618823815994db1bff32b67201c51c0cc925ac56b2752e; receipt_id=wr_74c264b4a87d9a71da618823; rule_bundle=; schema_version=ward-resolution/v1; unsigned_actions=System.Object[]; ward_signed=False}.receipt_hash)
- Decision: $(@{assumptions=System.Object[]; case=; checks=System.Object[]; decision=approved; engine_version=0.2.10; evidence=System.Object[]; observed_at=1700000300; receipt_hash=74c264b4a87d9a71da618823815994db1bff32b67201c51c0cc925ac56b2752e; receipt_id=wr_74c264b4a87d9a71da618823; rule_bundle=; schema_version=ward-resolution/v1; unsigned_actions=System.Object[]; ward_signed=False}.decision)
- Ward signed: $(@{assumptions=System.Object[]; case=; checks=System.Object[]; decision=approved; engine_version=0.2.10; evidence=System.Object[]; observed_at=1700000300; receipt_hash=74c264b4a87d9a71da618823815994db1bff32b67201c51c0cc925ac56b2752e; receipt_id=wr_74c264b4a87d9a71da618823; rule_bundle=; schema_version=ward-resolution/v1; unsigned_actions=System.Object[]; ward_signed=False}.ward_signed)
- Unsigned action type: 
etten.circle_release_review

## Replay Verification

- Replay status: matched
- Independent verifier: scripts/verify_resolution_receipt.py
- Hash verification: true

## Signer Boundary

Ward evaluates the tax-reserve workflow and prepares a receipt. Ward does not custody funds, sign transactions, release escrow, settle reserves, or override Netten/client/freelancer authority.

The external release authority remains: reelancer/agency + client.

## Institution Review Status

- Status: ready for Netten/Jermaine review
- Reviewer acceptance: not yet recorded
- Partner data required before live pilot: one non-sensitive Circles example with agreed source of truth, release condition, dispute rule, and external signer.

## Limitations

- This is a synthetic pilot fixture, not a production deployment.
- The workflow assumes supplied facts are captured from Netten/Circles or an agreed evidence adapter.
- A client disapproval or open review window must block the release-review path.
- Production use still requires partner review, independent replay, and explicit acceptance/blocking reasons.