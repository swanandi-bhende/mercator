# Mercator Security Framework

## 1. Threat Model
- **Platform Risks**: Contract exploits, logic bugs in Escrow.
- **User Risks**: Private key compromise, phishing.
- **System Risks**: IPFS availability, Algorand network downtime.
- **Economic Risks**: Reputation manipulation, Sybil attacks on listings.

## 2. Wallet & Secret Security
- **Backend**: Credentials (e.g., Deployer Mnemonics) must never be hardcoded. Use environment variables and secret management services (AWS Secrets Manager, Vault).
- **Frontend**: Recommend Pera Wallet or MyAlgo; minimize local storage of sensitive data.

## 3. Smart Contract Safety
- **TEAL Logic**: Use of `Assert` for all critical state transitions.
- **Reentrant Guard**: Explicit check on transaction types and sequence.
- **Ownership**: Clear separation between Admin/Treasury and User permissions.
- **Balance Checks**: Ensure the Escrow contract never holds more OR less than the intended funds.

## 4. API & Integration Validation
- **Input Sanitization**: All inputs to the backend (FastAPI) are validated using Pydantic models.
- **Rate Limiting**: Implementation of Redis-based rate limiting to prevent DoS on API endpoints.
- **Signature Validation**: Verifying transaction signatures before processing off-chain actions.

## 5. Escrow Protections
- **Timelocks**: Mandatory dispute window before funds can be withdrawn by a seller if the buyer doesn't confirm manually.
- **Multi-sig Potential**: Future integration of multi-sig for high-value escrow resolution.

## 6. Reputation Integrity
- **Non-Transferable**: Reputation scores are linked to the account address and cannot be traded.
- **Transaction-Linked**: Scores can only be updated if a valid Escrow transaction ID is provided.

## 7. Edge Case Testing
- **Insufficient Funds**: Verified handling of accounts with low ALGO/Asset balances.
- **Opt-in Status**: Checking if participants are opted into necessary Assets/Apps before transactions.
- **Double Spending**: Prevention through Algorand's native transaction uniqueness.

## 8. Transaction Validation
- **Group Transactions**: Usage of Atomic Transfers to ensure all parts of a trade (payment, escrow, listing update) succeed or fail together.

## 9. Failure Handling
- **Graceful Degradation**: If an external service (like the IPFS gateway) is down, the system should still allow basic querying of on-chain data.
- **Error Codes**: Standardization of error codes for easier debugging and user feedback.

## 10. Security Audit Checklist
- [ ] Logic coverage: 100%
- [ ] Branch coverage: 90%+
- [ ] Static analysis: Ran with `Tealview` or similar tools.
- [ ] Formal Verification (Future): Exploring Reach or similar languages for verification.

## 11. Known Limitations
- Current version relies on platform-side health checkers for IPFS validity.
- Reputation system is susceptible to self-trading (farming) at a cost (transaction fees).

## 12. Future Improvements
- **ZKP Privacy**: Using Zero-Knowledge Proofs for private service delivery verification.
- **Decentralized Disputes**: Integration with Kleros or a similar DAO-based arbitration system.
