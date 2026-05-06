import { useEffect, useState } from 'react'
import type { RegisteredAgent } from '../../types'
import { getVerifiedAgentRecord } from '../../utils/verifiedAgents'

interface VerifiedBadgeProps {
  walletAddress: string
  compact?: boolean
}

export default function VerifiedBadge({ walletAddress, compact = false }: VerifiedBadgeProps) {
  const [agentRecord, setAgentRecord] = useState<RegisteredAgent | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let mounted = true

    const fetchRecord = async () => {
      setIsLoading(true)
      const record = await getVerifiedAgentRecord(walletAddress)
      if (mounted) {
        setAgentRecord(record)
        setIsLoading(false)
      }
    }

    fetchRecord()

    return () => {
      mounted = false
    }
  }, [walletAddress])

  if (isLoading || !agentRecord) {
    return null
  }

  if (compact) {
    return (
      <span className="verified-badge verified-badge--compact" title={`Verified ${agentRecord.role}`}>
        ✓ Verified
      </span>
    )
  }

  return (
    <div className="verified-badge verified-badge--full">
      <span className="verified-badge-icon">✓</span>
      <div className="verified-badge-content">
        <span className="verified-badge-label">Verified Agent</span>
        <span className="verified-badge-role">{agentRecord.role}</span>
      </div>
    </div>
  )
}
