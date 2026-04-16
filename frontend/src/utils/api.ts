import axios from 'axios'
import type {
  ListResponse,
  DemoPurchaseRequest,
  DemoPurchaseResponse,
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
} from '../types'

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
  listInsight: async (insightText: string, price: number | string, sellerWallet: string) => {
    try {
      const response = await client.post<ListResponse>('/list', {
        insight_text: insightText.trim(),
        price: typeof price === 'string' ? parseFloat(price) : price,
        seller_wallet: sellerWallet.trim(),
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
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  public readonly originalError: unknown
  public readonly userMessage: string

  constructor(message: string, error: unknown) {
    super(message)
    this.originalError = error
    this.userMessage = this.extractUserMessage(error)
  }

  private extractUserMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
      const data = error.response?.data as Record<string, unknown> | undefined

      // Check backend error message
      if (typeof data?.error === 'string') return data.error
      if (typeof data?.detail === 'string') return data.detail
      if (typeof data?.message === 'string') return data.message

      // Network/CORS/backend-down cases should never fall through to generic message.
      if (!error.response) {
        if (error.code === 'ECONNABORTED') return errorMessageMap.TIMEOUT
        if (error.code === 'ERR_NETWORK') {
          return 'Cannot reach backend API. Ensure backend server is running and CORS origin is configured.'
        }
        return 'Network request failed. Verify backend URL and internet connectivity.'
      }

      // Map common error codes
      for (const [code, message] of Object.entries(errorMessageMap)) {
        const backendError = typeof data?.error === 'string' ? data.error : ''
        if (this.message.includes(code) || backendError.includes(code)) {
          return message
        }
      }

      // Use status code fallback
      if (error.code === 'ECONNABORTED') return errorMessageMap.TIMEOUT
      if (error.response?.status === 500)
        return 'Server error. Please try again later.'
      if (error.response?.status === 400)
        return 'Invalid request. Please check your input.'
    } else if (error instanceof Error) {
      return error.message
    }

    return 'An unexpected error occurred. Please try again.'
  }
}
