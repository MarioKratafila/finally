"""LLM client: calls the FinAlly assistant via LiteLLM -> OpenRouter (Cerebras)."""

import os

from litellm import completion

from .prompt import build_context_message, build_system_prompt
from .schema import LLMResponse

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}

MOCK_RESPONSE = LLMResponse(
    message="I see your portfolio. You have $10,000 in cash. How can I help you today?",
    trades=[],
    watchlist_changes=[],
)

ERROR_RESPONSE = LLMResponse(
    message="I encountered an error. Please try again.",
    trades=[],
    watchlist_changes=[],
)


async def chat_with_llm(
    user_message: str,
    portfolio_context: dict,
    conversation_history: list[dict],
) -> LLMResponse:
    """Calls the LLM and returns a structured response.

    If env var LLM_MOCK=true, returns MOCK_RESPONSE without calling the API.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    portfolio_context: dict with cash, total_value, realized_pnl, positions, watchlist
    """
    if os.environ.get("LLM_MOCK", "").lower() == "true":
        return MOCK_RESPONSE

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_context_message(portfolio_context)},
        *conversation_history,
        {"role": "user", "content": user_message},
    ]

    try:
        response = completion(
            model=MODEL,
            messages=messages,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            response_format=LLMResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
        result = response.choices[0].message.content
        return LLMResponse.model_validate_json(result)
    except Exception:
        return ERROR_RESPONSE
