import { VaultMonitor } from '../src/monitor'
import { WardError } from '../src/primitives'

const VALID_ADDRESS = 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh'
const VALID_ADDRESS2 = 'rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe'

describe('VaultMonitor', () => {
  describe('addVault', () => {
    it('accepts valid XRPL address', () => {
      const m = new VaultMonitor('altnet')
      expect(() => m.addVault(VALID_ADDRESS)).not.toThrow()
      expect(m.watchedVaults).toContain(VALID_ADDRESS)
    })

    it('rejects invalid XRPL address', () => {
      const m = new VaultMonitor('altnet')
      expect(() => m.addVault('bad-address')).toThrow(WardError)
    })

    it('supports chaining', () => {
      const m = new VaultMonitor('altnet')
      m.addVault(VALID_ADDRESS).addVault(VALID_ADDRESS2)
      expect(m.watchedVaults).toHaveLength(2)
    })
  })

  describe('determineEvent', () => {
    it('returns health.warning when crossing below 2.0', () => {
      expect(VaultMonitor.determineEvent(1.9, 2.5)).toBe('vault.health.warning')
    })

    it('returns health.elevated when crossing below 1.75', () => {
      expect(VaultMonitor.determineEvent(1.7, 1.8)).toBe('vault.health.elevated')
    })

    it('returns health.critical when crossing below 1.5', () => {
      expect(VaultMonitor.determineEvent(1.4, 1.6)).toBe('vault.health.critical')
    })

    it('returns default.resolved on recovery above 1.5', () => {
      expect(VaultMonitor.determineEvent(1.6, 1.4)).toBe('vault.default.resolved')
    })

    it('returns null when no threshold crossed', () => {
      expect(VaultMonitor.determineEvent(2.2, 2.5)).toBeNull()
    })

    it('returns null when previous is null (first reading)', () => {
      expect(VaultMonitor.determineEvent(1.4, null)).toBeNull()
    })
  })

  describe('callbacks', () => {
    it('fires default callbacks', async () => {
      const m = new VaultMonitor('altnet')
      const received: unknown[] = []
      m.onDefault((evt) => { received.push(evt) })

      const mockEvent = {
        vault_address: VALID_ADDRESS,
        health_ratio: 1.2,
        status: 'critical' as const,
        ledger_index: 12345,
        ward_signed: false as const,
      }
      await m._fireDefaultCallbacks(mockEvent)
      expect(received).toHaveLength(1)
      expect(received[0]).toEqual(mockEvent)
    })

    it('fires webhook callbacks', async () => {
      const m = new VaultMonitor('altnet')
      const received: unknown[] = []
      m.onWebhook((payload) => { received.push(payload) })

      const mockPayload = {
        event: 'vault.health.critical' as const,
        vault_address: VALID_ADDRESS,
        health_ratio: 1.2,
        ledger_index: 12345,
        timestamp: Date.now(),
        ward_signed: false as const,
      }
      await m._fireWebhookCallbacks(mockPayload)
      expect(received).toHaveLength(1)
    })
  })
})
