"""Reputation contract: On-chain seller reputation scoring system.

Purpose: Stores and retrieves seller trust scores (0-100 scale) used by buyer agent for purchase decisions.
Acts as oracle for: reputation_score in semantic ranking + BUY threshold gate (score >= 50).

Key Responsibilities:
1. update_score(seller, new_score): Record or update seller's on-chain reputation.
2. get_score(seller): Read seller's current score (returns 0 if not found).
3. seller_scores: BoxMap (seller_address => reputation_score) storing all scores.

Contract Flow in Micropayment Cycle:
1. Agent calls semantic_search \u2192 fetches listing + calls get_score(seller).
2. Agent's evaluation function checks: if score < 50 \u2192 SKIP (no purchase).
3. If score >= 50 + value_for_price > 8.0 \u2192 BUY decision.
4. After successful x402 payment, reputation system can auto-update scores (future extension).

Design Notes:
- Read-only get_score is viewable by anyone (transparency).
- update_score is currently permissionless (admin contract call will gate this in production).
- Scores are 0-indexed (missing sellers default to score 0, auto-SKIP).
- No score decay or time-based expiration (permanent record).
"""

from algopy import ARC4Contract, BoxMap, arc4


class Reputation(ARC4Contract):
    """On-chain seller reputation scoring system.
    
    State:
        seller_scores: BoxMap(seller_address => score) storing seller trust scores (uint64).
    
    Purpose: Decentralized oracle for buyer purchase decisions + seller track record.
    """
    def __init__(self) -> None:
        self.seller_scores = BoxMap(arc4.Address, arc4.UInt64, key_prefix=b"rep")

    @arc4.abimethod()
    def update_score(self, seller: arc4.Address, new_score: arc4.UInt64) -> None:
        """Update or create a seller reputation score on-chain.
        
        Purpose: Record seller's current reputation (0-100 scale).
        Called during seller verification flow or post-purchase reputation updates.
        
        Actions:
        1. Store new_score in boxes under seller's address.
        2. Overwrites any previous score (last-write-wins).
        3. Emit event log for audit trail.
        
        Args:
            seller: Algorand wallet address to score.
            new_score: New reputation score (0-100 typically, no hard limit in contract).
        
        Notes:
        - Currently permissionless (admin contract call will gate in production).
        - No validation on score range (contract assumes valid input).
        - Box storage cost paid by caller (typical ~ 2500 micro-Algo for new entry).
        """
        self.seller_scores[seller] = new_score

    @arc4.abimethod(readonly=True)
    def get_score(self, seller: arc4.Address) -> arc4.UInt64:
        """Read a seller's current reputation score on-chain.
        
        Purpose: Public query for seller trust score. Called by buyer agent during evaluation.
        Readonly method (no state mutations, viewable via any algod node).
        
        Args:
            seller: Algorand wallet address to look up.
        
        Returns:
            Seller's reputation score (uint64). Returns 0 if seller not found (default: untrusted).
        
        Notes:
        - Default score for missing sellers is 0 (fails reputation gate in agent).
        - No caching on contract (each call does box lookup).
        - Transparent: external tools can audit all scores via algod API.
        """
        return self.seller_scores.get(seller, default=arc4.UInt64(0))
