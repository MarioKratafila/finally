# FinAlly — Market Data Backend: Summary

This document consolidates all planning, design, and review material for the market data subsystem of FinAlly. It supersedes the individual documents (`MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md`, `MARKET_DATA_DESIGN.md`, `MARKET_DATA_REVIEW.md`) as the single source of truth.

---

## What it does

The market data backend streams live price quotes to the rest of the FinAlly server. It runs as an in-process asyncio background task and writes into a shared in-memory cache. Everything downstream — SSE streaming, portfolio valuation, watchlist API — reads from that cache without knowing whether prices came from a simulator or a real API.

One environment variable chooses the source:

```
MASSIVE_API_KEY unset/empty  →  Simulator (GBM, no dependencies)
MASSIVE_API_KEY set          →  Massive / Polygon.io REST polling
```

---

## File layout

```
backend/market/
├── base.py        PricePoint dataclass + MarketDataSource ABC
├── cache.py       PriceCache — shared in-memory dict, lock-protected writes
├── simulator.py   SimulatorMarketData — GBM with correlated tickers + event spikes
├── massive.py     MassiveMarketData   — Polygon.io REST polling via run_in_executor
└── factory.py     create_market_data_source() — the single selection point
```

---

## Data contract — `PricePoint`

Every consumer receives this shape. No consumer touches source-specific fields.

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | Always uppercase |
| `price` | `float` | Current price |
| `prev_price` | `float` | Price on the previous tick — drives flash direction |
| `prev_close` | `float` | Previous trading day's close — drives daily % change |
| `change` | `float` | `price − prev_close` |
| `change_pct` | `float` | `change / prev_close × 100` |
| `timestamp` | `float` | Unix seconds UTC |
| `direction` | `str` | `"up"`, `"down"`, or `"flat"` vs `prev_price` |

---

## Interface — `MarketDataSource`

```python
class MarketDataSource(ABC):
    async def start(self) -> None           # called at FastAPI lifespan startup
    async def stop(self) -> None            # called at FastAPI lifespan shutdown
    def get_price(self, ticker) -> PricePoint | None
    def get_prices(self, tickers) -> dict[str, PricePoint]
    def get_all_prices(self) -> dict[str, PricePoint]
    async def is_ticker_supported(self, ticker) -> bool  # async: Massive hits the API
```

`get_price` / `get_prices` / `get_all_prices` are synchronous — they read `cache._data` directly, which is safe in CPython's single event-loop model (only `update()` needs the lock since it is the sole writer). `is_ticker_supported` is async because the Massive implementation must call the network.

---

## Simulator

**Algorithm:** Geometric Brownian Motion, `S(t+dt) = S(t) · exp((μ − σ²/2)·dt + σ·√dt·Z)`

- `dt = 0.5s / (252 days × 6.5 h × 3600 s) ≈ 8.5 × 10⁻⁸ years`
- Updates every 500 ms (fixed)
- 10 tickers only: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

**Correlation:** correlated normals produced by Cholesky decomposition of a 10×10 sector-grouped correlation matrix. Tech tickers share correlation ~0.60–0.72; financials (JPM, V) share ~0.65; cross-sector correlations are lower (~0.18–0.45).

**Per-ticker parameters:**

| Ticker | Drift | Vol | Notes |
|---|---|---|---|
| AAPL | 5% | 22% | |
| GOOGL | 6% | 24% | |
| MSFT | 7% | 20% | |
| AMZN | 8% | 26% | |
| TSLA | 10% | 55% | high vol |
| NVDA | 12% | 50% | high vol |
| META | 9% | 30% | |
| JPM | 4% | 18% | low vol, financial |
| V | 4% | 15% | low vol, financial |
| NFLX | 7% | 35% | |

**Event spikes:** each ticker has a 0.1% chance per tick of a 2–5% sudden move (random direction). This adds drama but contributes ~300× more variance per tick than the GBM diffusion term; events are intentionally uncorrelated across tickers.

