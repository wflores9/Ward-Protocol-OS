import { EscrowSettlement } from './types'
import { WardError, validateXrplAddress, validateNftTokenId, assertWardSignedFalse } from './primitives'

export class EscrowSettlementClient {
  constructor(
    private readonly apiUrl: string,
    private readonly institutionKey: string,
  ) {}

  /** F·06 — Get unsigned EscrowCreate for a valid claim */
  async createEscrow(
    vaultAddress: string,
    nftTokenId: string,
    claimantAddress: string,
    conditionHex: string,
  ): Promise<EscrowSettlement> {
    validateXrplAddress(vaultAddress)
    validateXrplAddress(claimantAddress)
    validateNftTokenId(nftTokenId)

    if (!conditionHex || !/^[0-9a-fA-F]+$/.test(conditionHex)) {
      throw new WardError('Invalid condition_hex — must be hex string')
    }

    const res = await fetch(`${this.apiUrl}/settlement/escrow`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Institution-Key': this.institutionKey,
      },
      body: JSON.stringify({
        vault_address: vaultAddress,
        nft_token_id: nftTokenId,
        claimant_address: claimantAddress,
        condition_hex: conditionHex,
      }),
    })

    if (!res.ok) {
      throw new WardError(`Settlement API error: ${res.status}`)
    }

    const result = await res.json() as EscrowSettlement
    assertWardSignedFalse(result)

    if (!result.institution_signs) {
      throw new WardError('Invariant violated: institution_signs must be true')
    }

    return result
  }
}
