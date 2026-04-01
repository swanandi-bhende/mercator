from dotenv import load_dotenv
import asyncio
import os
import logging
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage

try:
    from langchain.agents import create_tool_calling_agent, AgentExecutor  # type: ignore
except ImportError:
    create_tool_calling_agent = None
    AgentExecutor = None

from langchain.agents import create_agent

from contracts.insight_listing import InsightListingClient
from backend.contracts.escrow.smart_contracts.artifacts.escrow.escrow_client import EscrowClient
from backend.contracts.reputation.smart_contracts.artifacts.reputation.reputation_client import ReputationClient


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALGOD_URL = os.getenv("ALGOD_URL")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GEMINI_API_KEY,
    temperature=0.3,
    max_retries=0,
)

SYSTEM_PROMPT = """You are Mercator, an autonomous AI trading-insight buyer on Algorand. Your job is to: 1) Search for real human trading insights using semantic search, 2) Evaluate them using on-chain reputation and price, 3) Reason step-by-step whether to buy, 4) Only trigger x402 payment after explicit user approval. Never generate fake data. Always use real human insights."""

prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=SYSTEM_PROMPT),
        ("human", "{input}"),
    ]
)


@tool
def on_chain_query(listing_id: int) -> str:
    """Placeholder tool for reading on-chain listing details."""
    return f"on_chain_query placeholder: listing_id={listing_id}."


@tool
def semantic_search(query: str) -> str:
    """Placeholder tool for semantic retrieval over listings."""
    return f"semantic_search placeholder: query='{query}'."


@tool
def trigger_x402_payment(amount: float, seller_wallet: str) -> str:
    """Placeholder tool for triggering x402 payment flow."""
    return (
        "trigger_x402_payment placeholder: "
        f"amount={amount}, seller_wallet={seller_wallet}."
    )


tools = [on_chain_query, semantic_search, trigger_x402_payment]

if create_tool_calling_agent and AgentExecutor:
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
    )
else:
    logger.info(
        "LangChain create_tool_calling_agent/AgentExecutor not available; "
        "using create_agent compatibility mode"
    )
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    agent_executor = agent


async def run_agent(user_query: str, user_approval: bool = False):
    logger.info("Starting agent run with user_approval=%s", user_approval)
    payload: dict[str, Any]
    if create_tool_calling_agent and AgentExecutor:
        payload = {"input": user_query}
    else:
        payload = {"messages": [{"role": "user", "content": user_query}]}

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = await asyncio.to_thread(agent_executor.invoke, payload)
            return result
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            is_quota_error = (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "TooManyRequests" in error_text
            )
            is_model_error = (
                "404" in error_text
                or "NOT_FOUND" in error_text
                or "is not found" in error_text
                or "not supported for generateContent" in error_text
            )
            if is_quota_error and attempt < max_attempts:
                delay_seconds = 2 ** attempt
                logger.warning(
                    "Gemini quota/rate limit hit; retrying in %ss (attempt %s/%s)",
                    delay_seconds,
                    attempt,
                    max_attempts,
                )
                await asyncio.sleep(delay_seconds)
                continue

            if is_quota_error:
                logger.warning(
                    "Gemini quota exhausted on free tier; returning fallback response"
                )
                return {
                    "success": False,
                    "fallback": True,
                    "message": "Gemini free-tier quota reached. Skipping live AI reasoning for now.",
                    "next_step": "Retry later or upgrade Gemini quota/billing.",
                    "input": user_query,
                }

            if is_model_error:
                logger.warning(
                    "Configured Gemini model is unavailable for this key; returning fallback response"
                )
                return {
                    "success": False,
                    "fallback": True,
                    "message": (
                        f"Configured model '{GEMINI_MODEL}' is unavailable for this API key. "
                        "Set GEMINI_MODEL in .env to an available model and retry."
                    ),
                    "next_step": "Run Gemini ListModels or switch to a supported model for your project.",
                    "input": user_query,
                }

            raise


if __name__ == "__main__":
    result = asyncio.run(run_agent("Find me the latest NIFTY call option insight"))
    print(result)
