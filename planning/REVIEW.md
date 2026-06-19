# Review of `PLAN.md`

## Overall assessment

The plan establishes a coherent product scope and a sensible single-container architecture. The simulator-first approach, static frontend, SQLite persistence, and SSE transport are appropriate for a capstone and keep the demo operable without market-data infrastructure.

It is not yet a sufficiently precise implementation contract for multiple agents. Several important response schemas and lifecycle rules are left implicit, and two described chat behaviors cannot be implemented as stated. Resolve the blocking items below before splitting implementation across agents.

## Blocking issues

### 1. Same-turn watchlist add and trade does not work reliably in Massive mode

Section 9 says watchlist changes run first so that a newly added ticker has a price before a same-turn trade. Adding a database row does not populate the price cache. With a 15-second asynchronous poll interval, the trade may still have no price.

Choose and document one rule:

- On add, synchronously fetch and validate a quote before committing the watchlist entry, then place it in the cache. This gives same-turn trade execution deterministic semantics.
- Reject a same-turn trade until a quote arrives and return a structured `price_unavailable` result.
- Remove same-turn add-and-trade support.

The first option best matches the promised user experience. Also define behavior for stale quotes, closed markets, upstream timeouts, and invalid symbols.

### 2. The LLM cannot explain execution failures in its original message

The LLM generates `message` before the backend validates and executes its proposed actions. Therefore the statement that an execution error is returned “so the LLM can inform the user” is not true without a second model call.

Do not make a second model call. Define the API response as the proposed assistant message plus authoritative backend results, for example:

```json
{
  "message": "I’ll buy 10 shares of AAPL.",
  "action_results": [
    {
      "type": "trade",
      "status": "rejected",
      "ticker": "AAPL",
      "code": "insufficient_cash",
      "message": "Required $1,900.00; available $1,000.00."
    }
  ]
}
```

The frontend should render these results independently of the model text. Store proposed actions and actual results separately, or make the existing `actions` JSON explicitly represent both.

### 3. Financial mutations need explicit transactional and numeric rules

Trade execution updates cash, positions, realized P&L, the trade log, and a portfolio snapshot. These changes must occur in one SQLite transaction. Otherwise concurrent manual/chat requests or a mid-operation failure can create cash and holdings inconsistencies.

Specify all of the following:

- serialize writes and use a single atomic transaction per trade;
- validate `quantity` as finite and strictly positive, reject NaN/infinity, and normalize ticker case;
- define supported fractional precision and rounding behavior;
- define whether money is stored as integer cents, fixed-point decimal text, or rounded floating point;
- reject a missing or stale execution price;
- prevent cash and position quantity from becoming negative inside the transaction;
- define execution ordering for multiple LLM trades and whether failures are independent (the current text implies ordered, independent actions).

SQLite `REAL` may be acceptable for a demo, but the plan must then define comparison tolerances and display rounding. Integer minor units are safer for cash and realized P&L.

### 4. API and SSE payload contracts are missing

Endpoint names alone are not enough for frontend and backend agents to work independently. Add request/response examples or shared schemas for every endpoint, including error bodies and status codes.

At minimum, settle these ambiguities:

- whether portfolio position values and totals are calculated by the backend or frontend;
- whether `GET /api/watchlist` supplies daily change, previous close, or only the latest tick;
- whether chat history is returned by `GET /api/chat` or embedded elsewhere (there is currently no way to restore persisted chat after refresh);
- the exact `POST /api/chat` response after action validation;
- whether deleting an absent ticker is idempotent;
- how an empty portfolio is represented;
- timestamp format and timezone (use UTC RFC 3339 consistently);
- a stable error shape such as `{code, message, details}`.

For SSE, define an initial full snapshot, named event/type, event ID, retry interval, heartbeat behavior, disconnect cleanup, and payload shape. Native `EventSource` reconnects, but it does not provide application-level connection state or recovery guarantees by itself.

### 5. “Daily change” has no data source

The watchlist requires daily change percentage, but the shared cache only has latest and previous streamed prices. That yields tick-to-tick or session-since-launch change, not daily change. The simulator also has no documented previous close.

Add `previous_close`, `absolute_change`, and `percent_change` to the market-data model and SSE/watchlist contracts, with seeded simulator values. Alternatively relabel the UI as session change and define the session baseline.

## Important design gaps

### Database lifecycle and migrations

The plan alternates between initialization “on startup” and “on first request.” Initialize once during the FastAPI lifespan before starting pollers or accepting requests. First-request initialization creates races and unpredictable health behavior.

“Create missing tables” is not a migration strategy: it cannot evolve existing columns or constraints. Either explicitly state that schema changes require deleting the demo database, or add a lightweight versioned migration mechanism. Also enable foreign keys if they are added, choose WAL/busy-timeout settings, and index common queries such as snapshots and chat history by `(user_id, recorded_at/created_at)`.

### Market-data ownership and dynamic watchlists

Define how the poller learns about additions/removals, whether held tickers are always subscribed, and when cache entries are evicted. Although deletion is blocked for open positions today, this invariant should live in the market-data subscription rule rather than be assumed indirectly.

