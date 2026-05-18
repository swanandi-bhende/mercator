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
  target_listing_id?: number
  user_id?: string
  session_token?: string
}

export interface OnboardRequest {
  display_name: string
  email: string
  password: string
}

export interface OnboardResponse {
  user_id: string
  session_token: string
  algo_address: string
  display_name: string
  algo_balance_micro: number
  usdc_balance_micro: number
  funding_status: string
  message: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  user_id: string
  session_token: string
  algo_address: string
  message: string
}

export interface WalletCustodialResponse {
  is_custodial: boolean
  user_id?: string | null
  address?: string
  message?: string
  error?: string
}

export interface WalletExportResponse {
  mnemonic: string
  warning: string
}

export interface WalletBalanceResponse {
  algo_balance_micro: number
  usdc_balance_micro: number
  algo_balance_display: number
  usdc_balance_display: number
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

export interface SubscriptionReleaseResponse {
  success: boolean
  tx_id: string
  buyer_wallet: string
  listing_id: number
  payment_method: string
  subscription_access_granted: boolean
}

export interface SubscriptionStatusResponse {
  success: boolean
  active: boolean
  expiry_round: number
  expiry_approx_date: string
  months_remaining: number
  total_months_paid: number
  total_usdc_paid_micro: number
  source_type?: string
  error?: string
}

export interface FeeConfigResponse {
  success: boolean
  app_id?: number
  fee_rate_bps?: number
  fee_rate_display?: string
  treasury_address?: string
  total_fees_collected?: number
  usdc_asset_id?: number
  error?: string
}

export interface AtomicSubscribeResponse {
  success: boolean
  data?: {
    payment_tx_id?: string
    subscription_tx_id?: string
    tx_ids?: string[]
    group_id?: string
    confirmed_round?: number
    all_confirmed?: boolean
    months?: number
    buyer_wallet?: string
  }
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
  request_id?: string
  timestamp?: string
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
  source_type?: string
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

export interface ListingsFeedItem {
  timestamp: string
  tx_id: string
  cid: string
  listing_id: string | number
  asa_id: string | number
  seller_wallet: string
  price_usdc: number
  insight_text: string
  seller_reputation?: number
  source_type?: string
}

export interface ListingsFeedResponse {
  success: boolean
  count: number
  listings: ListingsFeedItem[]
}

export interface TraceEvent {
  event_type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface TraceSessionSummary {
  session_id: string
  last_event: string
  event_count: number
}

export interface TracesLatestResponse {
  success: boolean
  sessions: TraceSessionSummary[]
}

export interface TraceSessionResponse {
  success: boolean
  session_id: string
  count: number
  events: TraceEvent[]
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

export interface OpsCacheStat {
  present: boolean
  size?: number
  maxsize?: number
}

export interface OpsCacheStatsResponse {
  profile_cache: OpsCacheStat
  reputation_cache: OpsCacheStat
  listings_cache: OpsCacheStat
}

export interface AdminGenerateApiKeyResponse {
  success: boolean
  key_id: string
  plaintext_key: string
  owner_name: string
  owner_email: string
  tier: string
}

export interface AdminCuratorTriggerResponse {
  success: boolean
  results: Array<Record<string, unknown>>
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

// Agent Registry Types
export interface RegisteredAgent {
  wallet: string
  agent_name: string
  role: string
  registered_at_round: number
  total_transactions: number
}

export interface RegisteredAgentsResponse {
  success: boolean
  agents: RegisteredAgent[]
  count: number
  source?: string
  error?: string
  degraded?: boolean
}

// Seller Profile Types
export interface DecayInfo {
  last_updated_at: string | null
  decay_rate: number | null
  decay_points_applied: number | null
}

export interface SellerStats {
  seller_wallet: string
  total_purchases: number
  total_usdc_earned_micro: number
  avg_price_usdc: number | null
  first_listing_date: string | null
  last_purchase_date: string | null
  recent_evaluations_avg_score: number | null
  display_name: string
  registered_agent_name: string | null
  registered_agent_role: string | null
  registered_at_round: number | null
  trust_summary: string | null
}

export interface ListingHistoryEntry {
  listing_id: string
  timestamp_iso: string
  price_usdc: number | null
  purchase_count: number
  ipfs_cid: string | null
}

export interface ReputationHistoryEntry {
  score_before: number
  score_after: number
  change: number
  recorded_at: string
}

export interface EvaluationRecord {
  evaluation_id: string
  seller_wallet: string
  insight_listing_id: string
  total_score: number
  quality_score: number
  relevance_score: number
  decision: string
  created_at: string
}

export interface SellerProfileResponse {
  seller_wallet: string
  display_name: string
  registered_agent_name: string | null
  registered_agent_role: string | null
  registered_at_round: number | null
  reputation_score_effective: number
  reputation_score_raw: number
  decay_info: DecayInfo
  total_purchases: number
  total_usdc_earned_micro: number
  avg_price_usdc: number | null
  first_listing_date: string | null
  last_purchase_date: string | null
  days_active: number | null
  recent_evaluations_avg_score: number | null
  reputation_history: ReputationHistoryEntry[]
  evaluations: EvaluationRecord[]
  trust_summary: string
}

export interface SellerLeaderboardEntry {
  seller_wallet: string
  display_name: string
  reputation_score: number
  total_purchases: number
  total_usdc_earned: number
  avg_price_usdc: number | null
}

export interface SellerReputationResponse {
  wallet: string
  effective_score: number
  raw_score: number
  total_purchases: number
  decay_info: DecayInfo
}

export interface SellerPurchaseHistoryEntry {
  buyer_wallet: string
  listing_id: string | number
  purchase_round: number | null
  purchase_approx_date: string | null
}

export interface SellerPurchaseHistoryResponse {
  success: boolean
  wallet: string
  purchase_history: SellerPurchaseHistoryEntry[]
  count?: number
  note?: string
  error?: string
}

export interface ListingHistoryResponse {
  success: boolean
  listings: ListingHistoryEntry[]
  page: number
  page_size: number
  total_count: number
  has_more: boolean
  total_pages: number
}
