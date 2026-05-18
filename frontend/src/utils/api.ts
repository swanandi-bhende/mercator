import axios from 'axios'
import type {
  ListResponse,
  DemoPurchaseRequest,
  DemoPurchaseResponse,
  OnboardRequest,
  OnboardResponse,
  LoginRequest,
  LoginResponse,
  WalletBalanceResponse,
  WalletCustodialResponse,
  WalletExportResponse,
  HealthResponse,
  DiscoverResponse,
  LedgerResponse,
  OpsOverviewResponse,
  OpsAccessCheckResponse,
  OpsSyntheticHistoryResponse,
  OpsSyntheticRunResponse,
  OpsIpfsHealthResponse,
  OpsIpfsUploadResponse,
  OpsAlgorandStatusResponse,
  OpsPingResponse,
  OpsDiagnosticsResponse,
  OpsCacheStatsResponse,
  AdminGenerateApiKeyResponse,
  AdminCuratorTriggerResponse,
  ListingsFeedResponse,
  TracesLatestResponse,
  TraceSessionResponse,
  SellerReputationResponse,
  SellerPurchaseHistoryResponse,
  SubscriptionReleaseResponse,
  SubscriptionStatusResponse,
  FeeConfigResponse,
  AtomicSubscribeResponse,
  RegisteredAgentsResponse,
} from '../types'
import type { RegisteredAgent } from '../types'

type SubscribeResponse = {
  success: boolean
  tx_id: string
  subscription_tx_id?: string
  payment_tx_id?: string
  expiry_round: number
  expiry_approx_date?: string
  months_paid: number
}

const API_BASE = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 90000, // 90 seconds - increased from 30s to handle slow Algorand network + contract operations
})

// Extended timeout client for payment operations (up to 2 minutes for full payment + confirmation)
const paymentClient = axios.create({
  baseURL: API_BASE,
  timeout: 180000, // 180 seconds - gives headroom for transient testnet latency
})

function opsHeaders(apiKey?: string) {
  return apiKey?.trim() ? { 'x-api-key': apiKey.trim() } : undefined
}

function adminHeaders(adminKey?: string) {
  return adminKey?.trim() ? { 'x-admin-key': adminKey.trim() } : undefined
}

// Error message mapping for user-friendly display
const errorMessageMap: Record<string, string> = {
  IPFS_UPLOAD_FAIL: 'Could not upload insight to IPFS. Please try again.',
  CONTRACT_CALL_FAIL: 'Smart contract call failed. Check your account balance and connection.',
  PAYMENT_REJECTED: 'Payment was rejected. Verify wallet connection and balance.',
  WALLET_INSUFFICIENT_BALANCE: 'Insufficient balance. Please add funds and try again.',
  TIMEOUT: 'Request timed out. Please try again.',
}

