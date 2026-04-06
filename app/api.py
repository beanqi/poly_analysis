import logging
import time
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import (
    DEFAULT_BUCKETS,
    DEFAULT_BUY_THRESHOLDS,
    DEFAULT_SELL_THRESHOLDS,
    build_candles,
    compute_strategy_report,
)
from app.collector import CollectorService
from app.config import Settings, load_settings
from app.db import Database
from app.realtime import RealtimeHub


logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def create_app(
    database: Optional[Database] = None,
    settings: Optional[Settings] = None,
    enable_collector: bool = True,
    realtime_hub: Optional[RealtimeHub] = None,
) -> FastAPI:
    settings = settings or load_settings()
    database = database or Database(settings.db_path)
    realtime_hub = realtime_hub or RealtimeHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = database
        app.state.settings = settings
        collector = None
        if enable_collector:
            collector = CollectorService(database, settings, realtime_hub=realtime_hub)
            await collector.start()
        app.state.collector = collector
        app.state.realtime_hub = realtime_hub
        try:
            yield
        finally:
            if collector is not None:
                await collector.stop()

    app = FastAPI(title="Polymarket BTC 5m Dashboard", lifespan=lifespan)
    app.state.db = database
    app.state.settings = settings
    app.state.collector = None
    app.state.realtime_hub = realtime_hub

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "collector_enabled": enable_collector,
            "timestamp": int(time.time()),
        }

    @app.get("/api/events")
    def list_events(limit: int = Query(50, ge=1, le=500)):
        events = app.state.db.list_events(limit=limit)
        payload = []
        for event in events:
            counts = app.state.db.count_trades_by_asset(event.event_slug)
            item = event.to_dict()
            item["trade_count"] = sum(counts.values())
            item["yes_trade_count"] = counts.get(event.yes_token_id, 0)
            item["no_trade_count"] = counts.get(event.no_token_id, 0)
            payload.append(item)
        return {"events": payload}

    @app.get("/api/events/{event_slug}")
    def get_event(event_slug: str):
        event = app.state.db.get_event(event_slug)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        counts = app.state.db.count_trades_by_asset(event.event_slug)
        payload = event.to_dict()
        payload["trade_count"] = sum(counts.values())
        payload["yes_trade_count"] = counts.get(event.yes_token_id, 0)
        payload["no_trade_count"] = counts.get(event.no_token_id, 0)
        return {"event": payload}

    @app.get("/api/events/{event_slug}/trades")
    def get_trades(
        event_slug: str,
        outcome: Optional[str] = None,
        limit: int = Query(1000, ge=1, le=5000),
        order: str = Query("asc", pattern="^(asc|desc)$"),
    ):
        event = app.state.db.get_event(event_slug)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        asset_id = _resolve_asset_id(event, outcome)
        trades = app.state.db.list_trades(
            event_slug=event_slug,
            asset_id=asset_id,
            limit=limit,
            ascending=(order == "asc"),
        )
        return {"trades": [trade.to_dict() for trade in trades]}

    @app.get("/api/events/{event_slug}/candles")
    def get_candles(
        event_slug: str,
        outcome: str = Query("Yes"),
        bucket_seconds: int = Query(1, ge=1, le=300),
    ):
        event = app.state.db.get_event(event_slug)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        asset_id = _resolve_asset_id(event, outcome)
        trades = app.state.db.list_trades(event_slug=event_slug, ascending=True)
        candles = build_candles(
            event=event,
            trades=trades,
            asset_id=asset_id,
            bucket_seconds=bucket_seconds,
            now_ts=int(time.time()),
        )
        return {
            "event_slug": event_slug,
            "outcome": outcome,
            "bucket_seconds": bucket_seconds,
            "candles": candles,
        }

    @app.websocket("/ws")
    async def websocket_updates(websocket: WebSocket):
        await websocket.accept()
        queue = await app.state.realtime_hub.subscribe()
        try:
            await websocket.send_json({"type": "connected", "server_ts": int(time.time())})
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping", "server_ts": int(time.time())})
                    continue
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        finally:
            await app.state.realtime_hub.unsubscribe(queue)

    @app.get("/api/stats")
    def get_stats():
        now_ts = int(time.time())
        events = app.state.db.list_events_for_stats(now_ts=now_ts)
        event_slugs = {event.event_slug for event in events}
        trades = [
            trade
            for trade in app.state.db.list_trades(ascending=True)
            if trade.event_slug in event_slugs
        ]
        report = compute_strategy_report(
            events=events,
            trades=trades,
            buy_thresholds=DEFAULT_BUY_THRESHOLDS,
            sell_thresholds=DEFAULT_SELL_THRESHOLDS,
            buckets=DEFAULT_BUCKETS,
            now_ts=now_ts,
        )
        return report

    @app.get("/")
    def root():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def _resolve_asset_id(event, outcome: Optional[str]) -> Optional[str]:
    if outcome is None:
        return None
    value = outcome.strip().lower()
    if value in {"yes", event.yes_label.lower()}:
        return event.yes_token_id
    if value in {"no", event.no_label.lower()}:
        return event.no_token_id
    return None


app = create_app()
