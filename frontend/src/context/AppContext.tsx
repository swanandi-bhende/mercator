import React, { createContext, useState, useCallback } from 'react'
import type { Insight, PaymentState } from '../types'

export interface AppContextType {
  // Navigation & Flow State
  currentJourney: 'home' | 'seller' | 'buyer'
  setCurrentJourney: (journey: 'home' | 'seller' | 'buyer') => void

  // Seller State
  sellerWallet: string | null
  setSellerWallet: (wallet: string | null) => void
  lastListingTxId: string | null
  setLastListingTxId: (txId: string | null) => void
  listingInsight: Insight | null
  setListingInsight: (insight: Insight | null) => void

  // Buyer State
  selectedInsight: Insight | null
  setSelectedInsight: (insight: Insight | null) => void
  sellerMetadata: {
    reputation?: number
    address?: string
    totalSales?: number
    listingStatus?: string
    riskSignal?: string
    rankingReason?: string
  } | null
  setSellerMetadata: (
    metadata: {
      reputation?: number
      address?: string
      totalSales?: number
      listingStatus?: string
      riskSignal?: string
      rankingReason?: string
    } | null,
  ) => void
  buyerWallet: string | null
  setBuyerWallet: (wallet: string | null) => void

  // Transaction State (shared across seller & buyer flows)
  paymentState: PaymentState | null
  setPaymentState: (state: PaymentState | null) => void
  lastTransactionId: string | null
  setLastTransactionId: (txId: string | null) => void

  // Operator Mode
  isOperator: boolean
  setIsOperator: (operator: boolean) => void
  operatorKey: string | null
  setOperatorKey: (key: string | null) => void

  // Helper functions
  resetSellerFlow: () => void
  resetBuyerFlow: () => void
  clearAllState: () => void
}

export const AppContext = createContext<AppContextType | undefined>(undefined)

export function AppProvider({ children }: { children: React.ReactNode }) {
  // Navigation & Flow
  const [currentJourney, setCurrentJourney] = useState<
    'home' | 'seller' | 'buyer'
  >('home')

  // Seller state
  const [sellerWallet, setSellerWallet] = useState<string | null>(null)
  const [lastListingTxId, setLastListingTxId] = useState<string | null>(null)
  const [listingInsight, setListingInsight] = useState<Insight | null>(null)

  // Buyer state
  const [selectedInsight, setSelectedInsight] = useState<Insight | null>(null)
  const [sellerMetadata, setSellerMetadata] = useState<{
    reputation?: number
    address?: string
    totalSales?: number
    listingStatus?: string
    riskSignal?: string
    rankingReason?: string
  } | null>(null)
  const [buyerWallet, setBuyerWallet] = useState<string | null>(null)

  // Transaction state (shared)
  const [paymentState, setPaymentState] = useState<PaymentState | null>(null)
  const [lastTransactionId, setLastTransactionId] = useState<string | null>(null)

  // Operator mode
  const [isOperator, setIsOperator] = useState(false)
  const [operatorKey, setOperatorKey] = useState<string | null>(
    typeof window !== 'undefined'
      ? localStorage.getItem('operatorKey')
      : null,
  )

  // Helper functions
  const resetSellerFlow = useCallback(() => {
    setSellerWallet(null)
    setLastListingTxId(null)
    setListingInsight(null)
    setPaymentState(null)
    setCurrentJourney('home')
  }, [])

  const resetBuyerFlow = useCallback(() => {
    setSelectedInsight(null)
    setSellerMetadata(null)
    setBuyerWallet(null)
    setPaymentState(null)
    setCurrentJourney('home')
  }, [])

  const clearAllState = useCallback(() => {
    resetSellerFlow()
    resetBuyerFlow()
    setIsOperator(false)
    setOperatorKey(null)
  }, [resetSellerFlow, resetBuyerFlow])

  return (
    <AppContext.Provider
      value={{
        currentJourney,
        setCurrentJourney,
        sellerWallet,
        setSellerWallet,
        lastListingTxId,
        setLastListingTxId,
        listingInsight,
        setListingInsight,
        selectedInsight,
        setSelectedInsight,
        sellerMetadata,
        setSellerMetadata,
        buyerWallet,
        setBuyerWallet,
        paymentState,
        setPaymentState,
        lastTransactionId,
        setLastTransactionId,
        isOperator,
        setIsOperator,
        operatorKey,
        setOperatorKey,
        resetSellerFlow,
        resetBuyerFlow,
        clearAllState,
      }}
    >
      {children}
    </AppContext.Provider>
  )
}

export function useAppContext() {
  const context = React.useContext(AppContext)
  if (context === undefined) {
    throw new Error('useAppContext must be used within AppProvider')
  }
  return context
}
