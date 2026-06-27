from pydantic import BaseModel


class Trade(BaseModel):
    """A single trade action requested by the LLM."""

    ticker: str
    side: str  # "buy" or "sell"
    quantity: float


class WatchlistChange(BaseModel):
    """A single watchlist modification requested by the LLM."""

    ticker: str
    action: str  # "add" or "remove"


class LLMResponse(BaseModel):
    """Structured response returned by the FinAlly assistant."""

    message: str
    trades: list[Trade] = []
    watchlist_changes: list[WatchlistChange] = []
