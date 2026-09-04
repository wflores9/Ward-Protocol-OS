# XRPL Devnet packet-bearing evidence run - 2026-09-01

Public evidence certificate **WARD-DEVNET-20260901-001**. Issued with archive-on-issuance.
This is operator-run Ward evidence, not a Kairo Vault Technologies GK certificate.

KV-IV-2026-0712-001 is unchanged: unreproducible/legacy, raw_reads_archive null,
Devnet ledger 3576434.

## Result

- Network: XRPL Devnet, rippled 3.3.0
- Pinned ledger index: 4949701
- Pre-resolution ledger index: 4949752
- Ledger close: 2026-09-01T05:09:42Z
- Ward decision: approved
- Ward semantic checks: 9 of 9 passed
- Independent verification: passed (failures: [])
- Claim payout: 1000001 drops
- Unsigned settlement packet: present
- Settlement submitted: no
- `ward_signed = False` — always

The lifecycle producer signed disposable Devnet setup transactions using
ephemeral faucet wallets. Ward did not sign or submit the settlement packet.

## Files and SHA-256

- `phase1-devnet-pre-resolution-2026-09-01.json`
  `ed05928158f69cd57212194ff0e00687f5e915136caebe69907507f3a1346a14`
- `ward-evidence-pre-resolution-2026-09-01.json`
  `c0ab64470b38a9fa3f7a08435c9d9ceb8f331cfcf014a2aa59ae4f34e8a4d83f`
- `ward-evidence-pre-resolution-2026-09-01.raw-reads.json`
  `967e69133e38fc296af3076b0906701b06d22d0e71ffb9aa1dc71e0661c66c04`
- `ward-evidence-pre-resolution-2026-09-01.independent-verification.json`
  `b909cf9de8017574fa9891eb207280f4d8f36fbf68ac903e2aab7917b475ad96`

## Reproduce

From the repository root:

```bash
python3 scripts/validate_partner_evidence.py \
  docs/security/evidence/devnet/2026-09-01/ward-evidence-pre-resolution-2026-09-01.json

python3 scripts/verify_devnet_evidence_independent.py \
  docs/security/evidence/devnet/2026-09-01/phase1-devnet-pre-resolution-2026-09-01.json \
  docs/security/evidence/devnet/2026-09-01/ward-evidence-pre-resolution-2026-09-01.json

python3 scripts/check_certificate_reproducibility.py
```

Expected results:

- Structural gate: `Evidence bundle accepted`
- `approved_by_ward: true`
- `independently_verified: true`
- `failures: []`
- `WARD-DEVNET-20260901-001`: reproducible from raw_reads_archive
- `KV-IV-2026-0712-001`: unreproducible/legacy
