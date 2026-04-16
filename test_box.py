#!/usr/bin/env python3
from pathlib import Path
from dotenv import load_dotenv
import sys

load_dotenv(Path(".env.testnet"), override=True)

sys.path.insert(0, 'backend/contracts/insight_listing')
from smart_contracts.artifacts.insight_listing.insight_listing_client import InsightListingClient
from algokit_utils import AlgorandClient

algorand = AlgorandClient.from_environment()

# Test the new app
new_app_id = 758921498
client = InsightListingClient(
    algorand=algorand,
    app_id=new_app_id,
)

try:
    # Try to get the box state
    box_state = client.state.box
    print(f"✓ New app {new_app_id} box state accessible")
except Exception as e:
    print(f"✗ Error accessing box state on new app: {e}")
