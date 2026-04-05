import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

export default function HomePage() {
  const navigate = useNavigate()
  const { setCurrentJourney } = useAppContext()

  const handleSellerMode = () => {
    setCurrentJourney('seller')
    navigate('/sell')
  }

  const handleBuyerMode = () => {
    setCurrentJourney('buyer')
    navigate('/discover')
  }

  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="home-hero-glow home-hero-glow--left" aria-hidden="true" />
        <div className="home-hero-glow home-hero-glow--right" aria-hidden="true" />

        <div className="home-wrap">
          <p className="home-kicker">AI-Powered Insight Exchange</p>
          <h1 className="home-title">
            Trade market intelligence with on-chain proof and buyer-side AI evaluation.
          </h1>
          <p className="home-subtitle">
            Mercator is a two-sided marketplace for financial insights. Sellers publish analysis,
            buyers discover and evaluate it, and every critical step is verified through Algorand,
            IPFS, escrow logic, and reputation checks.
          </p>

          <div className="home-cta-row">
            <button type="button" className="home-btn home-btn--primary" onClick={handleSellerMode}>
              Sell an Insight
            </button>
            <button type="button" className="home-btn home-btn--secondary" onClick={handleBuyerMode}>
              Discover Insights
            </button>
          </div>

          <div className="home-answer-grid" aria-label="Mercator quick answers">
            <article className="home-answer-card">
              <h2>What it is</h2>
              <p>A working marketplace for paid market insights, not a static dashboard.</p>
            </article>
            <article className="home-answer-card">
              <h2>Why it matters</h2>
              <p>AI-assisted evaluation plus transparent settlement reduces trust friction.</p>
            </article>
            <article className="home-answer-card">
              <h2>Where to go next</h2>
              <p>Choose seller mode to publish insights or buyer mode to evaluate and purchase.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="home-strip">
        <div className="home-wrap">
          <ul className="home-strip-grid">
            <li>
              <strong>Live TestNet Proof</strong>
              <span>Transactions verifiable on explorer with immediate TX links.</span>
            </li>
            <li>
              <strong>IPFS Storage</strong>
              <span>Insight payloads pinned with content-addressed retrieval.</span>
            </li>
            <li>
              <strong>Escrow Release</strong>
              <span>Payment flow maps to stateful contract release checkpoints.</span>
            </li>
            <li>
              <strong>Reputation Filtering</strong>
              <span>Low-reputation sellers can be skipped by policy before payment.</span>
            </li>
            <li>
              <strong>x402 Payments</strong>
              <span>Programmatic approval model with explicit buyer confirmation.</span>
            </li>
          </ul>
        </div>
      </section>

      <section className="home-workflow">
        <div className="home-wrap">
          <div className="home-workflow-head">
            <p className="home-kicker">Featured Workflow</p>
            <h2>From seller insight to buyer unlock, in six clear steps</h2>
            <p>
              Mercator keeps the full loop legible so users understand what happens, why it
              happens, and what proof is available at each stage.
            </p>
          </div>

          <div className="home-bento-grid">
            <article className="home-bento home-bento--story">
              <h3>Process Story</h3>
              <ol className="home-process-list">
                <li>
                  <span>01</span>
                  <p>List insight with wallet and price metadata.</p>
                </li>
                <li>
                  <span>02</span>
                  <p>Review seller reputation and trust policy checks.</p>
                </li>
                <li>
                  <span>03</span>
                  <p>Search demand using query relevance scoring.</p>
                </li>
                <li>
                  <span>04</span>
                  <p>Approve x402 payment with visible status flow.</p>
                </li>
                <li>
                  <span>05</span>
                  <p>Release escrow through contract settlement state.</p>
                </li>
                <li>
                  <span>06</span>
                  <p>Unlock content with receipt and explorer proof.</p>
                </li>
              </ol>
            </article>

            <article className="home-bento home-bento--activity">
              <h3>Live Activity Panel</h3>
              <p className="home-bento-copy">Recent confirmations from listing and purchase flows.</p>
              <ul className="home-live-list">
                <li>
                  <div>
                    <strong>Listing Confirmed</strong>
                    <span>Insight #ML-204 · status: confirmed</span>
                  </div>
                  <a href="https://explorer.perawallet.app/tx/4SWT4P6VQ6A2B6PC4RGYQG7R/" target="_blank" rel="noreferrer">TX 4SWT...G7R</a>
                </li>
                <li>
                  <div>
                    <strong>Purchase Confirmed</strong>
                    <span>Buyer unlock complete · escrow released</span>
                  </div>
                  <a href="https://explorer.perawallet.app/tx/B8R7S3Q1M6J9N4C2X5T1Z8L0/" target="_blank" rel="noreferrer">TX B8R7...8L0</a>
                </li>
                <li>
                  <div>
                    <strong>Reputation Filter Applied</strong>
                    <span>Low-score seller skipped before payment</span>
                  </div>
                  <em>policy event</em>
                </li>
              </ul>
            </article>
          </div>

          <div className="home-role-grid">
            <article className="home-role-card">
              <p className="home-role-kicker">Seller Journey</p>
              <h3>You publish premium insight.</h3>
              <ul>
                <li><strong>You do:</strong> write insight, set price, confirm wallet.</li>
                <li><strong>Backend does:</strong> upload to IPFS, mint listing state, post tx.</li>
                <li><strong>You get proof:</strong> transaction ID, explorer link, listing/CID references.</li>
              </ul>
              <button type="button" onClick={handleSellerMode} className="home-inline-action">Go to Seller Console</button>
            </article>

            <article className="home-role-card">
              <p className="home-role-kicker">Buyer Journey</p>
              <h3>You evaluate before you pay.</h3>
              <ul>
                <li><strong>You do:</strong> search query, review recommendation, approve payment.</li>
                <li><strong>Backend does:</strong> relevance score, reputation filter, escrow-aware settlement.</li>
                <li><strong>You get proof:</strong> confirmation status, tx receipt, unlocked insight content.</li>
              </ul>
              <button type="button" onClick={handleBuyerMode} className="home-inline-action">Go to Discovery</button>
            </article>
          </div>
        </div>
      </section>

      <footer className="home-footer">
        <div className="home-wrap home-footer-grid">
          <section>
            <p className="home-kicker">Start Here</p>
            <h3>Mercator remains the stable entry state.</h3>
            <p>
              Choose your side of the marketplace and continue the same trust story across every route.
            </p>
            <div className="home-footer-actions">
              <button type="button" className="home-btn home-btn--primary" onClick={handleSellerMode}>Sell an Insight</button>
              <button type="button" className="home-btn home-btn--secondary" onClick={handleBuyerMode}>Discover Insights</button>
            </div>
          </section>

          <nav className="home-footer-links" aria-label="Footer navigation">
            <a href="/sell">Seller Route</a>
            <a href="/discover">Buyer Route</a>
            <a href="/trust">Trust & Reputation</a>
            <a href="/activity">Activity & Proof</a>
            <a href="/operations">Operations</a>
            <a href="/about">About Mercator</a>
          </nav>
        </div>
      </footer>
    </div>
  )
}
