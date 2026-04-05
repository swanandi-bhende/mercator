import axios from 'axios'
import type {
  ListResponse,
  DemoPurchaseRequest,
  DemoPurchaseResponse,
  HealthResponse,
} from '../types'

const API_BASE = 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

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
   */
  demoPurchase: async (request: DemoPurchaseRequest) => {
    try {
      const response = await client.post<DemoPurchaseResponse>('/demo_purchase', {
        user_query: request.user_query.trim(),
        buyer_address: request.buyer_address.trim(),
        user_approval_input: request.user_approval_input.trim(),
        force_buy_for_test: request.force_buy_for_test,
      })
      return response.data
    } catch (error) {
      throw new ApiError('Failed to purchase insight', error)
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
