// Insight and Market Data Types
export interface Insight {
  id?: string
  listing_id?: string
  asa_id?: string
  insight_text: string
  price: number
  seller_wallet: string
  seller_reputation?: number
  cid?: string
  created_at?: string
  tx_id?: string
}

// Backend Response Types
export interface ListResponse {
  success: boolean
  transaction_id?: string
  txId?: string
  tx_id?: string
  cid?: string
  listing_id?: string
  asa_id?: string
  explorer_url?: string
  message?: string
  error?: string
}

export interface DemoPurchaseRequest {
  user_query: string
  buyer_address: string
  user_approval_input: string
  force_buy_for_test: boolean
}

export interface DemoPurchaseResponse {
  success: boolean
  final_insight_text: string
  result: {
    decision: 'BUY' | 'SKIP'
    relevance?: number
    reputation?: number
    price_ok?: boolean
    reasoning?: string
    payment_status?: string
    escrow_status?: string
  }
  error?: string
  message?: string
}

export interface DiscoverMatch {
  listing_id: number
  price_micro_usdc: number
  price_usdc: number
  reputation: number
  cid: string
  asa_id: number
  score: number
  insight_preview: string
  seller_wallet?: string
  listing_status?: string
}

export interface DiscoverResponse {
  success: boolean
  query: string
  embedding_fallback?: boolean
  matches: DiscoverMatch[]
  message?: string
  error?: string
  degraded?: boolean
  diagnostics?: {
    code: string
    detail: string
  }
}

export interface HealthResponse {
  status: 'ok' | 'error'
  version?: string
  timestamp?: string
}

// Application State Types
export interface AppState {
  selectedInsight?: Insight
  userWallet?: string
  buyerWallet?: string
  isOperator: boolean
}

export interface PaymentState {
  stage: 'pending' | 'confirmed' | 'approved' | 'processing' | 'completed' | 'failed'
  txId?: string
  error?: string
  timestamp?: string
}

export interface OperatorMetrics {
  endpoint: string
  avgLatency: number
  successRate: number
  errorCount: number
  lastCall?: string
}

export interface ContractStatus {
  name: string
  appId: number
  status: 'deployed' | 'error' | 'missing'
  lastCall?: string
  callCount?: number
}
