# Evidence changelog

Record of every change to a published evidence file under
`docs/security/evidence/`. `ward_signed = False` — always.

## Append-only rule (effective on merge of this file)

1. An evidence file's bytes never change after it has been published: in a
   commit on `main` of either Ward repository, on wardprotocol.org, or in the
   Ward-Protocol-OS public repository.
2. A correction is published as a **new sibling file**
   (`<name>.correction-YYYY-MM-DD.json`) together with a new entry below and in
   `evidence-versions.json`. The original stays at its path with its original
   bytes.
3. Every entry records: file, old and new SHA-256, commit, date (UTC and ET),
   what changed, and the reason **as recorded in git history**. If no reason
   was recorded, the entry says `reason: not recorded`.
4. README SHA-256 pins list every published version of a file, not only the
   latest.
5. `tests/test_evidence_versions.py` fails CI when any evidence JSON under
   `docs/security/evidence/devnet/` hashes to a value not listed in
   `evidence-versions.json`, so an in-place edit cannot land silently.
6. Entries in this file and in `evidence-versions.json` are never edited or
   removed; mistakes are corrected by a new entry.

## Entries (oldest first)

The three changes below were made **before** this rule existed. They are
in-place edits and are disclosed here. In each case both versions pass the
structural gate (`scripts/validate_partner_evidence.py`) and the operator
re-derivation (`scripts/verify_devnet_evidence_independent.py
--verifier-role operator`, `failures: []`), rechecked offline 2026-09-25.
None of them changes a ledger fact: transaction hashes, ledger indexes, raw
reads, amounts, the decision, and `ward_signed = false` are identical across
versions.

### E-2026-08-27-1 · Aug 24 Devnet run · transaction type labels

- File: `docs/security/evidence/devnet/2026-08-24/ward-evidence-pre-resolution-2026-08-24.json`
- Original (published 2026-08-24, commit `90e2cd3a`): SHA-256
  `962dcaac0c71b9ecebaa449fdcf596ee56f522119b751520522c985b6e35e7c6`
- Edited: commit `af4c78745c1345bdf7279177cbf4c897cff2b362`,
  2026-08-27 17:32 UTC (13:32 ET), author Will Flores, pushed directly to
  `main` (no pull request). SHA-256
  `7793a1d7ec2a2579c99ccbde2c13ec2770be52c000858ddeed1156d37bcbe094`
- What changed (6 added, 4 removed lines): in `transactions[]`,
  `"type": "WardPolicyNFTokenMint"` became `"type": "NFTokenMint"` plus
  `"ward_role": "policy_nft_mint"`, and `"type": "WardPolicyPremiumPayment"`
  became `"type": "Payment"` plus `"ward_role": "policy_premium_payment"`.
  Hashes, ledger indexes, and engine results unchanged.
