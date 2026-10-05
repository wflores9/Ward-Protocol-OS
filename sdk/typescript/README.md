# Ward Protocol TypeScript SDK

`ward_signed = False` — always.

Ward evaluates agreed policy against authoritative evidence and produces
replayable, unsigned resolution records. Institutions sign. The chain settles.
Ward never custodies assets, never signs, and never submits transactions.

## Status

- **Networks:** XRPL Altnet (test network) through the hosted API at
  `https://api.wardprotocol.org`. XRPL Mainnet is not supported: XLS-65 and
  XLS-66 are not enabled on Mainnet, and there is no mainnet API.
- **Production use:** not approved. This SDK is for evaluation and
  non-production pilots.
- **What this package covers:** typed wrappers for the hosted API (vault
  registration, XLS-66 claim validation, unsigned transaction preparation) and
  offline input checks. It does **not** include the Evidence Snapshot /
  RuleBundle / Resolution Receipt engine. That engine ships in the Python
  package `ward-protocol` (`ward.resolution`, `ward.workflows`).

## Install

```bash
npm install ward-protocol-sdk
```

## Offline checks (no network, no key)

```typescript
import {
  WardClient,
  validateXrplAddress,
  assertWardSignedFalse,
} from 'ward-protocol-sdk';

// The constructor makes no network call.
const client = new WardClient({ network: 'altnet', institution_key: 'unused-offline' });

validateXrplAddress('rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh'); // throws WardError if invalid

// Every Ward response must carry ward_signed: false. This throws otherwise.
assertWardSignedFalse({ ward_signed: false });
```

## Hosted API calls (XRPL Altnet)

API calls send an `X-Institution-Key` header. Key issuance is not
self-serve and is not yet documented; contact team@wardprotocol.org for a
scoped evaluation key. Addresses must be funded XRPL Altnet accounts.

```typescript
import { WardClient } from 'ward-protocol-sdk';

const client = new WardClient({
  network: 'altnet',
  api_url: 'https://api.wardprotocol.org',
  institution_key: process.env.WARD_INSTITUTION_KEY!,
});

// Nine on-ledger checks against XRPL Altnet state. Returns a record with
// ward_signed: false; the SDK throws if it is not false.
const result = await client.validateClaim(
  process.env.CLAIMANT_ADDRESS!,
  process.env.POLICY_NFT_ID!,
  process.env.DEFAULTED_VAULT!,
  process.env.LOAN_ID!,
  process.env.POOL_ADDRESS!,
);
console.log(result);
```

Methods that prepare transactions (`preparePolicyPremium`,
`finalizePolicyMint`, `createClaimEscrow`) return **unsigned** XRPL
transactions for your institution to review, sign, and submit with its own
keys. Ward never accepts a seed, private key, wallet credential, or signed
transaction.

## Vocabulary note

Some method and field names (`premium`, `policy`, `coverage`, `claim`) come
from the XRPL Devnet test fixtures used to exercise XLS-65/66 lending
lifecycles. They are data labels in those fixtures. Ward is not an insurance
product, does not underwrite or pay claims, and holds no funds.

## What Ward does

1. Pin the facts — read authoritative state from the agreed source.
2. Apply fixed rules — evaluate the workflow against agreed policy.
3. Produce the record — return a replayable evidence receipt and an unsigned
   resolution path.
4. Keep authority — the institution reviews, signs, and settles.

## Links

- Site: https://wardprotocol.org
- Evidence register: https://wardprotocol.org/evidence
- Assurance: https://wardprotocol.org/assurance
- Python package: https://pypi.org/project/ward-protocol/
- Public source: https://github.com/wflores9/Ward-Protocol-OS

## License

MIT. Commercial terms cover scoped, non-production design-partner pilots
only. There is no mainnet API, no certification program, and no SLA. See
https://github.com/wflores9/Ward-Protocol-OS/blob/main/COMMERCIAL.md or
contact team@wardprotocol.org.

`ward_signed = False` — always.
