from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV = {}
for raw in (ROOT / ".env").read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    ENV[key.strip()] = value.strip().strip('"').strip("'")

payload = {
    "user_query": "Bank Nifty support holds near 52000 and bounce is likely",
    "buyer_address": ENV["BUYER_WALLET"],
    "user_approval_input": "approve",
    "force_buy_for_test": True,
}
request = Request(
    "http://127.0.0.1:8000/demo_purchase",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=180) as response:
    print(response.read().decode("utf-8"))