- Reason as recorded: commit message "Fix Devnet lifecycle transaction type
  labels" (no body, no PR, no issue). No fuller rationale is recorded.
  Context only, not a stated reason: the 2026-09-01 certificate commit
  `28cdcdf4` uses the same convention ("Fix NEW packet type vs ward_role
  (Payment/NFTokenMint)").
- README pin: the Aug 24 README kept pinning `962dcaac…` until PR #36
  (merged 2026-09-09 19:12 UTC / 15:12 ET, commits `7c1f4ac6`, `68419e2e`)
  re-pinned it to `7793a1d7…`. Between 2026-08-27 and 2026-09-09 the private
  README pin did not match its file.
- Public repo: Ward-Protocol-OS still carried the **original** bytes
  (`962dcaac…`) with a matching pin at commit `41f34b6d`, so the two
  repositories disagreed until this changelog.

### E-2026-09-07-1 · WARD-DEVNET-20260901-001 · generation commit backfill

- File: `docs/security/evidence/devnet/2026-09-01/ward-evidence-pre-resolution-2026-09-01.json`
- Original (published 2026-09-01, commit `28cdcdf4`): SHA-256
  `c0ab64470b38a9fa3f7a08435c9d9ceb8f331cfcf014a2aa59ae4f34e8a4d83f`
- Edited: commit `083c4e954aed` (PR #32, merged 2026-09-07 14:09 UTC /
  10:09 ET). SHA-256
  `7e3d92dea958432fb6e8ce8972f6afed71aa438ab62ddadd3dedfc1853ed3b5f`
- What changed: `"commit": "unknown"` became
  `"commit": "65446fce1ae618e47d4cf95da82468da4743c20c"`.
- Reason as recorded (commit message): `_git_commit()` recorded "unknown" at
  issuance; at `generated_at` 2026-09-01T05:10:08Z the tip of `main` was
  `65446fce` (Merge PR #13). Note: the backfilled value is a reconstruction
  from repository history, not a value recorded by the run itself.

### E-2026-09-07-2 · WARD-DEVNET-20260902-001 · coverage ratio display string

- File: `docs/security/evidence/devnet/2026-09-02/ward-evidence-pre-resolution-2026-09-02.json`
- Original (published 2026-09-02, commit `7968225e`): SHA-256
  `018bbf33b67f70e4830121cea0fdbe6dbe559d5a0667e1bfbafa2895bf2eda28`
- Edited: commit `8e31c81a68b2` (PR #32, merged 2026-09-07 14:09 UTC /
  10:09 ET). SHA-256
  `8ebfffac2a50ecd0a55a9240cb9a45b1c0d23ff184402894a0c7aa77e4ecb390`
- What changed: display string `"coverage_ratio": "99x"` became `"98.99x"`
  (99000001 / 1000001 = 98.9999…; the same PR changed the display rule to
  floor to two decimals). The underlying drop amounts are unchanged. The same
  commit changed the matching strings in `certificate-index.json` and the
  09-02 README.
- Reason as recorded (commit message): whole-number rounding displayed 98.9999…
  as 99x and could turn a just-above-threshold pool into a non-compliant whole
  number.

## Where each version is published (after this change)

| Evidence file | Canonical path holds | Other version published at |
|---|---|---|
| Aug 24 | `7793a1d7…` (edited 2026-08-27) | `…-2026-08-24.v1-original.json` (`962dcaac…`) |
| 09-01 | `7e3d92de…` (edited 2026-09-07) | `…-2026-09-01.v1-original.json` (`c0ab6447…`) |
| 09-02 | `8ebfffac…` (edited 2026-09-07) | `…-2026-09-02.v1-original.json` (`018bbf33…`) |

Both repositories carry the same bytes at the same paths.

## E-2026-09-29-1 · remediation edits to the certificate index and two historical pilot documents

Appended 2026-09-29. No earlier entry in this file was edited. The Ward-Protocol-OS repository has no
external commitment for its evidence history (the private WARD repository's guard is not present here), so this
entry is a plain append-only record, **not** a tamper-evident one: it can be edited by anyone who can edit this
repository. Treat the hashes below as a statement of what was changed, not as proof.

The remediation in this change set changed these files after `main` `5ca3838`:

| File | SHA-256 at `5ca3838` | SHA-256 after remediation |
|---|---|---|
| `docs/security/evidence/certificate-index.json` | `d27beef65400b39b07eee31f4307c0255c029cd2e2522ea5561f58baaa9145c6` | `b3e4478b24da95c0de3a9d6bdf292013c4a6d7067b9e763e1440a1a36f121b3e` |
| `docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md` | `d95bbc4ba6794478b4bc7da876551060d9f62330996ad257b30b79af49a5ead0` | `bb484986b2712604af6db45c7fdc4c7f4aef1b30c6b7bc288ff97f8b1d290f2a` |
| `docs/pilots/xrpl-devnet-independent-verification-2026-09-01.md` | `905680d8c2b34a9f0d3bba04d79c20a0c3d0fcd30c8455cec018fe17ed5af922` | `7c2edcbd7b5790186c5212b054ba4cdae8a62b9a3d67232e4c1be2583bb68597` |

What changed: in `certificate-index.json`, `WARD-DEVNET-20260901-001` now has `result.independently_verified` =
`false` (it was `true`), with a new `independently_verified_note`, and limitation wording that calls the
recomputation operator-run rather than independent; the two pilot documents now label Ward-run re-derivations as
operator-run and record that `independently_verified` is false for the 2026-09-01 run. No transaction hash, ledger
index, archive hash, decision or `ward_signed` value changed. The raw-read evidence files are untouched.

Limits: these are wording and flag corrections, not third-party verification. The toolkit document also had one
sentence about a partner verification boundary reworded on 2026-09-29 (a document outside the evidence set).


## E-2026-09-29-2 · supplement to E-2026-09-29-1: hashes that entry omitted

Appended 2026-09-29 after an independent review noted the omission. E-2026-09-29-1 above listed three files; the OS remediation
diff over `5ca3838` also modified three devnet READMEs and the 2026-08-24 evidence JSON (the already-disclosed
label correction, entry E-2026-08-27-1), and ADDED five files under `docs/security/evidence/` (the CHANGELOG, the
versions file, three `v1-original.json` copies and `operator-verification.json`). Nothing above was edited. Same limit as before: the Ward-Protocol-OS repository has no
external commitment for its evidence history, so this is a plain append, not a tamper-evident record.

| Change | File | SHA-256 at `5ca3838` | SHA-256 after remediation (before this entry) |
|---|---|---|---|
| modified | `docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md` | `d95bbc4ba6794478b4bc7da876551060d9f62330996ad257b30b79af49a5ead0` | `bb484986b2712604af6db45c7fdc4c7f4aef1b30c6b7bc288ff97f8b1d290f2a` |
| modified | `docs/pilots/xrpl-devnet-independent-verification-2026-09-01.md` | `905680d8c2b34a9f0d3bba04d79c20a0c3d0fcd30c8455cec018fe17ed5af922` | `7c2edcbd7b5790186c5212b054ba4cdae8a62b9a3d67232e4c1be2583bb68597` |
| modified | `docs/security/evidence/certificate-index.json` | `d27beef65400b39b07eee31f4307c0255c029cd2e2522ea5561f58baaa9145c6` | `b3e4478b24da95c0de3a9d6bdf292013c4a6d7067b9e763e1440a1a36f121b3e` |
| modified | `docs/security/evidence/devnet/2026-08-24/README.md` | `e8d3f3e7f586263aaaf772bd3e92c323694f0b8783790fcb4716e57ab093ff2e` | `a5219fedb1fb3bfc97409bdcebd8187252f31eda7db7329204cd4367070c39be` |
| modified | `docs/security/evidence/devnet/2026-08-24/ward-evidence-pre-resolution-2026-08-24.json` | `962dcaac0c71b9ecebaa449fdcf596ee56f522119b751520522c985b6e35e7c6` | `7793a1d7ec2a2579c99ccbde2c13ec2770be52c000858ddeed1156d37bcbe094` |
| added | `docs/security/evidence/devnet/2026-08-24/ward-evidence-pre-resolution-2026-08-24.v1-original.json` | — (new file) | `962dcaac0c71b9ecebaa449fdcf596ee56f522119b751520522c985b6e35e7c6` |
| modified | `docs/security/evidence/devnet/2026-09-01/README.md` | `4bdeb083b4fb3cfc5b3ea84d1d5cce2a9d3cc94249eb76b2ca3d38ecd4f0faaa` | `21dafb40f2e2df71ca1c4c05c5775d1403af050ea41b241a677c3731f4594c6b` |
| added | `docs/security/evidence/devnet/2026-09-01/ward-evidence-pre-resolution-2026-09-01.operator-verification.json` | — (new file) | `56090c635d3f3d2caea854118dfd6c8e31d93b298a51444d83d325a0e12d5e1c` |
| added | `docs/security/evidence/devnet/2026-09-01/ward-evidence-pre-resolution-2026-09-01.v1-original.json` | — (new file) | `c0ab64470b38a9fa3f7a08435c9d9ceb8f331cfcf014a2aa59ae4f34e8a4d83f` |
| modified | `docs/security/evidence/devnet/2026-09-02/README.md` | `1503f844c70790021c47ca0137462e11ba78ad1ca76b32a1e3d0dd0773256285` | `a7055ff214fcd6e93bbb80413e7df776502594e4ee8563b21434b489193d101c` |
| added | `docs/security/evidence/devnet/2026-09-02/ward-evidence-pre-resolution-2026-09-02.v1-original.json` | — (new file) | `018bbf33b67f70e4830121cea0fdbe6dbe559d5a0667e1bfbafa2895bf2eda28` |
| added | `docs/security/evidence/evidence-versions.json` | — (new file) | `719def1fae94242b3841cd071d9dceda1035a6de0ebf246d847a12f6fd782765` |

The CHANGELOG's own hash is deliberately not listed (a file cannot hash itself). The `v1-original.json` files are
the three devnet evidence files as first published (so the pre-correction bytes stay downloadable). The
three devnet README edits are wording alignments (operator-run label, pointer to the original files). No ledger or
raw-read evidence file was modified.

## E-2026-09-29-3 · OS pilot document wording aligned with the WARD copy

Appended 2026-09-29 (no earlier entry above was edited).

The OS copy of `docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md` still said "This run is the first design-partner proof of that
review surface", which implies a customer or partner relationship. The July 2026 run was a review by Kairo Vault Technologies GK, not a customer
pilot. The sentence is now the same as the WARD copy: "This run was the first unaffiliated review of that surface. It was not a customer pilot and
not proof of a customer deployment." The earlier forbidden-claims exemption for that line is removed (the text is fixed, not exempted). The OS repository has
no tamper-evident chain; this is a plain append. Only that one sentence changed.

| Change | File | SHA-256 before (after entry E-2026-09-29-2) | SHA-256 after |
|---|---|---|---|
| modified | `docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md` | `bb484986b2712604af6db45c7fdc4c7f4aef1b30c6b7bc288ff97f8b1d290f2a` | `a3ea1a85e9272da19d9e9328dc27195fe2619585b8d3d84541f2540551565038` |

Also in this change (not evidence files): the watchdog now enforces the exact declared result for the legacy certificate
(`workers/certificate-heartbeat-core.mjs`), and the test-only legacy-evaluator seam is honoured only for a `Symbol.for(...)` token.
