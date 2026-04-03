from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from backend.agent import run_agent
from backend.utils.runtime_env import normalize_network_env


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _launch(command: list[str], cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )


async def _interactive_agent() -> None:
    print("\nMercator demo agent ready. Type a query or 'quit'.")
    while True:
        user_query = input("query> ").strip()
        if user_query.lower() in {"quit", "exit"}:
            return
        if not user_query:
            continue

        result = await run_agent(
            user_query=user_query,
            buyer_address=os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip(),
            user_approval_input="approve",
            force_buy_for_test=True,
        )
        print(result)


async def main() -> None:
    normalize_network_env()

    backend_proc = _launch([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], ROOT)
    frontend_proc = _launch(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"], FRONTEND)

    def _shutdown(*_: object) -> None:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        await _interactive_agent()
    finally:
        _shutdown()


if __name__ == "__main__":
    asyncio.run(main())