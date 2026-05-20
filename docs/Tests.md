# Testing Guide

Comprehensive testing for Mercator covers unit tests, integration tests, smart contract tests, and end-to-end payment flows. This document explains how to run tests and what they cover.

## Quick Start

```bash
# Run all tests
source .venv/bin/activate
PYTHONPATH=. pytest backend/tests/ -v

# Run specific test file
PYTHONPATH=. pytest backend/tests/test_payment_flow.py -v

# Run with output
PYTHONPATH=. pytest backend/tests/ -v -s

# Stop on first failure
PYTHONPATH=. pytest backend/tests/ -x
```

---

## Test Suite Overview

Mercator includes ~15 pytest test files covering:

| Category | File | Coverage |
|----------|------|----------|
| **Core Payment** | `test_payment_flow.py` | End-to-end purchase, escrow, reputation |
| **Smart Contracts** | `test_insight_listing.py` | Listing creation/retrieval |
| | `test_escrow.py` | Atomic escrow execution |
| | `test_reputation.py` | Reputation updates |
| **Wallet** | `test_wallet_integration.py` | Address validation, signing |
| **Agent** | `test_agent_evaluation.py` | Semantic search, decision-making |
| **API** | `test_api_endpoints.py` | HTTP request/response validation |
| **Micropayments** | `test_micropayment_cycle.py` | Complete x402 flow |
| **Error Handling** | `test_error_scenarios.py` | Failure cases, retries |
| **Regression** | `test_critical_path_coverage.py` | Edge cases, replay attacks |

---

## Unit Tests

### Wallet Tests

**File**: `test_wallet_integration.py`

Tests wallet address validation and signing:

```python
def test_valid_algorand_address():
    """Valid addresses pass checksums"""
    assert is_valid_address("IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4")

def test_invalid_address_checksum():
    """Invalid checksums rejected"""
    assert not is_valid_address("IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVMXX")

def test_address_type_validation():
    """Non-string addresses rejected"""
    assert not is_valid_address(None)
    assert not is_valid_address(123456)
```

**Run**: `pytest backend/tests/test_wallet_integration.py -v`

**Expected**: All address validators pass with valid addresses, fail with invalid

---

### Smart Contract Tests

#### InsightListing Contract

**File**: `test_insight_listing.py`

```python
def test_create_listing():
    """Seller can create insight listing"""
    listing_id = contract.create_listing(
        seller="SELLER_ADDR",
        price=500000,  # 0.5 USDC
        cid="QmABC123",
        asa_id=10458941
    )
    assert listing_id > 0

def test_get_listing():
    """Retrieve listing metadata"""
    listing = contract.get_listing(listing_id)
    assert listing.price == 500000
    assert listing.seller == "SELLER_ADDR"

def test_list_all_active_listings():
    """Search returns active listings only"""
    active = contract.get_active_listings()
    assert len(active) > 0
    assert all(l.active == True for l in active)
```

**Run**: `pytest backend/tests/test_insight_listing.py -v`

#### Escrow Contract

**File**: `test_escrow.py`

```python
def test_atomic_escrow_release():
    """Payment and release happen atomically"""
    group = [
        asa_transfer_txn,
        escrow_release_txn,
        reputation_update_txn
    ]
    signed = sign_group(group)
    result = algod.send(signed)
    
    assert result.confirmed
    # Verify all 3 transactions in group
    block = algod.get_block_txns(result.group_id)
    assert len(block.transactions) == 3

def test_escrow_no_partial_releases():
    """If any txn fails, entire group fails"""
    invalid_group = [
        valid_transfer,
        invalid_escrow,  # Will fail
        reputation_update
    ]
    
    result = algod.send(sign_group(invalid_group))
    assert result.status == "FAILED"
    assert buyer_balance_unchanged()
```

**Run**: `pytest backend/tests/test_escrow.py -v`

#### Reputation Contract

**File**: `test_reputation.py`

