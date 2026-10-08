# Public Repository Audit — 2026-10-08

> **Status: IN PROGRESS.** This is a risk register and first-pass source review, **not** a completed security certification, clean secret-scan attestation, or production readiness endorsement.

## Scope inspected

- Recursive repository inventory: 249 tree entries on `main` (inventory only, not a byte-by-byte audit).
- Selected source/configuration and public-facing documentation: root README, commercial and infrastructure pages, packaging metadata, security notes, claims audit, integration index, CI and configuration.
- Draft documentation updates in [Molpha review PR #12](https://github.com/wflores9/Ward-Protocol-OS/pull/12) and this cleanup PR.

## Findings

| Priority | Finding | Evidence | Required disposition |
| --- | --- | --- | --- |
| RESOLVED IN PR | Root `LICENSE` absent while package manifests declared MIT. | Root tree and manifests | Published MIT license and restored matching package metadata. Confirm ownership/contributor rights before external relicensing. |
| HIGH | Historical `docs/infrastructure.md` asserted specific production hosting, API, DNS and test counts. | Former version; corrected in this PR | Validate current public services independently before claiming they exist. |
| HIGH | Former `COMMERCIAL.md` offered Mainnet API with SLA and certification without evidence of current contractual availability. | Former version; corrected in this PR | Confirm offerings before public promises. |
| MEDIUM | `docs/claims-audit.md` is dated June 2026 and includes claims about site files absent from the current repository tree, plus test counts and CI assertions not revalidated here. | Claims audit vs current tree | Label historical; do not promote to current certification. |
| MEDIUM | `docs/security/security_notes.md` (March 2026) includes descriptions of historical signing/settlement flows and known TOCTOU issues; not all text reflects the current Ward boundary. | Security notes | Add historical banner; review line-by-line against current code before citing as active design. |
| MEDIUM | `sdk/python/setup.py` advertises an older version and XRPL AMM positioning, uses stale repository URL and a brittle README-open expression. | Python SDK setup | Harmonize package metadata after verifying packaging and release process. |
| MEDIUM | `pyproject.toml` points its Documentation URL to a hosted API endpoint and Repository URL to a website, not the GitHub source. | Package metadata | Correct source URL and confirm docs endpoint before release. |
| MEDIUM | Public docs contain exploratory chain adapters, grant history and pilot titles that may be read as completed adoption. | Inventory and sampled files | Classify active/proposed/historical and review externally attributable claims. |
| LOW | `.gitignore` covers `.env` and seed files but is not proof against committed or historical secrets. | Gitignore | Perform full working-tree **and history** scanning. |

## Confirmed certificate reproducibility failure (HIGH)

The [October 5, 2026 weekly workflow](https://github.com/wflores9/Ward-Protocol-OS/actions/runs/37318315471) failed because all three pinned XRPL Devnet ledger reads returned `lgrNotFound`: `KV-IV-2026-0712-001` (ledger 3576434), `WARD-DEVNET-20260901-001` (4949701), and `WARD-DEVNET-20260902-001` (4970389). The status output reported **three unreproducible certificates, zero check errors**. This is an **availability/reproducibility limitation of the historical public RPC evidence**, not evidence of a forged certificate or a secret leak. Preserve original evidence and failure status; do not disable the failing check or claim independent live re-verification.

Remediation requires independently archived raw ledger proof or a durable, trustworthy historical ledger source, then a new verification run. Do not rewrite old receipt hashes or silently replace historical ledger locators.

## Credential exposure status

**Not cleared.** Filename inspection did not reveal obvious `.env`, `.pem`, or private-key filenames in the current tree, but this does **not** establish that file contents, embedded images, archives, previous commits, or GitHub Actions artifacts are clean. An attempted repository-wide content scan did not finish. Do not assert “no leaks” until those scans complete.

## Required before final sign-off

1. Scan the complete Git object history and all reachable branches/tags with a secret scanner (for example Gitleaks), then manually triage all hits **without publishing credential values**.
2. Scan current tree including JSON evidence, image metadata, workflow definitions, and third-party links for PII and internal operational details.
3. Check dependency advisories for Python and npm lockfiles; run the test suites and signing-boundary checks.
4. Validate all public Markdown links and external URLs; review every documentation claim of pilot, partner, customer, audit, mainnet, deployment and certification.
5. MIT license selected and added; confirm contributor rights, package publishing posture, and security contact/response commitments.
6. Review and approve both stacked PRs; merge the Molpha branch first and then the audit branch if appropriate.

**Publication note:** Editing or deleting a file does not erase previous public Git history. If credentials are found, revoke/rotate immediately and coordinate history remediation separately.


## Automated verification — October 8, 2026

[GitHub Actions run 37827708066](https://github.com/wflores9/Ward-Protocol-OS/actions/runs/37827708066) produced:

- **Passed:** Gitleaks Git-history secret scan, signing-boundary script, Python dependency audit. This does not guarantee the absence of every secret or vulnerability.
- **Failed:** Python test collection. One invalid multi-exception handler in `scripts/verify_devnet_evidence_independent.py` and undeclared `hypothesis` were corrected in this branch; the missing `ward.adapters` package remains a real collection blocker. Do not invent the historical Wormhole adapter merely to satisfy tests; determine whether to restore a supported implementation or explicitly archive its obsolete tests.
- **Failed:** npm dependency audit. Four high-severity findings in the current Wrangler / Miniflare dependency chain (including `sharp` and `undici`). The audit recommended a newer Wrangler outside the declared range; update and regenerate the lockfile with compatibility testing, not by ignoring the audit.
- **Pending:** a fresh verification run of the corrected branch; historical Devnet certificate live verification remains unreproducible.

**Release gate:** do not describe the repository as clean or merge the stacked PRs until test collection and dependency vulnerabilities are addressed and a green run is recorded. Keep historical certificate limitations visible.
