# Massive API Reference (formerly Polygon.io)

Polygon.io rebranded as **Massive** on October 30, 2025. Existing API keys, accounts, and integrations continue to work unchanged. Both `api.polygon.io` and `api.massive.com` are supported as base URLs.

---

## Authentication

All requests require an API key. Pass it as a query parameter or via Bearer token header.

**Query parameter (simplest):**
```
GET https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?apiKey=YOUR_API_KEY
```

**Authorization header:**
```
Authorization: Bearer YOUR_API_KEY
```

API keys are managed at `https://massive.com/dashboard/api-keys`.

---

## Base URLs

| Option | URL |
|--------|-----|
| New (Massive) | `https://api.massive.com` |
| Legacy (Polygon) | `https://api.polygon.io` (still supported) |

Both are functionally identical — use either. This project uses `https://api.polygon.io` as the default since that is what existing `polygon` Python client versions target.

---

## Rate Limits

| Plan | Requests / Minute | Data Latency |
|------|------------------|--------------|
| Free / Starter | **5** | 15-minute delay |
| Developer | Unlimited | 15-minute delay |
| Advanced | Unlimited | Real-time |
| Business | Unlimited | Real-time |

Paid plans recommend staying under **100 requests/second** as a courtesy limit. The free tier's 5 req/min limit is why `PRICE_POLL_INTERVAL_SECONDS` defaults to 15 in this project.

---

## Python Client Library

The official client wraps the REST API with automatic pagination and type hints.

```bash
pip install -U polygon-api-client
# or the Massive-branded package:
pip install -U massive
```

Both packages expose the same `RESTClient` interface. This project uses `polygon-api-client` (the more established name in PyPI).

```python
from polygon import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")
```

---

## Key Endpoints

### 1. Full Market Snapshot — Multiple Tickers

Retrieve the latest price data for a comma-separated list of tickers (or all tickers if omitted) in a single call. **This is the primary endpoint used by this project for bulk price polling.**

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tickers` | string | No | Comma-separated symbols, e.g. `AAPL,GOOGL,MSFT`. Omit for all tickers. |
| `include_otc` | boolean | No | Include OTC securities. Default: `false` |
| `apiKey` | string | Yes | Your API key |

**Example Request:**
```python
from polygon import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")

# Fetch snapshot for specific tickers
snapshots = client.get_snapshot_all(
    "stocks",
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
)
for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price:.2f} (change: {snap.todays_change_perc:.2f}%)")
```

**Raw HTTP Example:**
```python
import requests

tickers = "AAPL,GOOGL,MSFT,AMZN,TSLA,NVDA,META,JPM,V,NFLX"
resp = requests.get(
    "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers",
    params={"tickers": tickers, "apiKey": "YOUR_API_KEY"},
    timeout=10,
)
data = resp.json()
# data["tickers"] is a list of snapshot objects
```

**Response Structure:**
```json
{
  "count": 2,
  "status": "OK",
  "tickers": [
    {
      "ticker": "AAPL",
      "lastTrade": {
        "p": 192.35,
        "s": 100,
        "t": 1717000000000000000,
        "x": 4
      },
      "prevDay": {
        "c": 189.87,
        "h": 193.10,
        "l": 188.50,
        "o": 190.00,
        "v": 52341000,
        "vw": 190.85
      },
      "day": {
        "c": 192.35,
        "h": 193.50,
        "l": 191.00,
        "o": 191.20,
        "v": 28450000,
        "vw": 192.10
      },
      "min": {
        "c": 192.35,
        "h": 192.40,
        "l": 192.20,
        "o": 192.30,
        "v": 12400
      },
      "todaysChange": 2.48,
      "todaysChangePerc": 1.306,
      "updated": 1717000000000000000
    }
  ]
}
```

**Key Fields:**

| Field | Description |
|-------|-------------|
| `lastTrade.p` | Most recent trade price |
| `lastTrade.s` | Trade size (shares) |
| `lastTrade.t` | Trade timestamp (Unix nanoseconds) |
| `prevDay.c` | Previous day's closing price |
| `day.c` | Today's current close/last price |
| `todaysChange` | Dollar change from previous close |
| `todaysChangePerc` | Percentage change from previous close |
| `updated` | Last update timestamp (Unix nanoseconds) |

---

### 2. Single Ticker Snapshot

Detailed snapshot for one ticker, including minute bar.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}
```

