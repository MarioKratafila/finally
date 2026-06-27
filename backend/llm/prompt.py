"""Prompt construction for the FinAlly trading assistant."""


def build_system_prompt() -> str:
    """Returns the system prompt for the FinAlly assistant."""
    return (
        "You are FinAlly, an AI trading copilot embedded in a simulated trading "
        "workstation. You help the user understand and manage a virtual portfolio "
        "of stocks funded with fake money.\n\n"
        "Your responsibilities:\n"
        "- Analyze portfolio composition, risk concentration, and P&L.\n"
        "- Suggest trades with clear, data-driven reasoning.\n"
        "- Execute trades when the user asks or agrees.\n"
        "- Manage the watchlist proactively (add or remove tickers).\n"
        "- Be concise, professional, and grounded in the numbers you are given.\n\n"
        "You MUST always respond with a single valid JSON object matching this schema:\n"
        "{\n"
        '  "message": "your conversational reply to the user",\n'
        '  "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],\n'
        '  "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]\n'
        "}\n\n"
        "Rules for the JSON:\n"
        '- "message" is required and is the only text shown to the user.\n'
        '- "trades" is optional; omit it or use an empty array when no trade is needed.\n'
        '- "watchlist_changes" is optional; omit it or use an empty array when none is needed.\n'
        '- "side" must be "buy" or "sell". "action" must be "add" or "remove".\n'
        "- Do not include any text outside the JSON object."
    )


def build_context_message(portfolio_context: dict) -> str:
    """Formats portfolio context into a human-readable summary for the LLM.

    portfolio_context keys:
      - cash: float
      - total_value: float
      - realized_pnl: float
      - positions: list of {ticker, quantity, avg_cost, current_price,
                            unrealized_pnl, pnl_pct}
      - watchlist: list of {ticker, price, change_pct}
    """
    cash = portfolio_context.get("cash", 0.0)
    total_value = portfolio_context.get("total_value", 0.0)
    realized_pnl = portfolio_context.get("realized_pnl", 0.0)
    positions = portfolio_context.get("positions", [])
    watchlist = portfolio_context.get("watchlist", [])

    lines = ["Current portfolio state:"]
    lines.append(f"- Cash balance: ${cash:,.2f}")
    lines.append(f"- Total portfolio value: ${total_value:,.2f}")
    lines.append(f"- Cumulative realized P&L: ${realized_pnl:,.2f}")

    if positions:
        lines.append("\nPositions:")
        for p in positions:
            lines.append(
                f"- {p.get('ticker')}: {p.get('quantity')} shares @ avg "
                f"${p.get('avg_cost', 0.0):,.2f}, current ${p.get('current_price', 0.0):,.2f}, "
                f"unrealized P&L ${p.get('unrealized_pnl', 0.0):,.2f} "
                f"({p.get('pnl_pct', 0.0):+.2f}%)"
            )
    else:
        lines.append("\nPositions: none (no open positions).")

    if watchlist:
        lines.append("\nWatchlist:")
        for w in watchlist:
            lines.append(
                f"- {w.get('ticker')}: ${w.get('price', 0.0):,.2f} "
                f"({w.get('change_pct', 0.0):+.2f}%)"
            )
    else:
        lines.append("\nWatchlist: empty.")

    return "\n".join(lines)
