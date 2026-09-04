# Operator SUPERSEDE — WARD-DEVNET-20260902-001

XRPL Devnet only. Not production or mainnet. `ward_signed = False` always.
`independently_verified = false`.

This certificate is an **operator-run SUPERSEDE** of the
`WARD-DEVNET-20260901-001` operator receipt. It is **not** a Kairo Vault
Technologies GK independent verification. It does **not** retract or rewrite:

- `KV-IV-2026-0712-001` (frozen unreproducible/legacy)
- `WARD-DEVNET-20260901-001` (kept as-is, including `independently_verified: true`)

## What this run is

A later Devnet lending lifecycle was reconstructed read-only from XRPL Devnet
at two pins. Loan, LoanBroker, and Vault were discovered from LoanSet metadata
(`C4A6A5626F6B4CE2B1513520CB184B9507EA91A772FB73614721929E85EBF942` tesSUCCESS
in ledger 4970389), not from prior locators.

`scripts/run_xrpl_devnet_evidence.py` performed canonical validation pinned to
the evaluation ledger. FeeSettings was read with `ledger_entry`
`{"fee": true, "ledger_index": <pin>}` at both pins. The chain-confirmed
FeeSettings index at both pins is
`4BC50C9B0D8515D3EAAE1E74B29A95804346C491EE1A95BF25E4AAB854A6A651`
(ReserveBase 1000000, ReserveIncrement 200000, BaseFee `"1"`,
ReferenceFeeUnits 10). Those raw `ledger_entry` results are archived on the
operator certificate. An unsigned settlement packet was prepared. Settlement
was not submitted. Ward did not sign.

Operator verification (`--verifier-role operator`) re-derived policy, premium,
vault/loan binding, default-ready timing at the evaluation pin, payout,
solvency, and packet binding. That path always sets
`independently_verified: false`.

## Identifiers

- Certificate: `WARD-DEVNET-20260902-001`
- Network: XRPL Devnet (`https://s.devnet.rippletest.net:51234`)
- Issuance pin: `4970389` /
  `8CFDACA5A48F98ED2B3403E227211DA5DF40E29C5C1FC023645AD8ED789B9811` /
  close_time `841620142`
- Evaluation pin: `4970443` /
  `4334E6D89D0974E9E64B3D976F29E8BB862D7CE005420C2DEEF80D83979FCEE5` /
  close_time `841620310`
- Policy NFT: `0001000071D83DC56AA2B54109B20A7BAB1474A448972F00AC9B5D3F004BD78B`
- Vault: `8E4DF1B9E9B2236337EAD52997F31E7F3034C868F3720B609F463D6DFC4BB3BB`
- LoanBroker: `A79566221134207ED5832BDAA812A024DD1F530AD49CBE77E664DB24D4187794`
- Loan: `C40A6982236B411D963C0996BB4F56DA12FFFBA34D5A0584DC172D3040053963`
- Pool: `raDLoN4ByQaJUvf5LGDUz7qvG1X1y9FU3K`
- Claimant: `rB4xQPMUuxuwLLZW4jtsbJK5Cc5f2oqL6J`
- Defaulted vault owner: `rYxPGyS5f7XsePWN4z74BVDSCoqdyfhNP`

## Result

- Approved: yes
- Steps passed: 9 / 9
- Independently verified: **no**
- Claim payout: 1000001 drops
- Vault loss: 1000001 drops
- Policy coverage: 2000000 drops
- Coverage ratio (usable / payout) after FeeSettings reserves: 99x
- Unsigned packet present: yes
- Ward signed: no

## Archive

Complete `ward-raw-ledger-reads/v1` document:

`docs/security/evidence/archives/ward-evidence-pre-resolution-2026-09-02.raw-reads.json`

Operator SHA-256: `372cd7bed0cf9c4864cc047a90f8c40cc1dd8888d849edb4147eba240e40c87e`

Kairo's independent archive sha256
`50090fc373b39ab16cbf057a63e82a2611a6462307a462de9700ad627dd6f6ba`
(23 reads) is a different artifact and is not this file.

Weekly reproducibility re-proofs from this archive and does not query public
Devnet RPC.

## Limitations

- Devnet evidence only.
- Operator-run SUPERSEDE; not third-party attestation.
- Does not replace KV-IV or rewrite 20260901-001.
- Settlement packet remains unsigned and unsubmitted.
