# Testing Guide

This document covers all aspects of testing the Mercator system, from unit tests to end-to-end scenarios.

## Test Suite Overview

Mercator includes two primary test suites:

1. **Micropayment Cycle Tests** (`test_micropayment_cycle.py`): Core regression tests covering the full purchase flow
2. **Critical Path Coverage Tests** (`test_critical_path_coverage.py`): Edge cases and error handling

## Quick Start

### Run All Tests

```bash
source .venv/bin/activate
pytest backend/tests/ -v
```

### Run Specific Test Suite

```bash
# Run only micropayment cycle tests
pytest backend/tests/test_micropayment_cycle.py -v

# Run only critical path coverage tests
pytest backend/tests/test_critical_path_coverage.py -v
```

### Run Tests with Output

```bash
# Show print statements and detailed output
pytest backend/tests/ -v -s

# Stop on first failure
pytest backend/tests/ -x

# Run only tests matching a pattern
pytest backend/tests/ -k "test_payment" -v
```

## Test Categories

### 1. Micropayment Cycle Tests

These tests verify the core transaction flow from listing to purchase to delivery.

#### test_list_insight_and_retrieve_cid
- **Purpose**: Verify listing creation and IPFS storage
- **Flow**: 
  1. Create new insight listing
  2. Verify listing metadata stored on InsightListing contract
  3. Verify CID uploaded to IPFS (Pinata)
  4. Verify CID retrieval works

#### test_purchase_and_payment_execution
- **Purpose**: Verify x402 payment execution with atomic grouping
- **Flow**:
  1. Initiate payment for listed insight
  2. Verify payment transaction submitted in atomic group with escrow redeem
  3. Verify USDC transfer confirmed on-chain
  4. Verify escrow release confirmed on-chain

#### test_reputation_update_after_purchase
- **Purpose**: Verify seller reputation incremented after successful purchase
- **Flow**:
  1. Record seller reputation before purchase
  2. Complete purchase transaction
  3. Record seller reputation after purchase
  4. Verify reputation increased by +10

#### test_payment_decline_exceeding_limit
- **Purpose**: Verify micropayment ceiling is enforced
- **Flow**:
  1. Request payment exceeding `MAX_MICROPAYMENT_USDC` (5.0 USDC)
  2. Verify payment rejected with `PAYMENT_LIMIT_EXCEEDED` error
  3. Verify no on-chain state changes

#### test_low_reputation_skip
- **Purpose**: Verify agent skips listings with low-reputation sellers
- **Flow**:
  1. Create listing with owner having very low reputation
  2. Run agent discovery and evaluation
  3. Verify agent decision is SKIP with appropriate message

#### test_insufficient_balance_rejection
- **Purpose**: Verify payment fails gracefully when buyer lacks funds
- **Flow**:
  1. Attempt payment with insufficient USDC balance
  2. Verify payment rejected with `PAYMENT_EXECUTION_FAILED`
  3. Verify error message indicates wallet balance issue

### 2. Critical Path Coverage Tests

These tests focus on error handling, edge cases, and security validations.

#### test_missing_deployer_mnemonic
- **Purpose**: Verify graceful failure when deployer credentials missing
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
