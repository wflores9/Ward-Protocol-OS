import { ClaimValidationResult } from './types'
import { WardError, validateXrplAddress, validateNftTokenId, validateLoanId, assertWardSignedFalse } from './primitives'

export class ClaimValidator {
  constructor(
    private readonly apiUrl: string,
    private readonly institutionKey: string,
  ) {}

  /** F·05 — Run 9-step claim validation */
  async validateClaim(
    vaultAddress: string,
    nftTokenId: string,
    loanId: string,
    claimantAddress: string,
  ): Promise<ClaimValidationResult> {
    validateXrplAddress(vaultAddress)
    validateXrplAddress(claimantAddress)
    validateNftTokenId(nftTokenId)
    validateLoanId(loanId)

    const res = await fetch(`${this.apiUrl}/claims/validate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Institution-Key': this.institutionKey,
      },
      body: JSON.stringify({
        vault_address: vaultAddress,
        nft_token_id: nftTokenId,
        loan_id: loanId,
        claimant_address: claimantAddress,
      }),
    })

    if (!res.ok) {
      throw new WardError(`Claim validation API error: ${res.status}`)
    }

    const result = await res.json() as ClaimValidationResult
    assertWardSignedFalse(result)

    if (result.checks_total !== 9) {
      throw new WardError(`Expected 9 validation checks, got ${result.checks_total}`)
    }

    return result
  }
}