**Example Request:**
```python
snap = client.get_snapshot("stocks", "AAPL")
print(f"AAPL: ${snap.last_trade.price:.2f}")
print(f"  Prev close: ${snap.prev_day.close:.2f}")
print(f"  Today change: {snap.todays_change_perc:.2f}%")
```

**Raw HTTP:**
```python
resp = requests.get(
    "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/AAPL",
    params={"apiKey": "YOUR_API_KEY"},
    timeout=10,
)
snap = resp.json()["ticker"]
price = snap["lastTrade"]["p"]
```

**Response:**
```json
{
  "request_id": "657e430f1ae768891f018e08e03598d8",
  "status": "OK",
  "ticker": {
    "ticker": "AAPL",
    "day":      { "c": 192.35, "o": 191.20, "h": 193.50, "l": 191.00, "v": 28450000 },
    "min":      { "c": 192.35, "o": 192.30, "h": 192.40, "l": 192.20, "v": 12400 },
    "lastTrade":{ "p": 192.35, "s": 100, "t": 1717000000000000000 },
    "lastQuote":{ "p": 192.34, "P": 192.36, "s": 8, "S": 4 },
    "prevDay":  { "c": 189.87, "o": 190.00, "h": 193.10, "l": 188.50, "v": 52341000 },
    "todaysChange": 2.48,
    "todaysChangePerc": 1.306,
    "updated": 1717000000000000000
  }
}
```

---

### 3. Previous Day Bar (OHLC)

End-of-day aggregate for a single ticker. Use this for historical close prices.

