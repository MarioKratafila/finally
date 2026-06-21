# FinAlly — AI Trading Workstation

FinAlly is a Bloomberg-terminal-style trading workstation: live-streaming watchlist prices, a simulated $10,000 portfolio, and an LLM chat copilot that can analyze your positions and execute trades on your behalf. Built entirely by orchestrated coding agents as the capstone project for an agentic AI coding course.

## Stack

- **Frontend**: Next.js (TypeScript, static export) — dark, data-dense terminal UI
- **Backend**: FastAPI (Python, managed with `uv`)
- **Database**: SQLite, lazily initialized and seeded on first run
- **Real-time data**: Server-Sent Events (`/api/stream/prices`)
- **AI**: LiteLLM → OpenRouter (Cerebras inference), structured-output trade/watchlist actions
- **Market data**: built-in GBM simulator by default, or live data via the Massive (Polygon.io) API

Everything ships in a single Docker container on port `8000`.

## Quick Start

```bash
cp .env.example .env   # add your OPENROUTER_API_KEY
./scripts/start_mac.sh # or start_windows.ps1 on Windows
```

Open `http://localhost:8000`. No login required — you start with a default 10-ticker watchlist and $10,000 in virtual cash.

```bash
./scripts/stop_mac.sh  # stop the container (data persists in the db/ volume)
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | Powers the AI chat assistant |
| `MASSIVE_API_KEY` | no | Enables live market data (otherwise uses the built-in simulator) |
| `LLM_MOCK` | no | `true` for deterministic mock LLM responses (used in tests) |
| `CHAT_HISTORY_LIMIT` | no | Chat messages kept as LLM context (default `10`) |
| `PRICE_POLL_INTERVAL_SECONDS` | no | Massive API poll interval in seconds (default `15`) |

## Project Layout

```
frontend/   Next.js static-export UI
backend/    FastAPI app (API, SSE, market data, LLM integration, DB)
test/       Playwright E2E tests
scripts/    Docker start/stop scripts
planning/   Full project specification (see planning/PLAN.md)
```

## Testing

- Backend unit tests: `pytest` (within `backend/`)
- Frontend unit tests: React Testing Library (within `frontend/`)
- E2E: Playwright via `test/docker-compose.test.yml`, running with `LLM_MOCK=true`

## Full Specification

See [`planning/PLAN.md`](planning/PLAN.md) for the complete project spec — architecture rationale, database schema, API contract, and design details.

## License

MIT — see [LICENSE](LICENSE).
