# Ward Protocol TypeScript SDK

> `ward_signed = False — always.`
> Ward constructs unsigned transactions. Institutions sign. XRPL settles.

[![npm](https://img.shields.io/npm/v/@wardprotocol/sdk)](https://www.npmjs.com/package/@wardprotocol/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../../LICENSE)

## Install

```bash
npm install @wardprotocol/sdk
```

## Quick Start

```typescript
import { WardClient, ClaimValidator } from '@wardprotocol/sdk';

const validator = new ClaimValidator({
  url: 'https://s.altnet.rippletest.net:51234/'
});

const result = await validator.validateClaim({
  claimantAddress: 'rClaimant...',
  nftTokenId: 'AAA...',
  defaultedVault: 'rVault...',
  poolAddress: 'rPool...'
});

console.log(result.approved);      // true
console.log(result.stepsPassed);   // 9
console.log(result.wardSigned);    // false — always
```

## Stats

| Metric | Value |
|--------|-------|
| Version | 0.2.9 |
| Tests | 53/53 passing |
| Open CVEs | 0 |
| ward_signed | false — always |

## Links

- [wardprotocol.org](https://wardprotocol.org)
- [Assurance](https://wardprotocol.org/assurance)
- [Docs](https://wardprotocol.org/build)
- [PyPI](https://pypi.org/project/ward-protocol/)
- [GitHub](https://github.com/wflores9/ward-protocol)

## License

MIT — SDK is free forever.
Mainnet API requires commercial license.
Contact: team@wardprotocol.org

ward_signed = False — always.