```
GET /v2/aggs/ticker/{stocksTicker}/prev
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `adjusted` | boolean | No | Split-adjusted prices. Default: `true` |
| `apiKey` | string | Yes | Your API key |

**Example Request:**
```python
prev = client.get_previous_close_agg("AAPL")
print(f"AAPL previous close: ${prev[0].close:.2f}")
print(f"  Open: ${prev[0].open:.2f}, High: ${prev[0].high:.2f}, Low: ${prev[0].low:.2f}")
print(f"  Volume: {prev[0].volume:,.0f}")
```

**Raw HTTP:**
```python
resp = requests.get(
    "https://api.polygon.io/v2/aggs/ticker/AAPL/prev",
    params={"adjusted": "true", "apiKey": "YOUR_API_KEY"},
    timeout=10,
)
result = resp.json()["results"][0]
prev_close = result["c"]  # closing price
```

**Response:**
```json
{
  "ticker": "AAPL",
  "adjusted": true,
  "queryCount": 1,
  "resultsCount": 1,
  "status": "OK",
  "request_id": "abc123",
  "results": [
    {
      "o": 190.00,
      "h": 193.10,
      "l": 188.50,
      "c": 189.87,
      "v": 52341000,
      "vw": 190.85,
      "t": 1716940800000,
      "n": 423180
    }
  ]
}
```

**Key Fields:**

| Field | Description |
|-------|-------------|
| `o` | Open price |
| `h` | High price |
| `l` | Low price |
| `c` | Close price |
| `v` | Volume |
| `vw` | Volume-weighted average price (VWAP) |
| `t` | Bar start timestamp (Unix milliseconds) |
| `n` | Number of transactions |

---

### 4. Daily OHLC Summary (Historical)

OHLC for any specific date, including pre-market and after-hours prices.

```
GET /v1/open-close/{stocksTicker}/{date}
```

**Path Parameters:** `stocksTicker` (e.g. `AAPL`), `date` (e.g. `2024-01-09`)

**Example Request:**
```python
resp = requests.get(
    "https://api.polygon.io/v1/open-close/AAPL/2024-01-09",
    params={"adjusted": "true", "apiKey": "YOUR_API_KEY"},
    timeout=10,
)
day = resp.json()
print(f"Open: {day['open']}, Close: {day['close']}")
print(f"Pre-market: {day['preMarket']}, After-hours: {day['afterHours']}")
```

**Response:**
```json
{
  "afterHours": 185.30,
  "close": 185.92,
  "from": "2024-01-09",
  "high": 186.74,
  "low": 183.43,
  "open": 184.35,
  "preMarket": 184.00,
  "status": "OK",
  "symbol": "AAPL",
  "volume": 49128336
}
```

---

### 5. Last Trade (Single Ticker, Real-Time)

Most recent trade for a single ticker. Lower overhead than the snapshot for single-ticker use cases.

```
GET /v2/last/trade/{stocksTicker}
```

**Example Request:**
```python
trade = client.get_last_trade("AAPL")
print(f"Last trade: ${trade.price:.2f} x {trade.size} shares")
```

**Raw HTTP:**
```python
resp = requests.get(
    "https://api.polygon.io/v2/last/trade/AAPL",
    params={"apiKey": "YOUR_API_KEY"},
    timeout=10,
)
result = resp.json()["results"]
price = result["p"]  # price
size = result["s"]   # shares traded
timestamp_ns = result["t"]  # Unix nanoseconds
```

**Response:**
```json
{
  "request_id": "f05562305bd26ced64b98ed68b3c5d96",
  "results": {
    "T": "AAPL",
    "p": 192.35,
    "s": 100,
    "t": 1717000000000000000,
    "x": 4,
    "z": 3
  },
  "status": "OK"
}
```

---

## Unified Snapshot (v3) — Multi-Asset Class

The v3 endpoint supports querying up to 250 tickers across asset classes in a single request.

```
GET /v3/snapshot
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker.any_of` | string | No | Comma-separated tickers, up to 250 |
| `type` | string | No | Asset class: `stocks`, `options`, `fx`, `crypto`, `indices` |
| `limit` | integer | No | Results per page (max: 250, default: 10) |
| `order` | string | No | `asc` or `desc` |
| `sort` | string | No | Field to sort by |
| `apiKey` | string | Yes | Your API key |

**Example Request:**
```python
resp = requests.get(
    "https://api.polygon.io/v3/snapshot",
    params={
        "ticker.any_of": "AAPL,GOOGL,MSFT,AMZN,TSLA",
        "type": "stocks",
        "limit": 250,
        "apiKey": "YOUR_API_KEY",
    },
    timeout=10,
)
data = resp.json()
for item in data["results"]:
    print(item)
```

---

## Error Handling

All endpoints return a `status` field. On error:

```json
{
  "status": "ERROR",
  "error": "Your API Key is not valid.",
  "request_id": "abc123"
}
```

HTTP status codes:
- `200` — Success
- `403` — Invalid or missing API key
- `404` — Ticker not found
- `429` — Rate limit exceeded

**Handling rate limits:**
```python
import time
import requests

def fetch_with_retry(url, params, max_retries=3):
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Rate limit exceeded after retries")
```

---

## Ticker Universe

For the free/Starter tier, the API supports all US exchange-listed stocks. There is no restriction on which tickers can be queried — any valid US equity symbol works.

Tickers not recognized by Massive return `404` or an empty result rather than an error, so validate ticker existence before adding to the watchlist.

---

## Summary: Which Endpoint to Use

| Use Case | Endpoint | Notes |
|----------|----------|-------|
| Poll prices for 10 watched tickers | `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=...` | Single call for all tickers |
| End-of-day close for one ticker | `GET /v2/aggs/ticker/{ticker}/prev` | Returns OHLCV |
| Historical OHLC for a date | `GET /v1/open-close/{ticker}/{date}` | Includes pre/after-hours |
| Real-time price for one ticker | `GET /v2/last/trade/{ticker}` | Lowest latency, single ticker |
| Multi-asset snapshot | `GET /v3/snapshot?ticker.any_of=...` | Up to 250 tickers, any asset class |
