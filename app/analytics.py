import math
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from app.models import EventRecord, TradeRecord


DEFAULT_BUY_THRESHOLDS = [0.10, 0.20, 0.30]
DEFAULT_SELL_THRESHOLDS = [0.20, 0.40, 0.60]
DEFAULT_BUCKETS = [
    (0, 60, "0-1m"),
    (60, 120, "1-2m"),
    (120, 180, "2-3m"),
    (180, 240, "3-4m"),
    (240, 300, "4-5m"),
]


def build_candles(
    event: EventRecord,
    trades: Sequence[TradeRecord],
    asset_id: str,
    bucket_seconds: int = 5,
    now_ts: int = None,
) -> List[dict]:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    if now_ts is None:
        now_ts = int(time.time())

    grouped: Dict[int, List[TradeRecord]] = defaultdict(list)
    for trade in sorted(trades, key=lambda item: item.timestamp):
        if trade.asset_id != asset_id:
            continue
        if trade.timestamp < event.start_ts or trade.timestamp > event.end_ts:
            continue
        bucket_time = event.start_ts + (
            ((trade.timestamp - event.start_ts) // bucket_seconds) * bucket_seconds
        )
        grouped[bucket_time].append(trade)

    candles_by_time = {}
    for bucket_time in sorted(grouped):
        bucket_trades = grouped[bucket_time]
        prices = [trade.price for trade in bucket_trades]
        candles_by_time[bucket_time] = {
            "time": bucket_time,
            "open": bucket_trades[0].price,
            "high": max(prices),
            "low": min(prices),
            "close": bucket_trades[-1].price,
            "volume": round(sum(trade.size for trade in bucket_trades), 8),
            "trade_count": len(bucket_trades),
        }

    if bucket_seconds != 1 or not candles_by_time:
        return [candles_by_time[bucket_time] for bucket_time in sorted(candles_by_time)]

    candles = []
    first_bucket_time = min(candles_by_time)
    fill_end = event.end_ts - 1
    if event.status != "closed":
        fill_end = min(fill_end, now_ts - 1)
    last_bucket_time = max(first_bucket_time, fill_end)
    previous_close = None
    for bucket_time in range(first_bucket_time, last_bucket_time + 1):
        candle = candles_by_time.get(bucket_time)
        if candle is None:
            if previous_close is None:
                continue
            candle = {
                "time": bucket_time,
                "open": previous_close,
                "high": previous_close,
                "low": previous_close,
                "close": previous_close,
                "volume": 0.0,
                "trade_count": 0,
            }
        else:
            previous_close = candle["close"]
        candles.append(candle)
        previous_close = candle["close"]
    return candles


def compute_strategy_report(
    events: Sequence[EventRecord],
    trades: Sequence[TradeRecord],
    buy_thresholds: Sequence[float] = DEFAULT_BUY_THRESHOLDS,
    sell_thresholds: Sequence[float] = DEFAULT_SELL_THRESHOLDS,
    buckets: Sequence[Tuple[int, int, str]] = DEFAULT_BUCKETS,
    now_ts: int = None,
) -> dict:
    if now_ts is None:
        now_ts = int(time.time())

    eligible_events = [
        event
        for event in events
        if event.status == "closed" or event.end_ts <= now_ts
    ]

    trades_by_event_asset: Dict[Tuple[str, str], List[TradeRecord]] = defaultdict(list)
    for trade in sorted(trades, key=lambda item: item.timestamp):
        trades_by_event_asset[(trade.event_slug, trade.asset_id)].append(trade)

    counters = {}
    sample_events = set()
    for event in eligible_events:
        for buy_threshold in buy_thresholds:
            for sell_threshold in sell_thresholds:
                if sell_threshold <= buy_threshold:
                    continue
                for bucket_start, bucket_end, bucket_label in buckets:
                    for side_label, asset_id in (
                        ("Yes", event.yes_token_id),
                        ("No", event.no_token_id),
                    ):
                        key = (side_label, bucket_label, buy_threshold, sell_threshold)
                        counters.setdefault(
                            key,
                            {
                                "sample_size": 0,
                                "wins": 0,
                                "losses": 0,
                                "total_hold_seconds": 0,
                            },
                        )
                        result = _simulate_bucket_trade(
                            event=event,
                            trades=trades_by_event_asset.get((event.event_slug, asset_id), []),
                            bucket_start=bucket_start,
                            bucket_end=bucket_end,
                            buy_threshold=buy_threshold,
                            sell_threshold=sell_threshold,
                        )
                        if result is None:
                            continue
                        counters[key]["sample_size"] += 1
                        sample_events.add(event.event_slug)
                        if result["success"]:
                            counters[key]["wins"] += 1
                            counters[key]["total_hold_seconds"] += result["hold_seconds"]
                        else:
                            counters[key]["losses"] += 1

    rows = []
    for buy_threshold in buy_thresholds:
        for sell_threshold in sell_thresholds:
            if sell_threshold <= buy_threshold:
                continue
            for _, _, bucket_label in buckets:
                combined = {"sample_size": 0, "wins": 0, "losses": 0, "total_hold_seconds": 0}
                for side_label in ("Yes", "No"):
                    metrics = counters.get(
                        (side_label, bucket_label, buy_threshold, sell_threshold),
                        {"sample_size": 0, "wins": 0, "losses": 0, "total_hold_seconds": 0},
                    )
                    rows.append(
                        _format_row(
                            outcome=side_label,
                            bucket_label=bucket_label,
                            buy_threshold=buy_threshold,
                            sell_threshold=sell_threshold,
                            metrics=metrics,
                        )
                    )
                    combined["sample_size"] += metrics["sample_size"]
                    combined["wins"] += metrics["wins"]
                    combined["losses"] += metrics["losses"]
                    combined["total_hold_seconds"] += metrics["total_hold_seconds"]
                rows.append(
                    _format_row(
                        outcome="Combined",
                        bucket_label=bucket_label,
                        buy_threshold=buy_threshold,
                        sell_threshold=sell_threshold,
                        metrics=combined,
                    )
                )

    rows.sort(
        key=lambda row: (
            row["buy_threshold_cents"],
            row["sell_threshold_cents"],
            row["bucket_order"],
            0 if row["outcome"] == "Yes" else 1 if row["outcome"] == "No" else 2,
        )
    )

    return {
        "meta": {
            "event_count": len(eligible_events),
            "events_with_samples": len(sample_events),
            "buy_thresholds_cents": [int(round(value * 100)) for value in buy_thresholds],
            "sell_thresholds_cents": [int(round(value * 100)) for value in sell_thresholds],
            "buckets": [label for _, _, label in buckets],
        },
        "rows": rows,
    }


def _simulate_bucket_trade(
    event: EventRecord,
    trades: Sequence[TradeRecord],
    bucket_start: int,
    bucket_end: int,
    buy_threshold: float,
    sell_threshold: float,
) -> dict:
    entry_trade = None
    for trade in trades:
        delta = trade.timestamp - event.start_ts
        if delta < bucket_start or delta >= bucket_end:
            continue
        if trade.price < buy_threshold:
            entry_trade = trade
            break

    if entry_trade is None:
        return None

    for trade in trades:
        if trade.timestamp <= entry_trade.timestamp:
            continue
        if trade.timestamp > event.end_ts:
            break
        if trade.price > sell_threshold:
            return {
                "success": True,
                "hold_seconds": max(trade.timestamp - entry_trade.timestamp, 0),
            }

    return {"success": False, "hold_seconds": 0}


def _format_row(
    outcome: str,
    bucket_label: str,
    buy_threshold: float,
    sell_threshold: float,
    metrics: dict,
) -> dict:
    sample_size = metrics["sample_size"]
    wins = metrics["wins"]
    win_rate = wins / sample_size if sample_size else 0.0
    avg_hold_seconds = (
        metrics["total_hold_seconds"] / wins if wins else None
    )
    return {
        "outcome": outcome,
        "bucket": bucket_label,
        "bucket_order": _bucket_sort_key(bucket_label),
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "buy_threshold_cents": int(round(buy_threshold * 100)),
        "sell_threshold_cents": int(round(sell_threshold * 100)),
        "sample_size": sample_size,
        "wins": wins,
        "losses": metrics["losses"],
        "win_rate": round(win_rate, 4),
        "avg_hold_seconds": (
            None if avg_hold_seconds is None else round(avg_hold_seconds, 2)
        ),
    }


def _bucket_sort_key(bucket_label: str) -> int:
    start = bucket_label.split("m")[0]
    try:
        return int(start.split("-")[0])
    except ValueError:
        return math.inf