```python
def test_initial_reputation():
    """New sellers start at 50"""
    rep = contract.get_reputation("NEW_SELLER")
    assert rep == 50

def test_reputation_increment():
    """Successful purchase increments +10"""
    initial = contract.get_reputation(seller)
    contract.update_reputation(seller, +10)
    final = contract.get_reputation(seller)
    assert final == initial + 10

def test_reputation_decrement_on_dispute():
    """Dispute decrements -10"""
    contract.update_reputation(seller, -10)
    assert contract.get_reputation(seller) <= 40

def test_reputation_max_cap():
    """Reputation capped at 100"""
    contract.update_reputation(seller, +1000)
    assert contract.get_reputation(seller) <= 100
```

**Run**: `pytest backend/tests/test_reputation.py -v`

---

## Integration Tests

### API Tests

**File**: `test_api_endpoints.py`

```python
def test_list_insight_endpoint():
    """POST /list creates listing"""
    response = client.post("/list", json={
        "insight_text": "NIFTY...",
        "price": 0.5,
        "seller_wallet": "SELLER_ADDR"
    })
    assert response.status_code == 200
    assert "transaction_id" in response.json()

def test_discover_insights_endpoint():
    """GET /discover returns ranked results"""
    response = client.get("/discover", params={
        "query": "NIFTY trading setup",
        "buyer_address": "BUYER_ADDR"
    })
    assert response.status_code == 200
    results = response.json()["insights"]
    assert len(results) > 0
    # Check ranking (highest relevance first)
    assert results[0]["relevance"] >= results[1]["relevance"]

def test_checkout_endpoint():
    """POST /checkout executes payment"""
    response = client.post("/checkout", json={
        "listing_id": 1,
        "buyer_wallet": "BUYER_ADDR",
        "user_approval": "approve"
    })
    assert response.status_code == 200
    assert "transaction_id" in response.json()
```

**Run**: `pytest backend/tests/test_api_endpoints.py -v`

### Agent Tests

**File**: `test_agent_evaluation.py`

```python
def test_semantic_search():
    """Agent finds relevant insights"""
    results = search("NIFTY resistance levels")
    assert len(results) > 0
    # All results mention NIFTY or resistance
    assert all("NIFTY" in r.text or "resistance" in r.text for r in results)

def test_evaluation_logic():
    """Agent evaluates relevance + reputation + price"""
    insight = Insight(
        text="NIFTY at 24,500",
        price=0.5,
        seller_reputation=60
    )
    evaluation = agent.evaluate(insight, query="NIFTY analysis")
    assert evaluation.relevance > 80
    assert evaluation.value_for_price > 8.0
    assert evaluation.decision == "BUY"

def test_agent_skips_low_reputation():
    """Agent filters sellers with rep < 50"""
    low_rep_insight = Insight(
        text="Trade setup",
        price=0.1,
        seller_reputation=30  # Below minimum
    )
    evaluation = agent.evaluate(low_rep_insight)
    assert evaluation.decision == "SKIP"

def test_agent_respects_approval_gate():
    """Agent only pays when user approves"""
    result = agent.process_query(
        query="Buy best insight",
        user_approval_input=""  # Empty
    )
    assert result["status"] == "BUY_PENDING_APPROVAL"
    
    # With approval
    result = agent.process_query(
        query="Buy best insight",
        user_approval_input="approve"
    )
    assert result["status"] == "PAYMENT_SUCCESS"
```

**Run**: `pytest backend/tests/test_agent_evaluation.py -v`

---

## Critical Path Coverage

### Test File: `test_critical_path_coverage.py`

Tests edge cases and failure scenarios:

#### Insufficient Balance

```python
def test_insufficient_usdc_balance():
    """Payment rejected when buyer lacks USDC"""
    buyer_balance = 0.1  # Only 0.1 USDC
    payment_amount = 0.5  # Want to pay 0.5
    
    result = execute_payment(...)
    assert result["status"] == "PAYMENT_FAILED"
    assert "insufficient balance" in result["error"]
```

#### Address Validation

