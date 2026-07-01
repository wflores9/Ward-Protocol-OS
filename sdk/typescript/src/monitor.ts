import { VaultHealth, WebhookPayload, WebhookEvent } from './types'
import { WardError, validateXrplAddress } from './primitives'
import {
  HEALTH_RATIO_THRESHOLD,
  DEFAULT_CONFIRMATION_CLOSES,
  NETWORK_CONFIG,
} from './constants'

export type DefaultCallback = (event: VaultHealth) => void | Promise<void>
export type WebhookCallback = (payload: WebhookPayload) => void | Promise<void>

/** F·04 — VaultMonitor: WebSocket-based default detection */
export class VaultMonitor {
  private readonly wsUrl: string
  private readonly vaultAddresses: Set<string> = new Set()
  private readonly defaultCallbacks: DefaultCallback[] = []
  private readonly webhookCallbacks: WebhookCallback[] = []
  private confirmCounts: Map<string, number> = new Map()
  private running = false

  constructor(network: keyof typeof NETWORK_CONFIG = 'altnet') {
    this.wsUrl = NETWORK_CONFIG[network].ws
  }

  addVault(address: string): this {
    validateXrplAddress(address)
    this.vaultAddresses.add(address)
    return this
  }

  onDefault(cb: DefaultCallback): this {
    this.defaultCallbacks.push(cb)
    return this
  }

  onWebhook(cb: WebhookCallback): this {
    this.webhookCallbacks.push(cb)
    return this
  }

  /** Determine webhook event from health ratio threshold crossing */
  static determineEvent(
    healthRatio: number,
    previousRatio: number | null,
  ): WebhookEvent | null {
    if (previousRatio === null) return null

    if (healthRatio < 1.5 && previousRatio >= 1.5) return 'vault.health.critical'
    if (healthRatio < 1.75 && previousRatio >= 1.75) return 'vault.health.elevated'
    if (healthRatio < 2.0 && previousRatio >= 2.0) return 'vault.health.warning'
    if (healthRatio >= 1.5 && previousRatio < 1.5) return 'vault.default.resolved'

    return null
  }

  stop(): void {
    this.running = false
  }

  get isRunning(): boolean {
    return this.running
  }

  get watchedVaults(): string[] {
    return Array.from(this.vaultAddresses)
  }

  /** Exposed for testing — fire default callbacks */
  async _fireDefaultCallbacks(event: VaultHealth): Promise<void> {
    for (const cb of this.defaultCallbacks) {
      await cb(event)
    }
  }

  /** Exposed for testing — fire webhook callbacks */
  async _fireWebhookCallbacks(payload: WebhookPayload): Promise<void> {
    for (const cb of this.webhookCallbacks) {
      await cb(payload)
    }
  }
}

// Re-export constants for callers who import from monitor
export { HEALTH_RATIO_THRESHOLD, DEFAULT_CONFIRMATION_CLOSES }
