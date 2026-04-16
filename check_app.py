#!/usr/bin/env python3
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from algokit_utils import AlgorandClient

# Load .env.testnet
load_dotenv(Path(".env.testnet"), override=True)

# Get the InsightListing app
app_id = 758025190
algorand = AlgorandClient.from_environment()

algod = algorand.client.algod
app_info = algod.application_info(app_id)

print(f"App ID: {app_id}")
print(f"State Schema - Global: integers={app_info['params'].get('global-state-schema', {}).get('num-uint', 0)}, bytes={app_info['params'].get('global-state-schema', {}).get('num-byte-slice', 0)}")
print(f"State Schema - Local: integers={app_info['params'].get('local-state-schema', {}).get('num-uint', 0)}, bytes={app_info['params'].get('local-state-schema', {}).get('num-byte-slice', 0)}")
print(f"Extra Pages: {app_info['params'].get('extra-pages', 0)}")

# Check if there's a "box" key
if 'box-state' in app_info['params']:
    print(f"Box State: {app_info['params']['box-state']}")
else:
    print("No box-state found in app info - app does NOT support boxes!")
