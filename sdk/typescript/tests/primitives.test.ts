import {
  WardError,
  validateXrplAddress,
  validateDrops,
  validateLoanId,
  validateNftTokenId,
  assertWardSignedFalse,
} from '../src/primitives'

describe('Ward Primitives', () => {
  describe('validateXrplAddress', () => {
    it('accepts valid XRPL address', () => {
      expect(() => validateXrplAddress('rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh')).not.toThrow()
    })
    it('rejects address not starting with r', () => {
      expect(() => validateXrplAddress('xInvalidAddress')).toThrow(WardError)
    })
    it('rejects empty string', () => {
      expect(() => validateXrplAddress('')).toThrow(WardError)
    })
  })

  describe('validateDrops', () => {
    it('accepts valid drops', () => {
      expect(() => validateDrops(1_000_000)).not.toThrow()
    })
    it('rejects float', () => {
      expect(() => validateDrops(1.5)).toThrow(WardError)
    })
    it('rejects negative', () => {
      expect(() => validateDrops(-1)).toThrow(WardError)
    })
  })

  describe('validateLoanId', () => {
    it('accepts 64-char hex', () => {
      expect(() => validateLoanId('a'.repeat(64))).not.toThrow()
    })
    it('rejects wrong length', () => {
      expect(() => validateLoanId('abc')).toThrow(WardError)
    })
    it('rejects non-hex', () => {
      expect(() => validateLoanId('z'.repeat(64))).toThrow(WardError)
    })
  })

  describe('validateNftTokenId', () => {
    it('accepts 64-char hex', () => {
      expect(() => validateNftTokenId('f'.repeat(64))).not.toThrow()
    })
    it('rejects wrong length', () => {
      expect(() => validateNftTokenId('abc')).toThrow(WardError)
    })
  })

  describe('assertWardSignedFalse', () => {
    it('passes when ward_signed is false', () => {
      expect(() => assertWardSignedFalse({ ward_signed: false })).not.toThrow()
    })
    it('throws when ward_signed is true', () => {
      expect(() => assertWardSignedFalse({ ward_signed: true })).toThrow(WardError)
    })
  })
})
