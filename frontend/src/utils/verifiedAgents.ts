import { api, ApiError } from './api'
import type { RegisteredAgent } from '../types'

let cachedAgents: RegisteredAgent[] | null = null
let lastFetchTime: number = 0
const CACHE_DURATION = 5 * 60 * 1000 // 5 minutes

/**
 * Fetch the list of verified agents from the /agents/registered endpoint.
 * Results are cached to avoid excessive API calls.
 */
export async function getVerifiedAgents(): Promise<RegisteredAgent[]> {
  const now = Date.now()

  // Return cached results if still valid
  if (cachedAgents && now - lastFetchTime < CACHE_DURATION) {
    return cachedAgents
  }

  try {
    const agents = await api.verifiedAgents()
    cachedAgents = agents
    lastFetchTime = now
    return agents
  } catch (error) {
    if (error instanceof ApiError) {
      console.error('Failed to fetch verified agents:', error.userMessage)
    } else {
      console.error('Failed to fetch verified agents:', error)
    }
    // Return empty array on error, but don't cache the error
    return []
  }
}

/**
 * Check if a wallet address is verified (registered in AgentRegistry).
 */
export async function isAgentVerified(walletAddress: string): Promise<boolean> {
  const agents = await getVerifiedAgents()
  return agents.some((agent) => agent.wallet === walletAddress)
}

/**
 * Get the verified agent record for a wallet, if it exists.
 */
export async function getVerifiedAgentRecord(walletAddress: string): Promise<RegisteredAgent | null> {
  const agents = await getVerifiedAgents()
  return agents.find((agent) => agent.wallet === walletAddress) || null
}

/**
 * Invalidate the cache to force a fresh fetch on next call.
 */
export function invalidateVerifiedAgentsCache(): void {
  cachedAgents = null
  lastFetchTime = 0
}