```python
def test_invalid_seller_address():
    """Payment rejected with bad seller address"""
    result = execute_payment(
        seller_address="INVALID_ADDRESS",
        ...
    )
    assert result["status"] == "VALIDATION_FAILED"
    assert "invalid address" in result["error"]
```

#### Replay Attack Prevention

```python
def test_replay_attack_prevention():
    """Same payment can't be replayed"""
    payment1 = execute_payment(...)
    tx_id_1 = payment1["transaction_id"]
    
    # Try same payment again
    payment2 = execute_payment(...)
    tx_id_2 = payment2["transaction_id"]
    
    # Different transactions created
    assert tx_id_1 != tx_id_2
```

#### Network Failure Recovery

```python
def test_retry_on_network_timeout():
    """Failed transactions retry with backoff"""
    with mock_network_timeout():
        result = execute_payment(...)
    
    # Should succeed after retries
    assert result["status"] == "CONFIRMED"
    assert result["retry_count"] >= 1
```

**Run**: `pytest backend/tests/test_critical_path_coverage.py -v`

---

## End-to-End Tests

### Complete Payment Flow

**File**: `test_payment_flow.py`

```python
def test_complete_purchase_flow():
    """Full flow: List → Search → Buy → Confirm"""
    
    # Step 1: Seller lists insight
    listing = create_listing(
        seller=seller_wallet,
        text="NIFTY trading setup",
        price=0.5
    )
    assert listing.id > 0
    
    # Step 2: Buyer searches
    results = search_insights("NIFTY")
    assert any(r.id == listing.id for r in results)
    
    # Step 3: Agent evaluates and buys
    payment = execute_agent_purchase(
        query="Buy best NIFTY insight",
        buyer=buyer_wallet,
        approval="approve"
    )
    assert payment["status"] == "SUCCESS"
    
    # Step 4: Verify on-chain effects
    assert get_usdc_balance(seller_wallet) > 0
    assert get_reputation(seller_wallet) == 60  # 50 + 10
    assert get_ipfs_content(listing.cid) is not None

def test_purchase_with_reputation_update():
    """Reputation increases after each purchase"""
    initial_rep = get_reputation(seller)
    
    execute_payment(seller, listing_id)
    new_rep = get_reputation(seller)
    
    assert new_rep == initial_rep + 10

def test_multiple_purchases_same_seller():
    """Multiple buyers can buy from same seller"""
    for buyer in [buyer1, buyer2, buyer3]:
        execute_payment(
            seller=seller,
            buyer=buyer,
            listing_id=listing
        )
    
    final_rep = get_reputation(seller)
    assert final_rep == 50 + (10 * 3)  # +10 per purchase
```

**Run**: `pytest backend/tests/test_payment_flow.py -v`

---

## Test Coverage Report

Generate coverage report:

```bash
pip install pytest-cov

pytest backend/tests/ --cov=backend --cov-report=html

# Opens coverage/index.html with detailed report
```

**Expected Coverage**:
- Backend code: > 80%
- Smart contract logic: > 90%
- API endpoints: > 85%
- Error handling: > 75%

---

## Performance/Load Tests

### Benchmark Payment Throughput

```python
def test_payment_throughput():
    """Measure transactions per second"""
    start_time = time()
    
    for i in range(100):
        execute_payment(...)
    
    elapsed = time() - start_time
    tps = 100 / elapsed
    
    assert tps > 5  # At least 5 payments/sec
    print(f"Throughput: {tps:.1f} payments/sec")
```

**Run**: `pytest backend/tests/test_performance.py -v -s`

---

## Manual Testing Checklist

Before deployment, manually test:

- [ ] **Listing Creation**: Create 3 different insights with varied prices
- [ ] **Search Ranking**: Verify results ranked by relevance + reputation
- [ ] **Payment Flow**: Complete full purchase with real TestNet USDC
- [ ] **Receipt Display**: Verify transaction ID, explorer link, content unlock
- [ ] **Error Handling**: Try invalid wallet, insufficient balance, network timeout
- [ ] **Multi-Agent**: Run 2+ agents concurrently, verify no conflicts
- [ ] **Reputation**: Verify reputation increases +10 after purchase
- [ ] **Frontend**: Test on Chrome, Firefox, Safari, mobile browsers
- [ ] **Mobile**: Full payment flow on phone wallet (Pera)

