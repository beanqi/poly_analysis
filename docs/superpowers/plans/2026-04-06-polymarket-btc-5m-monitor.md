# Polymarket BTC 5m Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python service that continuously discovers active `btc-updown-5m-*` Polymarket events, stores tick trades in SQLite, derives YES/NO candlesticks, and exposes a read-only HTML dashboard with historical win-rate statistics.

**Architecture:** A FastAPI app owns a background collector. The collector polls Gamma for event discovery, listens to the public market WebSocket for low-latency trade notifications, and backfills authoritative fills from the public trades endpoint into SQLite. Analytics are computed from stored trades on demand and served to a static HTML/JS dashboard.

**Tech Stack:** Python 3, FastAPI, httpx, websockets, sqlite3, pytest, vanilla HTML/JS, Lightweight Charts (CDN)

---

### Task 1: Project skeleton and red tests

**Files:**
- Create: `pyproject.toml`
- Create: `tests/test_analytics.py`
- Create: `tests/test_api.py`

- [ ] Add package metadata and test dependencies.
- [ ] Write failing tests for candle aggregation, strategy bucket statistics, and the read-only dashboard API shape.
- [ ] Run `pytest` and confirm the new tests fail because the app code does not exist yet.

### Task 2: Storage and analytics

**Files:**
- Create: `app/db.py`
- Create: `app/models.py`
- Create: `app/analytics.py`
- Create: `app/__init__.py`

- [ ] Implement the SQLite schema and repository methods for events and trades.
- [ ] Implement trade-to-candle aggregation and strategy win-rate analysis.
- [ ] Re-run `pytest` and confirm analytics tests pass.

### Task 3: Polymarket collection service

**Files:**
- Create: `app/config.py`
- Create: `app/polymarket.py`
- Create: `app/collector.py`

- [ ] Implement active BTC 5m event discovery through Gamma.
- [ ] Implement public market WebSocket subscription for tracked token ids.
- [ ] Implement trade backfill through the public trades endpoint with deduped inserts.

### Task 4: Read-only API and dashboard

**Files:**
- Create: `app/api.py`
- Create: `static/index.html`
- Create: `static/app.js`
- Create: `static/styles.css`
- Create: `main.py`

- [ ] Expose JSON endpoints for events, candles, trades, and aggregated strategy statistics.
- [ ] Serve a static dashboard that renders YES/NO candlesticks and the historical win-rate tables.
- [ ] Verify the FastAPI test passes and the app starts locally.

### Task 5: Operational polish

**Files:**
- Create: `README.md`

- [ ] Document setup, run commands, data location, and what the strategy statistics mean.
- [ ] Run the full test suite and a quick startup smoke check.
