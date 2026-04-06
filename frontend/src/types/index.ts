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
  status: 'ok' | 'error' | 'degraded'
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

export interface OpsContractStatus {
  name: string
  app_id: number | string
  creator: string
  approval_hash: string
  total_calls: number
  last_call: string | null
  state: string
  status: 'healthy' | 'warning' | 'broken' | string
  explorer_url: string
  errors: string[]
}

export interface OpsEndpointErrorGroup {
  category: string
  count: number
  logs: Array<{
    timestamp: string
    latency_ms: number
    anon_user: string
  }>
}

export interface OpsEndpointMetric {
  endpoint: string
  latency_ms: number
  success_rate: number
  throughput_rpm: number
  recent_errors: OpsEndpointErrorGroup[]
  trend: Array<{
    throughput: number
    success_rate: number
  }>
}

export interface OpsEvent {
  id: string
  timestamp: string
  severity: 'error' | 'warning' | 'recovery' | 'info' | string
  type: string
  message: string
  details: Record<string, unknown>
}

export interface OpsOverviewResponse {
  success: boolean
  timestamp: string
  operator_access?: {
    authorized: boolean
    access_via_localhost: boolean
    access_via_api_key: boolean
    reason: string
  }
  operator_mode?: {
    active: boolean
    session_ttl_hint_seconds: number
  }
  health: HealthResponse
  contracts: OpsContractStatus[]
  request_metrics: OpsEndpointMetric[]
  endpoint_heatmap?: OpsEndpointHeatCell[]
  ipfs?: OpsIpfsHealth
  algorand?: OpsAlgorandStatus
  synthetic_recent?: OpsSyntheticResult[]
  environment: {
    network: string
    warning: string
    contracts: Record<string, string>
    wallets: Array<{
      label: string
      address: string
      algo_balance: number | null
    }>
    redacted_config: Record<string, string>
  }
  events: OpsEvent[]
}

export interface OpsEndpointSample {
  timestamp: string
  method: string
  status_code: number
  latency_ms: number
  anon_user: string
}

export interface OpsEndpointHeatCell {
  endpoint: string
  tone: 'good' | 'warn' | 'bad' | string
  status: 'healthy' | 'warning' | 'error' | string
  latency_ms: number
  success_rate: number
  sample_count: number
  summary: string
  samples: OpsEndpointSample[]
}

export interface OpsSyntheticStep {
  name: string
  status: 'passed' | 'failed' | string
  duration_ms: number
  message: string
  details: Record<string, unknown>
}

export interface OpsSyntheticResult {
  id: string
  timestamp: string
  status: 'passed' | 'failed' | string
  stopped_on: string | null
  total_duration_ms: number
  steps: OpsSyntheticStep[]
  error: string
}

export interface OpsIpfsHealth {
  status: 'healthy' | 'warning' | 'broken' | string
  connection: {
    pinata: {
      url: string
      status: string
      latency_ms: number
      http_status: number
      error: string
    }
    gateways: Array<{
      url: string
      status: string
      latency_ms: number
      http_status: number
      error: string
    }>
  }
  latency_ms: number
  slow_threshold_ms: number
  upload_success_rate: number
  last_upload: Record<string, unknown> | null
  fallback_gateways: string[]
  trend: Array<{
    timestamp: string
    latency_ms: number
    success: boolean
  }>
  timestamp: string
}

export interface OpsAlgorandStatus {
  status: 'healthy' | 'warning' | 'broken' | string
  latency_ms: number
  node_health: string
  current_round: number
  sync_status: string
  catchup_time: number
  time_since_last_round_ms: number
  recent_activity_count: number
  fee_suggestion_micro_algo: number
  warning: string
  trend: Array<{
    timestamp: string
    round: number
    latency_ms: number
    synced: boolean
  }>
  timestamp: string
}

export interface OpsAccessCheckResponse {
  success: boolean
  timestamp: string
  access: {
    authorized: boolean
    access_via_localhost: boolean
    access_via_api_key: boolean
    reason: string
  }
}

export interface OpsSyntheticHistoryResponse {
  success: boolean
  timestamp: string
  results: OpsSyntheticResult[]
}

export interface OpsSyntheticRunResponse {
  success: boolean
  timestamp: string
  result: OpsSyntheticResult
  history: OpsSyntheticResult[]
}

export interface OpsIpfsHealthResponse {
  success: boolean
  timestamp: string
  ipfs: OpsIpfsHealth
}

export interface OpsIpfsUploadResponse {
  success: boolean
  timestamp: string
  cid: string
  latency_ms: number
  gateway_url: string
}

export interface OpsAlgorandStatusResponse {
  success: boolean
  timestamp: string
  algorand: OpsAlgorandStatus
}

export interface OpsPingResponse {
  success: boolean
  timestamp: string
  result: {
    success: boolean
    endpoint: string
    latency_ms: number
    status: string
    summary: string
    payload_preview: Record<string, unknown>
  }
}

export interface OpsDiagnosticsResponse {
  success: boolean
  timestamp: string
  bundle: {
    overview: OpsOverviewResponse
    synthetic_tests: OpsSyntheticResult[]
    metrics_window_size: number
    ipfs_window_size: number
    algorand_window_size: number
    log_tail: string[]
    notes: string
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