---

## Continuous Integration

GitHub Actions automatically runs tests on each push:

**.github/workflows/test.yml**:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.12
      - run: pip install -r backend/requirements.txt
      - run: PYTHONPATH=. pytest backend/tests/ -v
      - run: pytest --cov=backend
```

---

## Troubleshooting Test Failures

### Import Errors

```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=$(pwd)
pytest backend/tests/

# Or run from backend directory
cd backend && python -m pytest tests/
```

### Wallet/Address Errors

```python
# Use valid TestNet address format
seller_address = "IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4"

# Never use invalid checksums
# Always validate with: is_valid_address(addr)
```

### Mock vs Real Transactions

Tests use **mock Algorand responses** (don't require TestNet):

```python
# Mock transaction submission
with mock.patch('algod.send_transaction') as mock_send:
    mock_send.return_value = "MOCK_TX_ID"
    result = execute_payment(...)
```

For **real TestNet testing**, set env var:

```bash
TEST_REAL_TRANSACTIONS=true pytest backend/tests/
```

---

## Next Steps

- **Add your tests**: Write tests for new features
- **Improve coverage**: Aim for >90% code coverage
- **Monitor regressions**: CI ensures no broken tests
- **Performance**: Run load tests before scaling

See [Deploy.md](Deploy.md) for CI/CD pipeline setup.

- **Expected**: `ValueError` with clear message

#### test_invalid_price_format
- **Purpose**: Verify price validation and rejection of bad formats
- **Tested**: negative prices, non-numeric input, NaN values
- **Expected**: Validation error before on-chain submission

#### test_malformed_cid
- **Purpose**: Verify CID format validation before IPFS lookup
- **Tested**: CID not starting with "Qm", invalid hash encoding
- **Expected**: `LISTING_STORE_ERROR` error

#### test_invalid_wallet_address
- **Purpose**: Verify wallet address format validation
- **Tested**: Non-Algorand addresses, wrong length, invalid characters
- **Expected**: `INVALID_ADDRESS` error

#### test_atomic_group_failure_handling
- **Purpose**: Verify system behavior when atomic group submission fails
- **Expected**: Graceful error message, no partial state changes

#### test_env_variable_fallbacks
- **Purpose**: Verify fallback paths when optional env vars missing
- **Tested**: OPERATOR_API_KEY missing, GEMINI_API_KEY missing
- **Expected**: System works with limited functionality

## Running Specific Test Scenarios

### Test a Complete Purchase Flow

```bash
# Run the full purchase scenario
pytest backend/tests/test_micropayment_cycle.py::test_purchase_and_payment_execution -v -s
```

### Test Edge Cases Only

```bash
# Run all edge-case tests
pytest backend/tests/test_critical_path_coverage.py -v
```

### Test With Environment Simulation

```bash
# Run with specific environment configuration
USDC_ASA_ID=10458941 pytest backend/tests/test_micropayment_cycle.py -v
```

## Environment Variables for Testing

When running tests, ensure these variables are set in your `.env.testnet`:

| Variable | Test Value | Purpose |
|----------|-----------|---------|
| `ALGOD_URL` | TestNet RPC | Smart contract operations |
| `INDEXER_URL` | TestNet Indexer | Transaction lookups |
| `INSIGHT_LISTING_APP_ID` | Deployed app ID | Listing operations |
| `ESCROW_APP_ID` | Deployed app ID | Payment escrow |
| `REPUTATION_APP_ID` | Deployed app ID | Reputation tracking |
| `USDC_ASA_ID` | 10458941 | USDC token |
| `USDC_DECIMALS` | 6 | USDC precision |
| `DEPLOYER_MNEMONIC` | TestNet mnemonic | Account signing |
| `BUYER_MNEMONIC` | TestNet mnemonic | Buyer account |

## Test Output Interpretation

### Successful Test Run

```
backend/tests/test_micropayment_cycle.py::test_list_insight_and_retrieve_cid PASSED  (0.45s)
backend/tests/test_micropayment_cycle.py::test_purchase_and_payment_execution PASSED  (1.23s)
backend/tests/test_micropayment_cycle.py::test_reputation_update_after_purchase PASSED  (0.87s)

