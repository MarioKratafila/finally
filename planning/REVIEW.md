# Review of PLAN.md

## Findings

### High: Default launch promises an AI chat panel, but the LLM key is required

`planning/PLAN.md:15`, `planning/PLAN.md:20`, and `planning/PLAN.md:123` conflict. The first-launch experience says the app starts with an AI chat panel ready to assist, but `OPENROUTER_API_KEY` is required and `LLM_MOCK` defaults to `false`. A user who runs the single Docker command without creating a real OpenRouter key will get a broken or unavailable core feature on first launch.

Recommendation: make the default demo path explicit. Either set `LLM_MOCK=true` in the provided starter `.env.example` and start scripts unless a key is supplied, or define graceful no-key behavior where `/api/chat` returns deterministic local responses and the UI remains usable.

### High: Same-turn AI watchlist add plus trade is not guaranteed to have a price

`planning/PLAN.md:310` says watchlist changes run before trades so a newly added ticker has a price available before a same-turn trade executes. That is not guaranteed in Massive mode because `planning/PLAN.md:174` polls every 15 seconds by default, and the background poller may not refresh the new ticker before trade validation/fill. The trade path requires current price data, but the plan does not specify an on-demand quote fetch, a cache miss strategy, or a "pending price" state.

Recommendation: define a synchronous price acquisition path for newly added tickers before executing same-turn trades, or require trades for newly added tickers to fail with a specific retryable error until the cache has a quote.

### High: The frontend requires daily change percent, but the backend data model only defines previous-tick change

The watchlist UI requires `daily change %` at `planning/PLAN.md:368`, but the price cache and SSE event shape only include latest price, previous price, timestamp, and change direction at `planning/PLAN.md:180` and `planning/PLAN.md:190`. Previous tick change is not daily change. Without a previous close, session open, or simulator baseline, frontend agents will either invent inconsistent calculations or show misleading data.

Recommendation: add `day_open_price` or `previous_close_price` plus `day_change` and `day_change_percent` to the market data contract and relevant API responses. For simulator mode, seed each ticker with a previous close or initial session price.

### Medium: Default simulator mode conflicts with watchlist feature and tests

`planning/PLAN.md:31` and `planning/PLAN.md:464` present watchlist add/remove as a normal user and E2E workflow, but `planning/PLAN.md:159` and `planning/PLAN.md:168` restrict simulator mode to the default 10 tickers. Since simulator mode is the default and recommended path, "add ticker" can only succeed for a previously removed default ticker. The structured LLM example uses `PYPL` at `planning/PLAN.md:325`, which will fail in the default mode.

Recommendation: either expand the simulator universe beyond the default watchlist, or make the default-mode UX/tests use only removable/re-addable seeded tickers. Also update the structured-output example so it does not demonstrate an action that fails in the default environment.

### Medium: Portfolio history may be empty on first render

`planning/PLAN.md:241` records snapshots every 30 seconds and after trades, while `planning/PLAN.md:467` expects the P&L chart to have data points in E2E. On a fresh start before 30 seconds pass and before any trade executes, `/api/portfolio/history` can legitimately be empty unless startup initialization creates an initial snapshot.

Recommendation: require an initial portfolio snapshot during database initialization or app startup. The frontend can then render a one-point baseline immediately.

### Medium: Database initialization and migration behavior is underspecified for existing volumes

`planning/PLAN.md:199` says missing tables are created and default data is seeded if the file does not exist or tables are missing. That is risky for persistent SQLite volumes: a partially migrated database can be reseeded incorrectly, and schema evolution is not defined even though this is a multi-agent build where agents may add columns independently.

Recommendation: add a simple `schema_version` table and idempotent migration steps. Seed only when creating a new user profile/watchlist for the first time, not merely because a table is missing.

### Medium: Trade validation lacks core numeric constraints

`planning/PLAN.md:273`, `planning/PLAN.md:331`, and `planning/PLAN.md:445` cover cash, share ownership, and watchlist validation, but the plan does not explicitly reject zero, negative, non-finite, or absurdly precise quantities. Since fractional shares are supported at `planning/PLAN.md:226` and `planning/PLAN.md:237`, agents need a shared precision and rounding rule.

Recommendation: specify `quantity > 0`, finite numeric inputs only, maximum decimal precision, cash/share comparison tolerance, and whether prices/portfolio math use integer cents/Decimal or floats.

### Low: Chat persistence is ambiguous

The schema supports `user` and `assistant` rows at `planning/PLAN.md:250`, but the chat flow at `planning/PLAN.md:311` says "Stores the message and executed actions" singular. It is unclear whether the user's inbound message is stored before the LLM call, whether failed LLM calls are recorded, and which row owns the executed action JSON.

Recommendation: define that each chat request stores one user row and one assistant row, with action results attached to the assistant row. Also define behavior for LLM/API failures so history remains understandable.

### Low: Massive polling contract needs an endpoint/batching decision

`planning/PLAN.md:174` says the backend polls the union of all watched tickers at a cadence chosen for a 5 calls/min free tier. That only works if the chosen Massive endpoint supports batching the full watchlist in one request. If implementation agents choose a per-ticker endpoint, the default 10 ticker watchlist will exceed the stated rate assumption immediately.

Recommendation: name the exact Massive endpoint/response shape or require a provider adapter with tests proving that one poll cycle stays within the configured request budget.

## Summary

The plan is directionally strong and gives agents a usable product shape, but it needs tighter contracts around default demo behavior, price availability, market data fields, and persistence. Fixing those gaps before implementation will prevent frontend, backend, and test agents from making incompatible assumptions.
