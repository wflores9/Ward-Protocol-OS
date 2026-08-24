# XRPL Devnet packet-bearing evidence run - 2026-08-24

This directory archives a Ward-generated XRPL Devnet evidence run. It is not an
external certificate and has not been attributed to Kairo Vault Technologies GK
or any other independent reviewer.

## Result

- Network: XRPL Devnet, rippled 3.3.0
- Pinned ledger index: 4740522
- Ward decision: approved
- Ward semantic checks: 9 of 9 passed
- Claim payout: 1,000,001 drops
- Unsigned settlement packet: present
- Packet action: XRPL Payment from the policy pool to the claimant
- Settlement submitted: no
- `ward_signed = False` — always

The lifecycle producer signed disposable Devnet setup transactions using
ephemeral faucet wallets. Ward did not sign or submit the settlement packet.

## Provenance

- Evidence generation commit: `487c42ce6d6a4392b7f2c0c740181564271eb4a9`
- Independent packet-binding verifier commit: `2c82a3898c040083b742eb5a7dffabc5bc1250f7`
- Raw-read archive completeness: complete, 31 reads
- Reproducibility at issuance: pinned ledger available from the public Devnet RPC

## Files and SHA-256

- `phase1-devnet-pre-resolution-2026-08-24.json`
  `1cff45f2a781a43f17df8fc1dd0960a25a96a120b73bd28ff6c87390262087e7`
- `ward-evidence-pre-resolution-2026-08-24.json`
  `962dcaac0c71b9ecebaa449fdcf596ee56f522119b751520522c985b6e35e7c6`
- `ward-evidence-pre-resolution-2026-08-24.raw-reads.json`
  `6efc5ed82230194f2559b42aa4b25ad027f919f2bbec0611b83f149b28fa9fad`
- `ward-evidence-pre-resolution-2026-08-24.independent-verification.json`
  `9f6cb8a9ffc0ab4e995fbd2535f4c4bf8a3cfc0ccc3f281b04ced2c7ffa4b71f`

The independent verifier derives the lifecycle, policy, premium, vault/loan
binding, payout, solvency, and unsigned packet binding without trusting Ward's
published check array. It is Ward-maintained verification code, not third-party
attestation.

## Reproduce

From the repository root:

```bash
python3 scripts/validate_partner_evidence.py \
  docs/security/evidence/devnet/2026-08-24/ward-evidence-pre-resolution-2026-08-24.json

python3 scripts/verify_devnet_evidence_independent.py \
  docs/security/evidence/devnet/2026-08-24/phase1-devnet-pre-resolution-2026-08-24.json \
  docs/security/evidence/devnet/2026-08-24/ward-evidence-pre-resolution-2026-08-24.json
```

Expected results:

- Structural gate: `Evidence bundle accepted`
- `approved_by_ward: true`
- `independently_verified: true`
- `failures: []`
- `unsigned_packet_matches_resolution: passed`
- `ward_signed: false`