================================ 3 passed in 2.55s =================================
```

### Failed Test Example

```
backend/tests/test_critical_path_coverage.py::test_missing_deployer_mnemonic FAILED

AssertionError: Expected ValueError but got None
```

**Action**: Check `.env.testnet` has `DEPLOYER_MNEMONIC` set. Run setup verification from [SETUP.md](SETUP.md).

## Common Test Failures and Solutions

### "Connection refused" Error

```
ConnectionError: cannot connect to https://testnet-api.algonode.cloud
```

**Solution**: 
- Verify internet connection
- Check `ALGOD_URL` is correct in `.env.testnet`
- Try alternative node: `https://testnet-api.algonode.cloud` or `https://api.testnet.algoexplorer.io`

### "App ID not found" Error

```
IndexError: Application index not found in account state
```

**Solution**:
- Verify contracts have been deployed (see [SETUP.md](SETUP.md) deployment section)
- Confirm `INSIGHT_LISTING_APP_ID`, `ESCROW_APP_ID`, `REPUTATION_APP_ID` are set in `.env.testnet`
- Verify app IDs match deployed contracts

### "Insufficient balance" Error

```
Transaction simulation failed: insufficient balance for this account
```

**Solution**:
- Fund buyer and deployer accounts via Algorand TestNet Dispenser
- Ensure accounts have at least 10 Algo each
- Wait 1-2 minutes for transaction confirmation on TestNet

### "USDC Asset Not Found" Error

```
AssetNotFoundError: Asset with index 10458941 not found
```

**Solution**:
- Verify you're on TestNet: check `NETWORK=testnet` in `.env.testnet`
- Ensure buyer account has opted-in to USDC asset (ASA 10458941)
- Run opt-in transaction: contact network admin or use asset-opt-in tool

## CodeQL and Static Analysis

### Run Python Code Quality Checks

```bash
# Use pylint for code quality
pip install pylint
pylint backend/tools/x402_payment.py

# Use flake8 for style issues
pip install flake8
flake8 backend/

# Use mypy for type checking
pip install mypy
mypy backend/tools/ --ignore-missing-imports
```

## Performance Testing

### Measure Test Execution Time

```bash
# Run tests with timing information
pytest backend/tests/ -v --durations=10
```

Expected performance (on standard machine):
- **Unit tests**: < 100ms each
- **Integration tests**: < 2 seconds each
- **Full suite**: < 1 minute

## Continuous Integration

Tests are designed to run in CI/CD pipelines. For GitHub Actions:

```yaml
- name: Run tests
  run: |
    source .venv/bin/activate
    pytest backend/tests/test_micropayment_cycle.py -v --tb=short
```

## Test Coverage

To measure test coverage:

```bash
pip install pytest-cov
pytest backend/tests/ --cov=backend --cov-report=html
```

Coverage report will be generated in `htmlcov/index.html`.

## Debugging Failed Tests

### Enable Verbose Logging

```bash
# Run with maximum verbosity and print statements
pytest backend/tests/test_micropayment_cycle.py -vv -s --log-cli-level=DEBUG
```

### Use Python Debugger

```python
# Add this to test file where you want to pause
import pdb; pdb.set_trace()

# Run test, it will pause at the breakpoint
pytest backend/tests/test_micropayment_cycle.py -s
```

### Inspect Test Data

```bash
# Print detailed transaction data
pytest backend/tests/test_micropayment_cycle.py -s -k "test_purchase_and_payment_execution"
```

## Next Steps

- See [DEMO.md](DEMO.md) to run the interactive user interface
- See [COMPONENTS.md](COMPONENTS.md) for proof artifacts and transaction examples
- See [ALGORAND.md](ALGORAND.md) for technical contract details
