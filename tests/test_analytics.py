from app.analytics import build_candles, compute_strategy_report
from app.models import EventRecord, TradeRecord


def make_event() -> EventRecord:
    return EventRecord(
        event_id="evt-1",
        event_slug="btc-updown-5m-1000",
        market_id="mkt-1",
        condition_id="cond-1",
        title="BTC Up or Down - 5 Minutes",
        question="BTC Up or Down - 5 Minutes",
        start_ts=1_000,
        end_ts=1_300,
        yes_token_id="yes-1",
        no_token_id="no-1",
        status="closed",
    )


def test_build_candles_groups_trades_into_5_second_bars():
    event = make_event()
    trades = [
        TradeRecord(
            trade_key="a",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.18,
            size=10.0,
            timestamp=1_001,
            transaction_hash="0xa",
        ),
        TradeRecord(
            trade_key="b",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="SELL",
            price=0.42,
            size=12.0,
            timestamp=1_004,
            transaction_hash="0xb",
        ),
        TradeRecord(
            trade_key="c",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.30,
            size=8.0,
            timestamp=1_006,
            transaction_hash="0xc",
        ),
    ]

    candles = build_candles(
        event=event,
        trades=trades,
        asset_id=event.yes_token_id,
        bucket_seconds=5,
    )

    assert candles == [
        {
            "time": 1_000,
            "open": 0.18,
            "high": 0.42,
            "low": 0.18,
            "close": 0.42,
            "volume": 22.0,
            "trade_count": 2,
        },
        {
            "time": 1_005,
            "open": 0.30,
            "high": 0.30,
            "low": 0.30,
            "close": 0.30,
            "volume": 8.0,
            "trade_count": 1,
        },
    ]


def test_build_candles_fills_empty_seconds_with_previous_close():
    event = make_event()
    trades = [
        TradeRecord(
            trade_key="a",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.18,
            size=10.0,
            timestamp=1_001,
            transaction_hash="0xa",
        ),
        TradeRecord(
            trade_key="b",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="SELL",
            price=0.42,
            size=12.0,
            timestamp=1_004,
            transaction_hash="0xb",
        ),
    ]

    candles = build_candles(
        event=event,
        trades=trades,
        asset_id=event.yes_token_id,
        bucket_seconds=1,
        now_ts=1_006,
    )

    assert candles[:5] == [
        {
            "time": 1_001,
            "open": 0.18,
            "high": 0.18,
            "low": 0.18,
            "close": 0.18,
            "volume": 10.0,
            "trade_count": 1,
        },
        {
            "time": 1_002,
            "open": 0.18,
            "high": 0.18,
            "low": 0.18,
            "close": 0.18,
            "volume": 0.0,
            "trade_count": 0,
        },
        {
            "time": 1_003,
            "open": 0.18,
            "high": 0.18,
            "low": 0.18,
            "close": 0.18,
            "volume": 0.0,
            "trade_count": 0,
        },
        {
            "time": 1_004,
            "open": 0.42,
            "high": 0.42,
            "low": 0.42,
            "close": 0.42,
            "volume": 12.0,
            "trade_count": 1,
        },
        {
            "time": 1_005,
            "open": 0.42,
            "high": 0.42,
            "low": 0.42,
            "close": 0.42,
            "volume": 0.0,
            "trade_count": 0,
        },
    ]


def test_build_candles_for_active_event_only_fills_to_now():
    event = EventRecord(
        event_id="evt-2",
        event_slug="btc-updown-5m-2000",
        market_id="mkt-2",
        condition_id="cond-2",
        title="BTC Up or Down - 5 Minutes",
        question="BTC Up or Down - 5 Minutes",
        start_ts=2_000,
        end_ts=2_300,
        yes_token_id="yes-2",
        no_token_id="no-2",
        status="active",
    )
    trades = [
        TradeRecord(
            trade_key="a2",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.25,
            size=5.0,
            timestamp=2_001,
            transaction_hash="0xa2",
        )
    ]

    candles = build_candles(
        event=event,
        trades=trades,
        asset_id=event.yes_token_id,
        bucket_seconds=1,
        now_ts=2_004,
    )

    assert [candle["time"] for candle in candles] == [2001, 2002, 2003]


def test_compute_strategy_report_buckets_success_and_failure():
    event = make_event()
    trades = [
        TradeRecord(
            trade_key="y1",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.19,
            size=5.0,
            timestamp=1_020,
            transaction_hash="0xy1",
        ),
        TradeRecord(
            trade_key="y2",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.yes_token_id,
            outcome="Yes",
            outcome_index=0,
            side="BUY",
            price=0.41,
            size=5.0,
            timestamp=1_040,
            transaction_hash="0xy2",
        ),
        TradeRecord(
            trade_key="n1",
            event_slug=event.event_slug,
            condition_id=event.condition_id,
            asset_id=event.no_token_id,
            outcome="No",
            outcome_index=1,
            side="BUY",
            price=0.18,
            size=5.0,
            timestamp=1_110,
            transaction_hash="0xn1",
        ),
    ]

    report = compute_strategy_report(
        events=[event],
        trades=trades,
        buy_thresholds=[0.2],
        sell_thresholds=[0.4],
        buckets=[
            (0, 60, "0-1m"),
            (60, 120, "1-2m"),
        ],
    )

    yes_row = next(
        row
        for row in report["rows"]
        if row["outcome"] == "Yes" and row["bucket"] == "0-1m"
    )
    no_row = next(
        row
        for row in report["rows"]
        if row["outcome"] == "No" and row["bucket"] == "1-2m"
    )
    combined_row = next(
        row
        for row in report["rows"]
        if row["outcome"] == "Combined" and row["bucket"] == "0-1m"
    )

    assert yes_row["sample_size"] == 1
    assert yes_row["wins"] == 1
    assert yes_row["win_rate"] == 1.0
    assert no_row["sample_size"] == 1
    assert no_row["wins"] == 0
    assert no_row["win_rate"] == 0.0
    assert combined_row["sample_size"] == 1
    assert combined_row["wins"] == 1