Specify failure behavior when the Massive service is unavailable. A configured but invalid key should not silently switch to simulated prices because that can make fake prices appear real. Expose source, last successful update, and degraded status through health or a system endpoint.

The phrase “any ticker Massive supports” also needs a concrete symbol-validation operation and canonicalization rules. Do not treat one failed quote as proof that a symbol is permanently invalid.

### Portfolio semantics

Clarify the following calculations:

- `total_value = cash + sum(quantity * current_price)`;
- unrealized P&L and percentage denominator;
- weighted average cost after additional buys;
- realized P&L and remaining average cost after partial sells;
- heatmap “portfolio weight” denominator—positions only or total value including cash;
- behavior when a required current price is unavailable.

The “P&L chart” currently graphs total portfolio value, which is not itself P&L. Either call it portfolio value history or define a P&L series and baseline. Seed an initial snapshot so the chart is not empty for the first 30 seconds. Add retention or downsampling; otherwise snapshots grow indefinitely.

### LLM contract and safety boundaries

Replace the instruction to use a named local skill with an implementation-level contract. A future agent may not have `cerebras-inference` installed. State the LiteLLM model/provider parameters, timeout, retry policy, and structured-output JSON Schema in the plan; a skill may remain an optional implementation aid.

The structured schema should require all three top-level fields, use empty arrays when there are no actions, disallow unknown fields, constrain side/action enums, normalize tickers, and require a finite positive quantity. Set maximum message length and maximum actions per response.

Define timeout, rate-limit, malformed-output, and provider-error responses. Persist the user message before the model call and persist an assistant/error result afterward so conversation history remains coherent. State whether the current user message is excluded from the separately loaded history to avoid including it twice.

Mock mode needs a deterministic request-to-response mapping, not only a flag. Define the exact prompts/commands recognized by the mock so backend and E2E tests agree.

### SSE and frontend state

The frontend needs one authoritative state strategy. Prices arrive through SSE while trades, watchlist changes, and chat actions mutate REST resources. Specify which resources are refetched after each mutation and how stale responses are prevented from overwriting newer SSE prices.

The connection dot needs application rules: when it becomes yellow, when it becomes red, and whether a stream that is open but has stopped receiving heartbeats is considered disconnected. Bound sparkline/main-chart samples to prevent unbounded browser memory use.

### Static hosting

Document FastAPI route precedence and SPA fallback behavior: `/api/*` must never fall through to `index.html`, static assets should return real 404s, and client-side routes—if any—need a fallback compatible with Next.js static export. Pin Node, Python, package-manager, and major framework versions through lockfiles for reproducible agent work.

### Container and startup behavior

The volume description is inconsistent: `finally-data:/app/db` is a named Docker volume and does not map the repository’s top-level `db/` directory. Decide between a named volume and bind mount and describe only that behavior.

Also clarify:

- whether `.env` is optional when simulator plus mock/no-chat operation is desired;
- whether missing `OPENROUTER_API_KEY` disables chat or fails startup;
- container name and image tag used by idempotent scripts;
- readiness versus liveness checks;
- graceful shutdown of background tasks and SSE clients;
- non-root runtime user and writable ownership of `/app/db`.

The host start script can open a browser; the container itself should not attempt to do so.

## Testing improvements

Add tests for the failure modes that protect state integrity:

- two concurrent buys competing for the same cash;
- concurrent sell requests for the same shares;
- rollback after failure between cash and position updates;
- zero, negative, NaN, infinity, excessive precision, and malformed quantities;
- absent, stale, and changing prices during execution;
- partial sells and realized P&L rounding;
- restart with an existing database;
- poller/API failure and recovery;
- SSE initial snapshot, heartbeat timeout, reconnect, and cleanup;
- malformed and semantically invalid LLM actions;
- mixed-success multi-action chat responses;
- same-turn Massive add-and-trade;
- refresh restoring watchlist, portfolio, snapshots, and chat history.

The E2E plan should state how SSE disconnection is induced and observed; “disconnect and verify reconnection” is not reproducible without a defined proxy, browser route interception, or server test hook.

## Recommended implementation sequence

1. Freeze domain models, REST/SSE schemas, error codes, numeric rules, and database transaction boundaries.
2. Implement database initialization and portfolio/watchlist services with unit and concurrency tests.
3. Implement simulator, cache, subscription lifecycle, and SSE contract.
4. Implement the frontend against the frozen simulator-backed contracts.
5. Add LLM structured output, authoritative action results, and deterministic mock mode.
6. Add Massive integration and its degraded/error states.
7. Complete container scripts and run E2E tests against the production image.

## Suggested definition of done

The core build is complete when a fresh checkout can start with one documented command; operate fully in simulator/mock mode without paid credentials; persist and restore state across container restarts; execute every trade atomically; recover visibly from stream interruption; render authoritative action failures separately from LLM prose; and pass unit, integration, and containerized E2E tests with pinned dependencies.
