"""Tests for two-phase IPFS listing preparation with simulation safety.

Purpose: Verify that IPFS two-phase approach prevents orphaned pins and
ensures consistency between on-chain and off-chain state.

Critical Tests:
- test_ipfs_upload_success_then_simulate: Verify happy path
- test_simulation_failure_triggers_unpin: Prove cleanup happens on failure
- test_orphan_prevention: Ensure no orphaned pins from failed simulations
- test_preparation_log_tracks_all_attempts: Verify audit trail
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from uuid import uuid4

from backend.utils.ipfs import (
    PreparedListing,
    create_listing_prepared,
    IPFSUploadError,
    ListingStoreError,
    store_cid_in_listing,
)
from backend.utils.db import (
    initialise_listing_preparation_schema,
    log_listing_preparation_start,
    log_listing_simulation_failure,
    log_listing_execution_result,
    get_db_path,
)


class TestPreparedListingDataclass:
    """Tests for PreparedListing dataclass."""
    
    def test_prepared_listing_success_state(self):
        """PreparedListing can represent successful preparation."""
        result = PreparedListing(
            preparation_id="prep-12345",
            cid="QmTestCID",
            listing_id=42,
            asa_id=123456,
            tx_id="TXID123",
            simulation_passed=True,
            execution_succeeded=True,
        )
        
        assert result.preparation_id == "prep-12345"
        assert result.cid == "QmTestCID"
        assert result.listing_id == 42
        assert result.asa_id == 123456
        assert result.tx_id == "TXID123"
        assert result.simulation_passed
        assert result.execution_succeeded
        assert result.error_message == ""
    
    def test_prepared_listing_simulation_failure(self):
        """PreparedListing can represent simulation failure with cleanup."""
        result = PreparedListing(
            preparation_id="prep-12345",
            cid="QmTestCID",
            simulation_passed=False,
            execution_succeeded=False,
            error_message="Simulation failed: agent not registered",
        )
        
        assert result.preparation_id == "prep-12345"
        assert result.cid == "QmTestCID"
        assert result.listing_id == 0  # Not set on failure
        assert not result.simulation_passed
        assert not result.execution_succeeded
        assert "agent not registered" in result.error_message
    
    def test_prepared_listing_execution_failure(self):
        """PreparedListing can represent execution failure (simulation passed)."""
        result = PreparedListing(
            preparation_id="prep-12345",
            cid="QmTestCID",
            simulation_passed=True,
            execution_succeeded=False,
            error_message="Network timeout during execution",
        )
        
        assert result.simulation_passed
        assert not result.execution_succeeded
        assert "Network timeout" in result.error_message


class TestListingPreparationDatabase:
    """Tests for listing_preparation_log table and logging functions."""
    
    def test_initialise_listing_preparation_schema(self):
        """Schema initializes successfully with correct columns."""
        initialise_listing_preparation_schema()
        
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Query the table schema
        cursor = conn.execute(
            "PRAGMA table_info(listing_preparation_log)"
        )
        columns = {row['name']: row['type'] for row in cursor.fetchall()}
        
        # Verify all required columns exist
        assert 'preparation_id' in columns
        assert 'seller_wallet' in columns
        assert 'cid_pinned' in columns
        assert 'simulation_success' in columns
        assert 'execution_success' in columns
        assert 'simulation_error' in columns
        assert 'execution_error' in columns
        assert 'execution_tx_id' in columns
        assert 'created_at' in columns
        
        conn.close()
    
    def test_log_listing_preparation_start(self):
        """Successfully logs preparation start with CID."""
        initialise_listing_preparation_schema()
        
        prep_id = str(uuid4())
        seller = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        cid = "QmTestCID123"
        
        log_listing_preparation_start(prep_id, seller, cid)
        
        # Verify the log entry was created
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute(
            "SELECT * FROM listing_preparation_log WHERE preparation_id = ?",
            (prep_id,)
        ).fetchone()
        
        assert row is not None
        assert row['preparation_id'] == prep_id
        assert row['seller_wallet'] == seller
        assert row['cid_pinned'] == cid
        assert row['simulation_success'] == 0  # Default false
        assert row['execution_success'] == 0  # Default false
        
        conn.close()
    
    def test_log_listing_simulation_failure(self):
        """Successfully logs simulation failure."""
        initialise_listing_preparation_schema()
        
        prep_id = str(uuid4())
        seller = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        cid = "QmTestCID123"
        error_msg = "Simulation failed: agent not registered"
        
        # First log the start
        log_listing_preparation_start(prep_id, seller, cid)
        
        # Then log the failure
        log_listing_simulation_failure(prep_id, error_msg)
        
        # Verify the update
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute(
            "SELECT * FROM listing_preparation_log WHERE preparation_id = ?",
            (prep_id,)
        ).fetchone()
        
        assert row is not None
        assert row['simulation_success'] == 0
        assert row['simulation_error'] == error_msg
        
        conn.close()
    
    def test_log_listing_execution_result_success(self):
        """Successfully logs execution success with transaction ID."""
        initialise_listing_preparation_schema()
        
        prep_id = str(uuid4())
        seller = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        cid = "QmTestCID123"
        tx_id = "TXID12345ABCDE"
        
        # First log the start
        log_listing_preparation_start(prep_id, seller, cid)
        
        # Then log success
        log_listing_execution_result(prep_id, True, tx_id=tx_id)
        
        # Verify the update
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute(
            "SELECT * FROM listing_preparation_log WHERE preparation_id = ?",
            (prep_id,)
        ).fetchone()
        
        assert row is not None
        assert row['simulation_success'] == 1
        assert row['execution_success'] == 1
        assert row['execution_tx_id'] == tx_id
        
        conn.close()
    
    def test_log_listing_execution_result_failure(self):
        """Successfully logs execution failure with error message."""
        initialise_listing_preparation_schema()
        
        prep_id = str(uuid4())
        seller = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        cid = "QmTestCID123"
        error_msg = "Execution failed: network timeout"
        
        # First log the start
        log_listing_preparation_start(prep_id, seller, cid)
        
        # Then log failure
        log_listing_execution_result(prep_id, False, error_message=error_msg)
        
        # Verify the update
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute(
            "SELECT * FROM listing_preparation_log WHERE preparation_id = ?",
            (prep_id,)
        ).fetchone()
        
        assert row is not None
        assert row['simulation_success'] == 1  # Was set in previous step
        assert row['execution_success'] == 0
        assert row['execution_error'] == error_msg
        
        conn.close()


# Integration tests (require mocking or TestNet setup)
@pytest.mark.asyncio
async def test_ipfs_upload_failure_returns_error():
    """IPFS upload failure is caught and returned as error."""
    with patch('backend.utils.ipfs.upload_insight_to_ipfs') as mock_upload:
        mock_upload.side_effect = IPFSUploadError("Pinata service down")
        
        with pytest.raises(IPFSUploadError):
            await create_listing_prepared(
                insight_text="test insight",
                price_usdc=100.0,
                seller_wallet="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                listing_app_id=123,
                signer_mnemonic="test mnemonic",
            )


@pytest.mark.asyncio
async def test_simulation_failure_triggers_unpin():
    """Simulation failure triggers unpin cleanup before raising error."""
    with patch('backend.utils.ipfs.upload_insight_to_ipfs') as mock_upload, \
         patch('backend.utils.ipfs.unpin_cid') as mock_unpin, \
         patch('backend.utils.ipfs.AlgorandClient') as mock_algorand:
        
        mock_upload.return_value = "QmTestCID"
        mock_unpin.return_value = None
        
        # Mock ATC with failed simulation
        mock_atc = MagicMock()
        sim_result = MagicMock()
        sim_result.failure_message = "agent not registered"
        sim_result.failed_at = [0]
        mock_atc.simulate.return_value = sim_result
        
        # Patch where AtomicTransactionComposer is imported in the function
        with patch('algosdk.atomic_transaction_composer.AtomicTransactionComposer', return_value=mock_atc):
            with pytest.raises(ListingStoreError) as exc_info:
                await create_listing_prepared(
                    insight_text="test insight",
                    price_usdc=100.0,
                    seller_wallet="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    listing_app_id=123,
                    signer_mnemonic="test mnemonic",
                )
            
            # Verify unpin was called
            mock_unpin.assert_called_once_with("QmTestCID")
            
            # Verify error mentions cleanup
            assert "cleaned up" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_orphan_prevention_audit_trail():
    """Audit trail tracks all attempts including orphan prevention."""
    initialise_listing_preparation_schema()
    
    with patch('backend.utils.ipfs.upload_insight_to_ipfs') as mock_upload, \
         patch('backend.utils.ipfs.unpin_cid') as mock_unpin, \
         patch('backend.utils.ipfs.AlgorandClient') as mock_algorand, \
         patch('backend.utils.ipfs._load_insight_listing_client_class') as mock_loader:
        
        mock_upload.return_value = "QmOrphanTest"
        mock_unpin.return_value = None
        
        # Mock ATC with failed simulation
        mock_atc = MagicMock()
        sim_result = MagicMock()
        sim_result.failure_message = "Invalid price"
        sim_result.failed_at = [0]
        mock_atc.simulate.return_value = sim_result

        mock_client = MagicMock()
        mock_client.get_method.return_value = MagicMock()
        mock_loader.return_value = MagicMock(return_value=mock_client)
        
        with patch('algosdk.atomic_transaction_composer.AtomicTransactionComposer', return_value=mock_atc):
            with pytest.raises(ListingStoreError):
                await create_listing_prepared(
                    insight_text="test insight for orphan prevention",
                    price_usdc=-100.0,  # Invalid price
                    seller_wallet="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    listing_app_id=123,
                    signer_mnemonic="test mnemonic",
                )
        
        # Verify the audit log has the failure recorded
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Get the most recent entry
        row = conn.execute(
            "SELECT * FROM listing_preparation_log WHERE cid_pinned = ? ORDER BY created_at DESC LIMIT 1",
            ("QmOrphanTest",)
        ).fetchone()
        
        assert row is not None
        assert row['cid_pinned'] == "QmOrphanTest"
        assert row['simulation_success'] == 0  # Simulation failed
        assert "Invalid price" in row['simulation_error']
        
        # Verify unpin was called (orphan prevention worked)
        mock_unpin.assert_called()
        
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_store_cid_in_listing_passes_box_reference(monkeypatch):
    """Ensure store_cid_in_listing constructs and passes the listing box reference."""
    from types import SimpleNamespace
    import os

    class DummyResult:
        abi_return = 81

    sent = {}

    # Fake AlgorandClient with minimal interface
    class FakeAlgorand:
        def __init__(self):
            self.account = SimpleNamespace()

        class account:
            @staticmethod
            def from_mnemonic(mnemonic, sender):
                return SimpleNamespace(address=sender)

        def set_default_signer(self, signer):
            self._signer = signer

    monkeypatch.setattr('backend.utils.ipfs.AlgorandClient.from_environment', lambda: FakeAlgorand())

    class FakeAppClient:
        def __init__(self, *args, **kwargs):
            pass

        class send:
            @staticmethod
            def create_listing(args, params=None, send_params=None):
                sent['args'] = args
                sent['params'] = params
                return DummyResult()

        class state:
            class global_state:
                next_listing_id = 80

            class box:
                class listings:
                    @staticmethod
                    def get_value(key):
                        return SimpleNamespace(asa_id=999)

    monkeypatch.setattr('backend.utils.ipfs._load_insight_listing_client_class', lambda: FakeAppClient)

    listing_id, asa_id = store_cid_in_listing(
        cid='QmTestCID',
        listing_app_id=758025190,
        seller_address='M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM',
        price=1000000,
        signer_mnemonic=os.environ.get('DEPLOYER_MNEMONIC', ''),
    )

    assert listing_id == 81
    assert asa_id == 999
    assert 'params' in sent
    params = sent['params']
    assert hasattr(params, 'box_references')
    assert params.box_references, 'Expected at least one box reference'
