# Market Data Backend — Code Review

**Reviewed:** 2026-06-27  
**Scope:** `backend/market/` (base, cache, simulator, massive, factory) + `backend/tests/` (all five test files)  
**Planning docs read:** PLAN.md, MARKET_DATA_DESIGN.md, MARKET_INTERFACE.md, MARKET_SIMULATOR.md, MASSIVE_API.md

---

## Test Results

```
35 collected — 34 passed, 1 FAILED (0.73s)
FAILED tests/test_simulator.py::test_correlated_tickers_show_expected_correlation_structure
```

All other tests pass cleanly: cache, base interface, factory, Massive parsing, simulator GBM math, lifecycle start/stop.

---

## Failing Test — Root Cause

**Test:** `test_correlated_tickers_show_expected_correlation_structure`  
**Assertion:** `aapl_googl_corr > 0.5` (expected ~0.70 from the correlation matrix)  
**Actual:** `0.0035` — essentially zero

### Why it fails

The test measures correlation of log returns across 8,000 ticks, but log returns have two independent contributions:

| Source | Std per tick (AAPL) | Variance per tick | Correlated? |
|---|---|---|---|
| GBM diffusion | `vol × √DT = 6.4e-5` | `4.1e-9` | Yes (Cholesky) |
| Random event spike | `P(event) × avg_mag ≈ 3.5e-2` | `1.2e-6` (approx) | No |

The event variance is **~299× larger** than the GBM diffusion variance. The 0.001-probability, 2–5% magnitude spikes are independent across tickers and completely swamp the Cholesky-correlated GBM signal. The sample correlation converges to near zero rather than 0.70.

**Verification:** patching `random.random` to `1.0` (suppressing all events) produces `AAPL/GOOGL = 0.701`, `JPM/NFLX = 0.240` — exactly as the matrix specifies. The GBM math and Cholesky implementation are correct; only the test is wrong.

### Fix

The test should patch out random events so it measures what it claims to measure:

```python
def test_correlated_tickers_show_expected_correlation_structure():
    sim = SimulatorMarketData()
    returns: dict[str, list[float]] = {t: [] for t in SEED_PRICES}

    with patch("market.simulator.random.random", return_value=1.0):  # suppress events
        for _ in range(8_000):
            before = dict(sim._prices)
            sim._advance_prices()
            for ticker in SEED_PRICES:
                returns[ticker].append(math.log(sim._prices[ticker] / before[ticker]))

    aapl_googl_corr = np.corrcoef(returns["AAPL"], returns["GOOGL"])[0, 1]
    jpm_nflx_corr = np.corrcoef(returns["JPM"], returns["NFLX"])[0, 1]

    assert aapl_googl_corr > 0.5
    assert aapl_googl_corr > jpm_nflx_corr
```

---

## Implementation Review

### Overall Assessment

The implementation is clean, well-structured, and faithful to the design documents. The interface/factory pattern is correctly applied, the GBM math is sound, and the error-handling in the background loops is solid. Two bugs and one test gap are noted below.

---

### Bug 1 — `is_ticker_supported` blocks the event loop in Massive mode [P2]

**File:** `backend/market/massive.py:65-80`

`is_ticker_supported` calls `_validate_ticker`, which calls `requests.get(...)` synchronously. When the FastAPI route handler invokes `mkt.is_ticker_supported(ticker)` from an async context, this blocks the entire event loop — all SSE streams and other requests stall for up to the 5-second timeout.

The blocking HTTP calls in `_fetch_and_update` are correctly offloaded via `run_in_executor`; the same must be done here. The cleanest fix is to make `is_ticker_supported` async on the interface:

```python
# In massive.py
async def is_ticker_supported(self, ticker: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, self._validate_ticker, ticker.upper())
```

This requires updating the ABC signature in `base.py` and updating `SimulatorMarketData` (its implementation is already non-blocking, so `async def is_ticker_supported` with a direct `return` is fine).

Alternatively, keep the interface synchronous and document that `MassiveMarketData.is_ticker_supported` must only be called from a thread or executor context — but changing the ABC is cleaner.

---

### Bug 2 — `MassiveMarketData.start()` leaves the cache empty for the first poll interval [P2]

**File:** `backend/market/massive.py:42-44`

