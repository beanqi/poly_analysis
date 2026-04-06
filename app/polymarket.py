import hashlib
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from app.models import EventRecord, TradeRecord


class PolymarketClient:
    def __init__(self, gamma_url: str, data_api_url: str):
        self.gamma_url = gamma_url.rstrip("/")
        self.data_api_url = data_api_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                headers={"User-Agent": "poly-analysis/0.1"},
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_active_btc_events(self) -> List[EventRecord]:
        await self.connect()
        events_by_slug = {}
        response = await self._client.get(
            self.gamma_url + "/events",
            params={"active": "true", "closed": "false", "limit": "500"},
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload:
            slug = item.get("slug", "")
            if not slug.startswith("btc-updown-5m-"):
                continue
            event = _parse_event(item)
            if event is not None:
                events_by_slug[event.event_slug] = event

        for slug in _candidate_btc_slugs():
            try:
                event = await self.fetch_event_by_slug(slug)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue
                raise
            if event is not None:
                events_by_slug[event.event_slug] = event

        events = list(events_by_slug.values())
        events.sort(key=lambda event: event.start_ts)
        return events

    async def fetch_event_by_slug(self, slug: str) -> Optional[EventRecord]:
        await self.connect()
        response = await self._client.get(self.gamma_url + f"/events/slug/{slug}")
        response.raise_for_status()
        return _parse_event(response.json())

    async def fetch_recent_trades(
        self,
        event: EventRecord,
        limit: int,
    ) -> List[TradeRecord]:
        await self.connect()
        response = await self._client.get(
            self.data_api_url + "/trades",
            params={"market": event.condition_id, "limit": str(limit)},
        )
        response.raise_for_status()
        payload = response.json()
        trades = []
        for item in payload:
            trade = _parse_trade(item, event)
            if trade is not None:
                trades.append(trade)
        trades.sort(key=lambda trade: trade.timestamp)
        return trades


def _parse_event(item: Dict) -> Optional[EventRecord]:
    markets = item.get("markets") or []
    if not markets:
        return None
    market = markets[0]
    token_ids = _parse_jsonish(market.get("clobTokenIds"))
    outcomes = _parse_jsonish(market.get("outcomes"))
    if not token_ids or len(token_ids) < 2:
        return None
    yes_label = outcomes[0] if outcomes and len(outcomes) >= 1 else "Yes"
    no_label = outcomes[1] if outcomes and len(outcomes) >= 2 else "No"
    slug = str(item.get("slug"))
    start_ts = _parse_btc_bucket_start(slug)
    if start_ts is None:
        start_ts = _parse_ts(market.get("startDate") or item.get("startDate"))
    end_ts = _parse_ts(market.get("endDate") or item.get("endDate"))
    if end_ts == 0 and start_ts:
        end_ts = start_ts + 300
    return EventRecord(
        event_id=str(item.get("id") or market.get("id")),
        event_slug=slug,
        market_id=str(market.get("id")),
        condition_id=str(market.get("conditionId")),
        title=str(item.get("title") or market.get("question") or slug),
        question=str(market.get("question") or item.get("title") or slug),
        start_ts=start_ts,
        end_ts=end_ts,
        yes_token_id=str(token_ids[0]),
        no_token_id=str(token_ids[1]),
        yes_label=str(yes_label),
        no_label=str(no_label),
        status="active" if market.get("active") and not market.get("closed") else "closed",
    )


def _parse_trade(item: Dict, event: EventRecord) -> Optional[TradeRecord]:
    asset_id = str(item.get("asset") or item.get("asset_id") or "")
    if not asset_id:
        return None
    timestamp = _normalize_trade_timestamp(item.get("timestamp"))
    transaction_hash = str(item.get("transactionHash") or item.get("transaction_hash") or "")
    trade_key = _build_trade_key(
        transaction_hash=transaction_hash,
        asset_id=asset_id,
        timestamp=timestamp,
        price=item.get("price"),
        size=item.get("size"),
    )
    return TradeRecord(
        trade_key=trade_key,
        event_slug=event.event_slug,
        condition_id=event.condition_id,
        asset_id=asset_id,
        outcome=str(item.get("outcome") or _guess_outcome_label(asset_id, event)),
        outcome_index=int(item.get("outcomeIndex") or _guess_outcome_index(asset_id, event)),
        side=str(item.get("side") or ""),
        price=float(item.get("price") or 0.0),
        size=float(item.get("size") or 0.0),
        timestamp=timestamp,
        transaction_hash=transaction_hash,
    )


def parse_ws_trade(item: Dict, event: EventRecord) -> Optional[TradeRecord]:
    if item.get("event_type") != "last_trade_price":
        return None
    asset_id = str(item.get("asset_id") or item.get("asset") or "")
    if not asset_id:
        return None
    timestamp = _normalize_trade_timestamp(item.get("timestamp"))
    if event.end_ts and timestamp > event.end_ts * 100:
        timestamp //= 1000
    if timestamp <= 0:
        return None
    transaction_hash = str(
        item.get("transaction_hash") or item.get("transactionHash") or item.get("hash") or ""
    )
    trade_key = _build_trade_key(
        transaction_hash=transaction_hash,
        asset_id=asset_id,
        timestamp=timestamp,
        price=item.get("price"),
        size=item.get("size"),
    )
    return TradeRecord(
        trade_key=trade_key,
        event_slug=event.event_slug,
        condition_id=event.condition_id,
        asset_id=asset_id,
        outcome=_guess_outcome_label(asset_id, event),
        outcome_index=_guess_outcome_index(asset_id, event),
        side=str(item.get("side") or ""),
        price=float(item.get("price") or 0.0),
        size=float(item.get("size") or 0.0),
        timestamp=timestamp,
        transaction_hash=transaction_hash,
    )


def _parse_jsonish(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


def _parse_ts(value: str) -> int:
    if not value:
        return 0
    value = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(value).timestamp())


def _normalize_trade_timestamp(value) -> int:
    if value is None:
        return 0
    timestamp = int(str(value))
    if timestamp > 10_000_000_000:
        return timestamp // 1000
    return timestamp


def _build_trade_key(
    transaction_hash: str,
    asset_id: str,
    timestamp: int,
    price,
    size,
) -> str:
    raw = ":".join(
        [
            transaction_hash or "",
            asset_id,
            str(timestamp),
            str(price),
            str(size),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _guess_outcome_index(asset_id: str, event: EventRecord) -> int:
    return 0 if asset_id == event.yes_token_id else 1


def _guess_outcome_label(asset_id: str, event: EventRecord) -> str:
    return event.yes_label if asset_id == event.yes_token_id else event.no_label


def _candidate_btc_slugs(now_ts: Optional[int] = None) -> List[str]:
    if now_ts is None:
        now_ts = int(time.time())
    base_ts = now_ts - (now_ts % 300)
    slugs = []
    # Probe a small rolling window so we see the current market, recent markets for catch-up,
    # and a few pre-created future markets before the handoff happens.
    for step in range(-2, 7):
        ts = base_ts + (step * 300)
        slugs.append(f"btc-updown-5m-{ts}")
    return slugs


def _parse_btc_bucket_start(slug: str) -> Optional[int]:
    if not slug.startswith("btc-updown-5m-"):
        return None
    value = slug.rsplit("-", 1)[-1]
    if not value.isdigit():
        return None
    return int(value)