export const api = {
  /**
   * List a new insight (seller flow)
   */
  listInsight: async (insightText: string, price: number | string, sellerWallet: string, custom_expiry_rounds?: number) => {
    try {
      const response = await client.post<ListResponse>('/list', {
        insight_text: insightText.trim(),
        price: typeof price === 'string' ? parseFloat(price) : price,
        seller_wallet: sellerWallet.trim(),
        ...(typeof custom_expiry_rounds === 'number' ? { custom_expiry_rounds } : {}),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to list insight', error)
    }
  },

  /**
   * Purchase an insight (buyer flow)
   * NOTE: Uses extended timeout (120s) because payment operations involve:
   * - Blockchain simulation (can be slow on testnet)
   * - Multiple contract calls (listing, escrow, reputation)
   * - Atomic group assembly and submission
   */
  demoPurchase: async (request: DemoPurchaseRequest) => {
    try {
      const response = await paymentClient.post<DemoPurchaseResponse>('/demo_purchase', {
        user_query: request.user_query.trim(),
        buyer_address: request.buyer_address.trim(),
        user_approval_input: request.user_approval_input.trim(),
        force_buy_for_test: request.force_buy_for_test,
        target_listing_id: request.target_listing_id,
        user_id: request.user_id,
        session_token: request.session_token,
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to purchase insight', error)
    }
  },

  /**
   * Discover and rank insights (buyer query flow)
   */
  discoverInsights: async (query: string) => {
    try {
      const response = await client.post<DiscoverResponse>('/discover', {
        user_query: query.trim(),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to discover insights', error)
    }
  },

  onboard: async (payload: OnboardRequest) => {
    try {
      const response = await client.post<OnboardResponse>('/onboard', payload)
      return response.data
    } catch (error) {
      throw new ApiError('Onboarding failed', error)
    }
  },

  login: async (payload: LoginRequest) => {
    try {
      const response = await client.post<LoginResponse>('/auth/login', payload)
      return response.data
    } catch (error) {
      throw new ApiError('Login failed', error)
    }
  },

  walletIsCustodial: async (address: string) => {
    try {
      const response = await client.get<WalletCustodialResponse>('/wallet/is_custodial', {
        params: { address: address.trim() },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to check custodial wallet status', error)
    }
  },

  walletExport: async (userId: string, password: string) => {
    try {
      const response = await client.post<WalletExportResponse>('/wallet/export', {
        user_id: userId.trim(),
        password,
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to export wallet', error)
    }
  },

  walletBalance: async (address: string) => {
    try {
      const response = await client.get<WalletBalanceResponse>('/wallet/balance', {
        params: { address: address.trim() },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch wallet balance', error)
    }
  },

  listingsFeed: async (limit = 50) => {
    try {
      const response = await client.get<ListingsFeedResponse>('/api/v1/listings', {
        params: { limit },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch listings feed', error)
    }
  },

  tracesLatest: async (limit = 20) => {
    try {
      const response = await client.get<TracesLatestResponse>('/traces/latest', {
        params: { limit },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch trace history', error)
    }
  },

  traceSession: async (sessionId: string, params?: { status?: string; eventName?: string }) => {
    try {
      const response = await client.get<TraceSessionResponse>(`/traces/${encodeURIComponent(sessionId)}`, {
        params: {
          status: params?.status,
          event_name: params?.eventName,
        },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch trace session', error)
    }
  },

  traceDownloadUrl: (sessionId: string) => `${API_BASE}/traces/${encodeURIComponent(sessionId)}/download`,

  subscriptionStatus: async (wallet: string) => {
    try {
      const response = await client.get<SubscriptionStatusResponse>('/subscription/status', {
        params: { wallet: wallet.trim() },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch subscription status', error)
    }
  },

  subscribe: async (buyerWallet: string, months: number) => {
    try {
      const response = await client.post<SubscribeResponse>('/subscribe', {
        buyer_wallet: buyerWallet.trim(),
        months,
      })
      return response.data
    } catch (error) {
      throw new ApiError('Subscription purchase failed', error)
    }
  },

  subscribeAtomically: async (buyerWallet: string, months: number, buyerPrivateKey?: string) => {
    try {
      const response = await client.post<AtomicSubscribeResponse>('/api/v1/subscribe_atomically', {
        buyer_wallet: buyerWallet.trim(),
        months,
        ...(buyerPrivateKey?.trim() ? { buyer_private_key: buyerPrivateKey.trim() } : {}),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Atomic subscription purchase failed', error)
    }
  },

  feeConfig: async () => {
    try {
      const response = await client.get<FeeConfigResponse>('/fee_config')
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch fee config', error)
    }
  },

  releaseForSubscriber: async (buyerWallet: string, listingId: number) => {
    try {
      const response = await client.post<SubscriptionReleaseResponse>('/escrow/release_for_subscriber', {
        buyer_wallet: buyerWallet.trim(),
        listing_id: listingId,
      })
      return response.data
    } catch (error) {
      throw new ApiError('Subscriber content release failed', error)
    }
  },

  /**
   * Check system health
   */
  health: async () => {
    try {
      const response = await client.get<HealthResponse>('/health')
      return response.data
    } catch (error) {
      throw new ApiError('System health check failed', error)
    }
  },

  /**
   * Fetch normalized transaction ledger from backend indexer endpoint
   */
  ledger: async (params?: { limit?: number; address?: string; nextToken?: string }) => {
    try {
      const response = await client.get<LedgerResponse>('/ledger', {
        params: {
          limit: params?.limit ?? 250,
          address: params?.address,
          next_token: params?.nextToken,
        },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch activity ledger', error)
    }
  },

  /**
   * Fetch operations dashboard overview with contracts, metrics, environment, and events
   */
  operationsOverview: async (params?: { verifyOnChain?: boolean }) => {
    try {
      const response = await client.get<OpsOverviewResponse>('/ops/overview', {
        params: {
          verify_on_chain: params?.verifyOnChain ?? true,
        },
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch operations overview', error)
    }
  },

  operationsAccessCheck: async (apiKey?: string) => {
    try {
      const response = await client.get<OpsAccessCheckResponse>('/ops/access-check', {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Operator access check failed', error)
    }
  },

  operationsOverviewSecure: async (params?: { verifyOnChain?: boolean; apiKey?: string }) => {
    try {
      const response = await client.get<OpsOverviewResponse>('/ops/overview', {
        params: {
          verify_on_chain: params?.verifyOnChain ?? true,
        },
        headers: opsHeaders(params?.apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch operations overview', error)
    }
  },

  operationsSyntheticHistory: async (apiKey?: string) => {
    try {
      const response = await client.get<OpsSyntheticHistoryResponse>('/ops/synthetic-tests', {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch synthetic test history', error)
    }
  },

  operationsRunSyntheticTest: async (
    payload?: { user_query?: string; buyer_address?: string; seller_wallet?: string; price?: number },
    apiKey?: string,
  ) => {
    try {
      const response = await client.post<OpsSyntheticRunResponse>('/ops/synthetic-test', payload || {}, {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Synthetic transaction test failed', error)
    }
  },

  operationsIpfsHealth: async (apiKey?: string) => {
    try {
      const response = await client.get<OpsIpfsHealthResponse>('/ops/ipfs/health', {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch IPFS health', error)
    }
  },

  operationsIpfsTestUpload: async (payload?: { content?: string; filename?: string }, apiKey?: string) => {
    try {
      const response = await client.post<OpsIpfsUploadResponse>('/ops/ipfs/test-upload', payload || {}, {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('IPFS test upload failed', error)
    }
  },

  operationsAlgorandStatus: async (apiKey?: string) => {
    try {
      const response = await client.get<OpsAlgorandStatusResponse>('/ops/algorand/status', {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch Algorand status', error)
    }
  },

  operationsAlgorandTest: async (apiKey?: string) => {
    try {
      const response = await client.post<OpsAlgorandStatusResponse>('/ops/algorand/test', {}, {
        headers: opsHeaders(apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Algorand connectivity test failed', error)
    }
  },

  operationsPingEndpoint: async (endpoint: string, apiKey?: string) => {
    try {
      const response = await client.post<OpsPingResponse>(
        '/ops/ping',
        { endpoint },
        {
          headers: opsHeaders(apiKey),
        },
      )
      return response.data
    } catch (error) {
      throw new ApiError('Endpoint ping failed', error)
    }
  },

  operationsDiagnosticsBundle: async (params?: { includeContractScan?: boolean; apiKey?: string }) => {
    try {
      const response = await client.get<OpsDiagnosticsResponse>('/ops/diagnostics', {
        params: {
          include_contract_scan: params?.includeContractScan ?? false,
        },
        headers: opsHeaders(params?.apiKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Diagnostics export failed', error)
    }
  },

  adminCuratorTriggerNow: async (adminKey?: string) => {
    try {
      const response = await client.post<AdminCuratorTriggerResponse>('/admin/curator/trigger_now', {}, {
        headers: adminHeaders(adminKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to trigger curator cycle', error)
    }
  },

  adminCacheStats: async () => {
    try {
      const response = await client.get<OpsCacheStatsResponse>('/admin/cache/stats')
      return response.data
    } catch (error) {
      throw new ApiError('Failed to fetch cache stats', error)
    }
  },

  adminGenerateApiKey: async (payload: { owner_name: string; owner_email: string; tier: string; plaintext_key?: string }, adminKey?: string) => {
    try {
      const response = await client.post<AdminGenerateApiKeyResponse>('/admin/api-keys/generate', payload, {
        headers: adminHeaders(adminKey),
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to generate API key', error)
    }
  },

  /**
   * Fetch the list of verified agents from AgentRegistry
   */
  verifiedAgents: async () => {
    try {
      const response = await client.get<RegisteredAgentsResponse>('/agents/registered')
      return response.data.agents || []
    } catch (error) {
      throw new ApiError('Failed to fetch verified agents', error)
    }
  },

  /**
   * Fetch seller profile (Tier 1 & Tier 2 data)
   */
  sellerProfile: async (wallet: string) => {
    try {
      const response = await client.get<{ success: boolean; profile: any }>(`/sellers/${wallet.trim()}/profile`)
      return response.data.profile
    } catch (error) {
      throw new ApiError(`Failed to fetch seller profile for ${wallet}`, error)
    }
  },

  /**
   * Fetch paginated seller listing history
   */
  sellerListings: async (wallet: string, page = 1, pageSize = 10) => {
    try {
      const response = await client.get<{ success: boolean; listings: any[] }>(`/sellers/${wallet.trim()}/listings`, {
        params: { page, page_size: pageSize },
      })
      return response.data
    } catch (error) {
      throw new ApiError(`Failed to fetch seller listings for ${wallet}`, error)
    }
  },

  /**
   * Fetch seller leaderboard (top sellers by earnings)
   */
  sellerLeaderboard: async (limit = 10) => {
    try {
      const response = await client.get<{ success: boolean; sellers: any[] }>('/sellers/leaderboard', {
        params: { limit },
      })
      return response.data.sellers
    } catch (error) {
      throw new ApiError('Failed to fetch seller leaderboard', error)
    }
  },

  /**
   * Fetch seller reputation history (sparkline data)
   */
  sellerReputationHistory: async (wallet: string) => {
    try {
      const response = await client.get<{ success: boolean; history: any[]; current_score: number }>(
        `/sellers/${wallet.trim()}/reputation_history`,
      )
      return response.data
    } catch (error) {
      throw new ApiError(`Failed to fetch seller reputation history for ${wallet}`, error)
    }
  },

  sellerReputation: async (wallet: string) => {
    try {
      const response = await client.get<SellerReputationResponse>(`/sellers/${wallet.trim()}/reputation`)
      return response.data
    } catch (error) {
      throw new ApiError(`Failed to fetch seller reputation for ${wallet}`, error)
    }
  },

  sellerPurchaseHistory: async (wallet: string, limit = 20) => {
    try {
      const response = await client.get<SellerPurchaseHistoryResponse>(`/sellers/${wallet.trim()}/purchase_history`, {
        params: { limit },
      })
      return response.data
    } catch (error) {
      throw new ApiError(`Failed to fetch seller purchase history for ${wallet}`, error)
    }
  },

  /**
   * Fetch seller evaluations (Buyer Agent scores)
   */
  sellerEvaluations: async (wallet: string, limit = 10) => {
    try {
      const response = await client.get<{ success: boolean; evaluations: any[] }>(
        `/sellers/${wallet.trim()}/evaluations`,
        {
          params: { limit },
        },
      )
      return response.data.evaluations
    } catch (error) {
      throw new ApiError(`Failed to fetch seller evaluations for ${wallet}`, error)
    }
  },
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  public readonly originalError: unknown
  public readonly userMessage: string
  public readonly recoverySuggestion?: string

  constructor(message: string, error: unknown) {
    super(message)
    this.originalError = error
    const { message: userMessage, recovery } = this.extractUserMessage(error)
    this.userMessage = userMessage
    this.recoverySuggestion = recovery
  }

  private extractUserMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
      const data = error.response?.data as Record<string, unknown> | undefined

      // If backend provided structured envelope, try to extract recovery suggestion
      const details = data?.error && typeof data.error === 'object' ? (data.error as any).details : data?.details
      const recovery = details && typeof details?.recovery_suggestion === 'string' ? details.recovery_suggestion : undefined

      // Check backend error message
      if (typeof data?.error === 'string') return { message: data.error, recovery }
      if (typeof data?.detail === 'string') return { message: data.detail, recovery }
      if (typeof data?.message === 'string') return { message: data.message, recovery }

      // Network/CORS/backend-down cases should never fall through to generic message.
      if (!error.response) {
        if (error.code === 'ECONNABORTED') return { message: errorMessageMap.TIMEOUT, recovery }
        if (error.code === 'ERR_NETWORK') {
          return { message: 'Cannot reach backend API. Ensure backend server is running and CORS origin is configured.', recovery }
        }
        return { message: 'Network request failed. Verify backend URL and internet connectivity.', recovery }
      }

      // Map common error codes
      for (const [code, message] of Object.entries(errorMessageMap)) {
        const backendError = typeof data?.error === 'string' ? data.error : ''
        if (this.message.includes(code) || backendError.includes(code)) {
          return { message, recovery }
        }
      }

      // Use status code fallback
      if (error.code === 'ECONNABORTED') return { message: errorMessageMap.TIMEOUT, recovery }
      if (error.response?.status === 500)
        return { message: 'Server error. Please try again later.', recovery }
      if (error.response?.status === 400)
        return { message: 'Invalid request. Please check your input.', recovery }
    } else if (error instanceof Error) {
      return { message: error.message }
    }

    return { message: 'An unexpected error occurred. Please try again.' }
  }
}