`SimulatorMarketData.start()` calls `await self._push_to_cache()` before creating the task, so SSE clients connecting immediately after startup get data. `MassiveMarketData.start()` creates the task and returns immediately — no initial fetch. With `poll_interval=15` (default), the cache is empty for up to 15 seconds after startup. During this window, `GET /api/stream/prices` sends nothing, and `GET /api/watchlist` returns prices as `null`.

Fix: add an initial fetch in `start()`, mirroring the simulator:

```python
async def start(self) -> None:
    await self._fetch_and_update()  # populate cache before first SSE client connects
    self._task = asyncio.create_task(self._poll_loop())
    log.info("MassiveMarketData started (interval=%.1fs)", self._poll_interval)
```

If `_tickers` is empty at startup (edge case), `_fetch_and_update` returns immediately, so this is safe.

---

### Observation — Direct `_data` access bypasses the async lock [Low]

**Files:** `simulator.py:78`, `massive.py:56` (and corresponding `get_prices`, `get_all_prices`)

Both implementations read `self._cache._data` directly rather than awaiting `cache.get()` / `cache.get_all()`. This bypasses the `asyncio.Lock`. The design document documents this intentionally — dict reads in CPython are GIL-protected and the lock only matters for the writer. This is acceptable for a single-event-loop app, but it creates tight coupling (implementations depend on the internal `_data` attribute of `PriceCache`) and the comment in `cache.py` is the only explanation.

No change required, but a future cleanup could expose a synchronous `get_sync` / `get_all_sync` method on `PriceCache` to make the contract explicit and eliminate the `._data` access.

---

### Observation — Design document discrepancy [Low]

`MARKET_INTERFACE.md` includes `self._prev_closes: dict[str, float] = {}` in `MassiveMarketData.__init__`; `MARKET_DATA_DESIGN.md` does not. The actual implementation follows MARKET_DATA_DESIGN.md (no `_prev_closes`; `prev_close` is read fresh from each API response). This is correct — `MARKET_INTERFACE.md` is an earlier draft that was superseded.

---

### What is working well

- **Interface design:** The ABC enforces the contract cleanly. `create_market_data_source()` is the single selection point; no downstream code needs to know which implementation is active.
- **GBM implementation:** The formula, parameter choices, and Cholesky correlation are all mathematically correct. The event spike mechanic adds appropriate drama.
- **Simulator `start()`:** Pre-seeding the cache before creating the task means SSE clients never see an empty first frame.
- **Background loop error handling:** Both `_tick_loop` and `_poll_loop` catch all exceptions, log them, and continue. `asyncio.CancelledError` is re-raised correctly in both.
- **`stop()` implementation:** Both implementations cancel the task and await it, correctly absorbing `CancelledError`. The `if self._task:` guard prevents a crash if `stop()` is called before `start()`.
- **`register_ticker` / `unregister_ticker`:** Clean set-based bookkeeping. The `sorted()` in `_fetch_and_update` gives deterministic query strings (good for caching and logging).
- **`_fetch_snapshots` error path:** `raise_for_status()` plus the `status != "OK"` check gives two layers of protection against bad responses.
- **Test suite coverage:** The 34 passing tests cover all the cases listed in PLAN.md §12 and MARKET_DATA_DESIGN.md §9: positive prices, formula correctness, direction tracking, event magnitude, ticker support, snapshot parsing, fallback to `day.c`, non-OK status handling, poll-loop resilience, factory env-var logic.
- **Deterministic test seed:** The `autouse` fixture seeding both `random` and `numpy.random` makes statistical tests reproducible across runs and CI.

---

## Summary

| Item | Severity | Status |
|---|---|---|
| Correlation test fails due to event noise masking GBM signal | Test bug | Fix: patch out events in that test |
| `is_ticker_supported` blocks the event loop (Massive mode) | P2 bug | Fix: run via executor or make async |
| `MassiveMarketData.start()` leaves cache empty on startup | P2 bug | Fix: add initial `_fetch_and_update()` call |
| Direct `._data` access couples impls to cache internals | Low | Acceptable; document or add sync accessor |
| `MARKET_INTERFACE.md` has stale `_prev_closes` field | Doc drift | Minor; MARKET_DATA_DESIGN.md is authoritative |

The market data backend is production-ready for the simulator path and structurally sound for the Massive path. Fix the two P2 bugs before wiring the Massive client into live FastAPI routes, and patch the correlation test so CI stays green.
