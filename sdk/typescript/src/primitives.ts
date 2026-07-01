import { WARD_POLICY_TAXON, WARD_KYC_TAXON } from './constants'

export class WardError extends Error {
  constructor(
    message: string,
    public readonly code?: string,
  ) {
    super(message)
    this.name = 'WardError'
  }
}

export function validateXrplAddress(address: string): void {
  if (!address || !address.startsWith('r') || address.length < 25 || address.length > 35) {
    throw new WardError(`Invalid XRPL address: ${address}`)
  }
}

export function validateDrops(drops: number): void {
  if (!Number.isInteger(drops) || drops < 0 || drops > 100_000_000_000_000_000) {
    throw new WardError(`Invalid drops value: ${drops}. Must be non-negative integer.`)
  }
}

export function validateLoanId(loanId: string): void {
  if (!loanId || loanId.length !== 64 || !/^[0-9a-fA-F]+$/.test(loanId)) {
    throw new WardError(`Invalid loan_id format: ${loanId}. Must be 64 hex chars.`)
  }
}

export function validateNftTokenId(tokenId: string): void {
  if (!tokenId || tokenId.length !== 64 || !/^[0-9a-fA-F]+$/.test(tokenId)) {
    throw new WardError(`Invalid NFT token ID: ${tokenId}. Must be 64 hex chars.`)
  }
}

export function assertWardSignedFalse(response: { ward_signed: boolean }): void {
  if (response.ward_signed !== false) {
    throw new WardError('Invariant violated: ward_signed must always be false')
  }
}

// suppress unused-import warning — these are re-exported for SDK consumers
void WARD_POLICY_TAXON
void WARD_KYC_TAXON
