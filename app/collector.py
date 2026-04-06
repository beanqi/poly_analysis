import asyncio
import json
import logging
import time
from typing import Dict, Iterable, Optional, Set

import websockets

from app.config import Settings
from app.db import Database
from app.models import EventRecord
from app.polymarket import PolymarketClient, parse_ws_trade


logger = logging.getLogger(__name__)


class CollectorService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.client = PolymarketClient(settings.gamma_url, settings.data_api_url)
        self._tasks = []
        self._stop_event = asyncio.Event()
        self._subscription_version = 0
        self._desired_assets: Set[str] = set()
        self._asset_to_condition: Dict[str, str] = {}
        self._dirty_conditions: Set[str] = set()

    async def start(self) -> None:
        self._stop_event.clear()
        await self.client.connect()
        self._tasks = [
            asyncio.create_task(self._discovery_loop(), name="poly-discovery"),
            asyncio.create_task(self._trade_sync_loop(), name="poly-trade-sync"),
            asyncio.create_task(self._ws_loop(), name="poly-market-ws"),
        ]

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("collector task failed during shutdown")
        self._tasks = []
        await self.client.close()

    async def _discovery_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                events = await self.client.fetch_active_btc_events()
                desired_assets = set()
                asset_to_condition = {}
                active_slugs = set()
                now_ts = int(time.time())
                for event in events:
                    active_slugs.add(event.event_slug)
                    self.db.upsert_event(event)
                    desired_assets.update([event.yes_token_id, event.no_token_id])
                    asset_to_condition[event.yes_token_id] = event.condition_id
                    asset_to_condition[event.no_token_id] = event.condition_id
                    self._dirty_conditions.add(event.condition_id)

                for event in self.db.list_active_events():
                    if event.event_slug not in active_slugs and event.end_ts <= now_ts:
                        self.db.update_event_status(event.event_slug, "closed")

                if desired_assets != self._desired_assets:
                    self._desired_assets = desired_assets
                    self._asset_to_condition = asset_to_condition
                    self._subscription_version += 1
                else:
                    self._asset_to_condition = asset_to_condition
            except Exception:
                logger.exception("event discovery failed")
            await asyncio.sleep(self.settings.discovery_interval_seconds)

    async def _trade_sync_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                conditions = set(self._dirty_conditions)
                self._dirty_conditions.clear()
                now_ts = int(time.time())
                for event in self.db.list_active_events(now_ts=now_ts - 120):
                    if event.end_ts >= now_ts - 120:
                        conditions.add(event.condition_id)
                for condition_id in sorted(conditions):
                    event = self.db.get_event_by_condition(condition_id)
                    if event is None:
                        continue
                    trades = await self.client.fetch_recent_trades(
                        event=event,
                        limit=self.settings.trade_fetch_limit,
                    )
                    self.db.insert_trades(trades)
                    if event.end_ts <= now_ts:
                        self.db.update_event_status(event.event_slug, "closed")
            except Exception:
                logger.exception("trade sync failed")
            await asyncio.sleep(self.settings.trade_sync_interval_seconds)

    async def _ws_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._desired_assets:
                await asyncio.sleep(1)
                continue
            subscription_version = self._subscription_version
            try:
                async with websockets.connect(
                    self.settings.market_ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "market",
                                "assets_ids": sorted(self._desired_assets),
                                "custom_feature_enabled": True,
                            }
                        )
                    )
                    while not self._stop_event.is_set():
                        if subscription_version != self._subscription_version:
                            break
                        try:
                            raw_message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=5,
                            )
                        except asyncio.TimeoutError:
                            continue
                        payload = json.loads(raw_message)
                        self._handle_ws_message(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("market websocket failed; reconnecting")
                await asyncio.sleep(self.settings.ws_reconnect_seconds)

    def _handle_ws_message(self, payload) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._handle_ws_message(item)
            return
        if not isinstance(payload, dict):
            return
        event_type = payload.get("event_type")
        if event_type != "last_trade_price":
            return
        asset_id = str(payload.get("asset_id") or payload.get("asset") or "")
        if not asset_id:
            return
        condition_id = self._asset_to_condition.get(asset_id)
        if condition_id:
            event = self.db.get_event_by_condition(condition_id)
            if event is not None:
                trade = parse_ws_trade(payload, event)
                if trade is not None:
                    self.db.insert_trades([trade])
        if condition_id:
            self._dirty_conditions.add(condition_id)