**`prev_close`:** initialised to the seed price at startup and never reset. The daily % change display therefore shows change-from-startup rather than change-from-yesterday. Acceptable for a demo; a future enhancement could snapshot prices at midnight.

---

## Massive API (Polygon.io)

Polls `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=...` at the configured interval (default 15 s, matching the free tier's 5 req/min limit).

- Any valid US equity symbol is supported
- The blocking `requests.get` call runs via `loop.run_in_executor` so it never stalls the event loop
- `start()` runs an initial fetch before creating the background loop so the cache is populated immediately on startup
- `register_ticker` / `unregister_ticker` maintain the live set of tickers to poll; called by the watchlist API on add/remove
- Ticker validation (`is_ticker_supported`) queries the single-ticker snapshot endpoint and checks for 404 / non-OK status; runs via `run_in_executor`

**Rate-limit handling:** the poll interval itself is the backoff — the free tier's 5 req/min becomes 12 s between calls, and the default is 15 s. A `429` causes `raise_for_status()` to raise, the error is logged, and the loop retries on the next scheduled tick.

**Price fallback:** `lastTrade.p` is preferred; if absent (pre-market, closed market), falls back to `day.c`.

**Environment variables:**

| Variable | Default | Effect |
|---|---|---|
| `MASSIVE_API_KEY` | unset | Unset/empty → simulator |
| `PRICE_POLL_INTERVAL_SECONDS` | `15` | Massive poll cadence only |

---

## Shared price cache

`PriceCache` is a plain dict (`str → PricePoint`) protected by an `asyncio.Lock`. Only `update()` takes the lock (it is the sole writer). Read methods access `_data` directly for performance — GIL protection is sufficient for single-value dict reads in CPython.

The SSE stream endpoint reads `get_all_prices()` every 500 ms and pushes all known prices. In Massive mode, prices may repeat across several SSE ticks between polls.

---

## FastAPI wiring (sketch)

```python
@asynccontextmanager
async def lifespan(app):
    market = create_market_data_source()
    await market.start()
    yield
    await market.stop()

@app.post("/api/watchlist")
async def add_ticker(body, mkt = Depends(get_market)):
    if not await mkt.is_ticker_supported(body.ticker.upper()):
        raise HTTPException(400, "Ticker not supported")
    if isinstance(mkt, MassiveMarketData):
        mkt.register_ticker(body.ticker.upper())
    # ... persist to DB ...
```

---

## Tests — 36 total, all passing

| File | Tests | Coverage |
|---|---|---|
| `test_base.py` | 3 | `PricePoint` fields, ABC cannot be instantiated, both impls are subclasses |
| `test_cache.py` | 5 | CRUD, missing key, overwrite, snapshot isolation |
| `test_factory.py` | 5 | Env-var selection, poll interval, default tickers pre-registered |
| `test_simulator.py` | 9 | Positive prices, formula correctness, direction, events, correlation, start/stop |
| `test_massive.py` | 14 | Snapshot parsing, fallback, direction tracking, ticker registration, error handling, poll resilience, start/stop, initial fetch |

**Determinism:** an `autouse` pytest fixture seeds both `random` and `numpy.random` before every test.

**Correlation test note:** the test suppresses random events (via `patch`) before measuring log-return correlation. Without suppression, event spikes (~300× the per-tick GBM variance) swamp the signal and produce near-zero measured correlation despite a true structural correlation of 0.70.

---

## Known limitations / future work

| Item | Notes |
|---|---|
| `prev_close` drift | Simulator uses startup price as prev_close forever; could snapshot at midnight wall-clock |
| Cache coupling | Implementations access `cache._data` directly; could add `get_sync` / `get_all_sync` helpers to formalise the contract |
| No rate-limit backoff | Massive: a `429` just waits for the next poll interval; exponential backoff would be more correct under sustained pressure |
| Simulator universe is fixed | Cannot add arbitrary tickers in simulator mode by design |
