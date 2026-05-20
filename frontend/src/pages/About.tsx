export default function AboutPage() {
  return (
    <div className="mercator-themed-page min-h-screen bg-[radial-gradient(1200px_560px_at_4%_0%,rgba(220,176,153,0.22),transparent_50%),radial-gradient(900px_500px_at_100%_14%,rgba(111,57,70,0.14),transparent_48%),linear-gradient(180deg,#fff8f4_0%,#fffdf8_100%)] px-4 py-12">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="mercator-elevated-card rounded-3xl bg-white p-8 text-center">
          <h1 className="mb-4 text-4xl font-bold text-[#22191a]">About Mercator</h1>
          <p className="text-xl text-[#5f4448]">
            A blockchain-powered marketplace for verified market intelligence
          </p>
        </div>

        {/* The Problem */}
        <div className="mercator-elevated-card rounded-3xl bg-white p-8">
          <h2 className="mb-4 text-2xl font-bold text-[#22191a]">The Problem</h2>
          <p className="text-[#5f4448]">
            Market intelligence is fragmented, unverified, and expensive. Gated research reports,
            advisory calls, and insider tips cost thousands of dollars. Meanwhile, independent
            traders and analysts with valuable insights have no way to monetize or distribute them
            at scale.
          </p>
        </div>

        {/* The Solution */}
        <div className="mercator-elevated-card rounded-3xl bg-white p-8">
          <h2 className="mb-4 text-2xl font-bold text-[#22191a]">The Solution</h2>
          <p className="mb-4 text-[#5f4448]">
            Mercator is a peer-to-peer marketplace for market insights, powered by the Algorand
            blockchain. It connects sellers (analysts, traders, researchers) directly with buyers
            (institutions, funds, retail traders) without middlemen.
          </p>
          <p className="text-[#5f4448]">
            Every transaction is verified on-chain, every seller has an auditable reputation score,
            and every insight is priced by the market, not by gatekeepers.
          </p>
        </div>

        {/* How It Works */}
        <div className="mercator-elevated-card rounded-3xl bg-white p-8">
          <h2 className="mb-4 text-2xl font-bold text-[#22191a]">How It Works</h2>
          <ol className="space-y-4 text-[#5f4448]">
            <li>
              <strong>1. Seller lists an insight</strong> – An analyst or trader writes a market
              insight (analysis, prediction, signal) and sets a price in USDC.
            </li>
            <li>
              <strong>2. Insight goes to IPFS</strong> – The insight is encrypted and stored on
              IPFS. A content hash (CID) is generated and posted to Algorand.
            </li>
            <li>
              <strong>3. Seller gets paid</strong> – The seller receives an NFT (ASA) representing
              ownership of that insight. They can trade, gift, or hold it.
            </li>
            <li>
              <strong>4. Buyer searches</strong> – A buyer types a market question. Our AI agent
              searches stored insights and ranks them by relevance, seller reputation, and price.
            </li>
            <li>
              <strong>5. Agent evaluates</strong> – The agent checks: Is this insight relevant?
              Is the seller trustworthy? Is the price fair? Should we buy?
            </li>
            <li>
              <strong>6. Buyer approves</strong> – If the agent recommends buying, the buyer
              approves the x402 payment. Payment goes into an escrow smart contract.
            </li>
            <li>
              <strong>7. Payment confirmed</strong> – The payment is confirmed on-chain. The
              seller's balance updates. Reputation points are awarded.
            </li>
            <li>
              <strong>8. Content unlocked</strong> – The buyer receives the IPFS CID and can
              download the full insight content immediately.
            </li>
          </ol>
        </div>

        {/* Key Principles */}
        <div className="mercator-elevated-card rounded-3xl bg-white p-8">
          <h2 className="mb-4 text-2xl font-bold text-[#22191a]">Key Principles</h2>
          <ul className="space-y-3 text-[#5f4448]">
            <li>
              <strong>Trustless:</strong> All transactions are verified on-chain. No middleman can
              steal, corrupt, or censor.
            </li>
            <li>
              <strong>Transparent:</strong> Every transaction is auditable. Seller reputation is
              visible. Prices are set by buyers and sellers, not algorithms.
            </li>
            <li>
              <strong>Peer-to-Peer:</strong> No gatekeepers. Any analyst or trader can sell. Any
              buyer can purchase at any price.
            </li>
            <li>
              <strong>Agent-Driven:</strong> Our AI agent reduces buyer risk by evaluating sellers
              and recommending purchases. It protects the market from low-quality or scammy insights.
            </li>
          </ul>
        </div>

        {/* The Future */}
        <div className="mercator-elevated-card rounded-3xl bg-white p-8">
          <h2 className="mb-4 text-2xl font-bold text-[#22191a]">The Future</h2>
          <p className="text-[#5f4448]">
            Mercator is the beginning of a new market structure. As the platform grows, insights
            will become a tradeable asset. Sellers will build reputation and brand. Buyers will
            have access to the world's best independent analysts without paying gatekeepers. The
            market for intelligence will be efficient, fair, and open.
          </p>
        </div>
      </div>
    </div>
  )
}
