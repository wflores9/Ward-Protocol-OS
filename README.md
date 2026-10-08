# Ward Protocol

**Deterministic evidence-to-decision infrastructure for institutional workflows.**

Ward evaluates authoritative evidence against fixed, versioned policies and produces **unsigned, replayable resolution receipts**. Institutions retain responsibility for policy adoption, review, approval, signing, custody, and execution.

> **Ward evaluates. The institution signs. The ledger settles.**  
> Invariant: `ward_signed = false`.

## What Ward does

A loan default, collateral restriction, or conditional release can require evidence from more than one system. Ward provides a reproducible decision record: **which evidence was used, which rules applied, what result followed, and why**.

The public repository includes a deterministic resolution engine, evidence snapshot and receipt schemas, synthetic workflow fixtures, and independent verification utilities. These are **technical artifacts**, not evidence of production adoption or a completed institutional pilot.

Ward **does not** hold customer assets or signing keys, sign or submit transactions, execute settlement, replace institutional approval, or certify that an external-world statement is true merely because its signature verifies.

## Explore the public technical work

| Start here | What it shows |
| --- | --- |
| [Integration and evidence review](docs/integration/README.md) | Current customer-facing workflow proposals and evidence verification boundaries |
| [Ward × Molpha conditional escrow workflow](docs/integration/ward-molpha-conditional-escrow-customer-workflow.md) | **Proposed** end-to-end institutional example; not a completed integration |
| [Resolution receipt schema](schemas/ward-resolution-receipt-v1.schema.json) | Machine-readable receipt structure |
| [Evidence snapshot schema](schemas/ward-evidence-snapshot-v1.schema.json) | Canonical evidence representation |
| [Conditional release fixture](examples/conditional-release-input.json) | Synthetic input for an illustrative workflow |
| [Independent receipt verifier](scripts/verify_resolution_receipt.py) | Tooling for checking receipt integrity |
| [Security and verification](docs/security/independent-verification-toolkit.md) | Review and verification approach |
| [Security reporting](SECURITY.md) | Responsible disclosure contact |

## How the boundary works

```text
Authoritative source / signed external evidence
             |
       Evidence snapshot
             |
    Fixed, versioned policy
             |
  Unsigned resolution receipt
             |
 Institutional review / approval
             |
 Institution-controlled signing
             |
   Supported execution rail
             |
    Outcome and audit/replay
```

Evidence verification and policy evaluation are distinct. A valid signature can support integrity and provenance; it does not automatically establish factual truth, contractual eligibility, or institutional authorization.

## Current status and limitations

- The repository contains open-source core components, SDKs, test fixtures, Devnet/Altnet research, and exploratory integration documentation.
- XLS-65/66 lending default workflows are subject to the relevant XRPL feature and network availability, implementation readiness, and institutional controls. **Do not infer XRPL Mainnet production readiness from Devnet fixtures or test results.**
- Multi-chain documents in this repository include historical or exploratory work; their presence does not establish production support on those networks.
- The Ward × Molpha workflow is a **proposal for technical review**. No Molpha integration, commercial arrangement, institutional customer, or completed pilot is claimed.
- Historical audits and test counts are point-in-time artifacts, not a current independent security certification.

## Local development

```bash
git clone https://github.com/wflores9/Ward-Protocol-OS.git
cd Ward-Protocol-OS
python -m pip install -e ".[dev]"
pytest tests/ -q
```

These commands are for local review. Any network-dependent workflow requires its own explicit environment configuration and validation.

## Security and contributions

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability, and [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. **Never put private keys, seeds, API tokens, customer data, or confidential agreements in issues, commits, or evidence fixtures.**

## License

See [COMMERCIAL.md](COMMERCIAL.md) for licensing and commercial inquiries. **A root LICENSE file is currently absent; do not assume a license grant from README badges or package metadata.** The presence of code or examples does not imply an available production service-level agreement.

[wardprotocol.org](https://www.wardprotocol.org)
