// Insight and Market Data Types
export interface Insight {
  id?: string
  listing_id?: string
  asa_id?: string
  insight_text: string
  price: number
  seller_wallet: string
  seller_reputation?: number
  relevance_score?: number
  query_text?: string
  market_context?: string
  synopsis?: string
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
    decision: 'BUY' | 'SKIP' | 'BUY_PENDING_APPROVAL' | 'ERROR'
    relevance?: number
    reputation?: number
    price_ok?: boolean
    reasoning?: string
    payment_status?: string | {
      success?: boolean
      tx_id?: string
      message?: string
      error?: string
      explorer_url?: string
      post_payment_output?: string
      payment_details?: {
        listing_id?: number
        buyer_address?: string
        seller_address?: string
        amount_usdc?: number
        settlement_asset_id?: number
      }
    }
    escrow_status?: string
    message?: string
    error?: string
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
  services?: {
    api?: { status: string; detail: string }
    algod?: { status: string; detail: string }
    indexer?: { status: string; detail: string }
    listing_app?: { status: string; detail: string }
    escrow_app?: { status: string; detail: string }
  }
}

export interface LedgerRecord {
  id: string
  timestampIso: string
  actionType: 'listing_created' | 'payment_confirmed' | 'escrow_released' | 'insight_delivered'
  seller: string
  buyer: string
  amountUsdc: number
  status: 'confirmed' | 'pending' | 'failed' | 'completed'
  txId: string
  explorerUrl: string
  cid: string
  ipfsUrl: string
  listingId: string
  contractId: string
  confirmationRound: number
  feeAlgo: string
  escrowStatus: string
  contentHash: string
  listingMetadata: string
  errorMessage?: string
}

export interface LedgerResponse {
  success: boolean
  records: LedgerRecord[]
  count: number
  nextToken?: string | null
  source?: string
  error?: string
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
  paymentTxId?: string
  escrowTxId?: string
  ipfsCid?: string
  listingId?: string
  deliveredInsightText?: string
  escrowReleased?: boolean
  explorerPaymentUrl?: string
  explorerEscrowUrl?: string
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
