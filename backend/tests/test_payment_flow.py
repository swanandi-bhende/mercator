import asyncio
import types
from types import SimpleNamespace
import pytest

from backend.tools import x402_payment as x402
from backend.utils.error_handler import PaymentError, AlgorandError, ErrorCode


class DummyAlgod:
    def __init__(self, sender_info=None, receiver_info=None, raise_on_account=False, send_raises=None):
        self._sender_info = sender_info or {}
        self._receiver_info = receiver_info or {}
        self._raise = raise_on_account
        self._send_raises = send_raises

    def account_info(self, address):
        if self._raise:
            raise TimeoutError("account info timeout")
        if address.endswith("SENDER"):
            return self._sender_info
        return self._receiver_info

    def suggested_params(self):
        return SimpleNamespace(first=1, last=1000, flat_fee=True, fee=1000)

    def send_transaction(self, signed):
        if self._send_raises:
            raise Exception(self._send_raises)
        return "TXID123"


@pytest.mark.asyncio
async def test_simulate_payment_insufficient_balance_maps_to_payment_error(monkeypatch):
    # Sender holds 10 units, we simulate payment of 100 -> should raise PaymentError(PAYMENT_INSUFFICIENT_BALANCE)
    sender_info = {"assets": [{"asset-id": x402.USDC_ASA_ID, "amount": 10}]}
    receiver_info = {"assets": []}
    dummy = DummyAlgod(sender_info=sender_info, receiver_info=receiver_info)
    algorand = SimpleNamespace(client=SimpleNamespace(algod=dummy))
    client = x402.X402Client(algorand=algorand)

    # Monkeypatch address validation and AssetTransferTxn to avoid SDK complexity
    monkeypatch.setattr(x402.encoding, "is_valid_address", lambda a: True)
    orig_asset = getattr(x402.transaction, "AssetTransferTxn", None)
    monkeypatch.setattr(x402.transaction, "AssetTransferTxn", lambda *a, **k: object())

    with pytest.raises(PaymentError) as exc:
        await client.simulate_payment(sender="ADDR_SENDER", receiver="ADDR_RECV", amount=100, asset_id=x402.USDC_ASA_ID)

    assert exc.value.code == ErrorCode.PAYMENT_INSUFFICIENT_BALANCE
    if orig_asset is not None:
        monkeypatch.setattr(x402.transaction, "AssetTransferTxn", orig_asset)


@pytest.mark.asyncio
async def test_simulate_payment_timeout_maps_to_algod_timeout(monkeypatch):
    dummy = DummyAlgod(raise_on_account=True)
    algorand = SimpleNamespace(client=SimpleNamespace(algod=dummy))
    client = x402.X402Client(algorand=algorand)

    # Patch address validation and AssetTransferTxn to avoid SDK requirements
    monkeypatch.setattr(x402.encoding, "is_valid_address", lambda a: True)
    orig_asset = getattr(x402.transaction, "AssetTransferTxn", None)
    monkeypatch.setattr(x402.transaction, "AssetTransferTxn", lambda *a, **k: object())

    with pytest.raises(AlgorandError) as exc:
        await client.simulate_payment(sender="ADDR_SENDER", receiver="ADDR_RECV", amount=1, asset_id=x402.USDC_ASA_ID)

    assert exc.value.code == ErrorCode.ALGOD_TIMEOUT
    if orig_asset is not None:
        monkeypatch.setattr(x402.transaction, "AssetTransferTxn", orig_asset)


@pytest.mark.asyncio
async def test_send_micropayment_insufficient_maps_to_payment_error(monkeypatch):
    # Replace PaymentTxn to a simple dummy with a sign method
    class DummyPaymentTxn:
        def __init__(self, sender, sp, receiver, amt):
            pass

        def sign(self, pk):
            return b"signed"

    # PaymentTxn is also imported as a top-level symbol in module; patch both
    monkeypatch.setattr(x402, "PaymentTxn", DummyPaymentTxn)
    monkeypatch.setattr(x402.transaction, "PaymentTxn", DummyPaymentTxn)

    dummy = DummyAlgod(send_raises="insufficient funds")
    algorand = SimpleNamespace(client=SimpleNamespace(algod=dummy))
    client = x402.X402Client(algorand=algorand)

    # Ensure key resolution returns a value so signing proceeds
    monkeypatch.setattr(client, "_resolve_private_key_for_sender", lambda sender: "PRIVKEY")

    with pytest.raises(PaymentError) as exc:
        await client.send_micropayment(sender="ADDR_SENDER", receiver="ADDR_RECV", amount=1, asset_id=0)

    assert exc.value.code == ErrorCode.PAYMENT_INSUFFICIENT_BALANCE
