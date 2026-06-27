import { test, expect, Page } from '@playwright/test';

const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

// Wait for SSE prices to start flowing (a ticker symbol becomes visible)
async function waitForPrices(page: Page) {
  await page.waitForFunction(
    () => document.body.innerText.includes('AAPL'),
    { timeout: 15000 }
  );
}

test('1. app loads with default watchlist', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/FinAlly/i);
  await expect(page.getByText('FinAlly', { exact: true }).first()).toBeVisible();
  await waitForPrices(page);
  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByText(ticker, { exact: true }).first()).toBeVisible();
  }
});

test('2. header shows $10,000 balance', async ({ page }) => {
  await page.goto('/');
  await waitForPrices(page);
  await expect(page.getByText(/10,000/).first()).toBeVisible();
  await expect(page.getByText(/Cash/i).first()).toBeVisible();
});

test('3. portfolio API returns correct initial state', async ({ page }) => {
  const res = await page.request.get('/api/portfolio');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.cash).toBeGreaterThanOrEqual(9999);
  expect(Array.isArray(body.positions)).toBe(true);
});

test('4. watchlist API returns 10 tickers', async ({ page }) => {
  const res = await page.request.get('/api/watchlist');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body)).toBe(true);
  expect(body.length).toBe(10);
  const tickers = body.map((r: { ticker: string }) => r.ticker);
  expect(tickers).toContain('AAPL');
});

test('5. health check', async ({ page }) => {
  const res = await page.request.get('/api/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe('ok');
});

test('6. buy trade executes correctly', async ({ page }) => {
  const before = await (await page.request.get('/api/portfolio')).json();

  const buy = await page.request.post('/api/portfolio/trade', {
    data: { ticker: 'AAPL', quantity: 1, side: 'buy' },
  });
  expect(buy.status()).toBe(200);

  const after = await (await page.request.get('/api/portfolio')).json();
  expect(after.cash).toBeLessThan(before.cash);
  const aapl = after.positions.find((p: { ticker: string }) => p.ticker === 'AAPL');
  expect(aapl).toBeTruthy();
  expect(aapl.quantity).toBeGreaterThanOrEqual(1);

  // Cleanup: sell the share back
  const sell = await page.request.post('/api/portfolio/trade', {
    data: { ticker: 'AAPL', quantity: 1, side: 'sell' },
  });
  expect(sell.status()).toBe(200);
});

test('7. trade rejected for insufficient cash', async ({ page }) => {
  const res = await page.request.post('/api/portfolio/trade', {
    data: { ticker: 'AAPL', quantity: 999999, side: 'buy' },
  });
  expect(res.status()).toBe(400);
});

test('8. trade rejected for non-watchlist ticker', async ({ page }) => {
  const res = await page.request.post('/api/portfolio/trade', {
    data: { ticker: 'INVALID', quantity: 1, side: 'buy' },
  });
  expect(res.status()).toBe(400);
});

test('9. AI chat with mock LLM', async ({ page }) => {
  const res = await page.request.post('/api/chat', {
    data: { message: 'Hello, how is my portfolio?' },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(typeof body.message).toBe('string');
  expect(body.message.length).toBeGreaterThan(0);
  expect(Array.isArray(body.trades)).toBe(true);
  expect(Array.isArray(body.watchlist_changes)).toBe(true);
});

test('10. portfolio history endpoint', async ({ page }) => {
  const res = await page.request.get('/api/portfolio/history');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body)).toBe(true);
});

test('11. SSE stream delivers prices', async ({ page }) => {
  await page.goto('/');
  await waitForPrices(page);
  await page.waitForTimeout(5000);
  const res = await page.request.get('/api/watchlist');
  const body = await res.json();
  const aapl = body.find((r: { ticker: string }) => r.ticker === 'AAPL');
  expect(aapl).toBeTruthy();
  expect(aapl.price).toBeGreaterThan(0);
});

test('12. watchlist add rejected for simulator-unsupported ticker', async ({ page }) => {
  const res = await page.request.post('/api/watchlist', {
    data: { ticker: 'PYPL' },
  });
  expect(res.status()).toBe(400);
});
