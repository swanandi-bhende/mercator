"""Atomic group safety tests for Mercator."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, SimulateAtomicTransactionResponse
from algosdk.v2client import algod

from backend.utils.transaction_utils import (
    TransactionSimulationError,
    build_group_id,
    estimate_group_fee,
    execute_with_simulation,
    validate_atomic_group,
)


class _DummyTxn:
    def __init__(self, fee: int, gh: str = "same_gh", txid: str = "dummy") -> None:
        self.fee = fee
        self._gh = gh
        self._txid = txid
        self.sender = "SENDER"

    def get_txn_dict(self) -> dict:
        return {"gh": self._gh}

    def get_txid(self) -> str:
        return self._txid


@pytest.mark.integration
@pytest.mark.skip(reason="Requires funded TestNet wallets, app ids, and live contracts")
def test_payment_and_escrow_in_same_group() -> None:
    """Build and execute payment + escrow in one group, then verify same confirmed round."""
    # Live test scaffold intentionally skipped in CI/local by default.
    # It should:
    # 1) build ATC with payment at index 0 and escrow method call at index 1
    # 2) call execute_with_simulation
    # 3) query algod for tx info of both tx ids and assert same confirmed round
    assert True


@pytest.mark.integration
@pytest.mark.skip(reason="Requires contract pause controls and funded TestNet wallets")
def test_escrow_revert_reverts_payment() -> None:
    """When escrow leg reverts, payment leg must also not confirm."""
    # Live adversarial scaffold intentionally skipped unless full staging controls exist.
    assert True


@pytest.mark.asyncio
async def test_simulation_failure_blocks_execution() -> None:
    atc = Mock(spec=AtomicTransactionComposer)
    sim_result = Mock(spec=SimulateAtomicTransactionResponse)
    sim_result.failure_message = "fee_too_low"
    sim_result.failed_at = [1]
    sim_result.simulate_response = {}
    atc.simulate = Mock(return_value=sim_result)
    atc.execute = Mock(side_effect=AssertionError("execute should not be called"))

    algod_client = Mock(spec=algod.AlgodClient)

    with pytest.raises(TransactionSimulationError) as exc:
        await execute_with_simulation(atc, algod_client, "simulation_failure_case")

    assert "fee_too_low" in str(exc.value)
    assert atc.execute.call_count == 0


@pytest.mark.integration
@pytest.mark.skip(reason="Requires funded TestNet wallets, app ids, and USDC setup")
def test_subscription_payment_and_contract_call_atomic() -> None:
    """Wrong subscription amount should revert full group including payment."""
    # Live scaffold intentionally skipped in normal test runs.
    assert True


@pytest.mark.integration
@pytest.mark.skip(reason="Requires mockable on-chain reputation failure in staging")
def test_reputation_update_reverts_with_escrow() -> None:
    """If reputation update fails, seller payout and listing changes must not commit."""
    # Live scaffold intentionally skipped in normal test runs.
    assert True


def test_fee_estimate_is_sufficient() -> None:
    assert estimate_group_fee(1, 4) == 5000


def test_validate_atomic_group_catches_fee_too_low() -> None:
    txns = [_DummyTxn(fee=1000, txid="tx1"), _DummyTxn(fee=1000, txid="tx2")]
    signers = [Mock(), Mock()]
    valid, reason = validate_atomic_group(txns, signers, inner_tx_count=4)
    assert valid is False
    assert "fee" in reason.lower()


def test_build_group_id_stable() -> None:
    first = build_group_id(["a", "b"])
    second = build_group_id(["b", "a"])
    assert first == second
