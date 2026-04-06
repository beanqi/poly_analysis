from app.analytics import build_candles
from app.collector import CollectorService
from app.config import Settings
from app.db import Database
from app.models import EventRecord


def test_handle_ws_message_accepts_list_payload(tmp_path):
    db = Database(tmp_path / "collector.db")
    service = CollectorService(
        db=db,
        settings=Settings(db_path=tmp_path / "collector.db"),
    )
    service._asset_to_condition = {
        "yes-token": "cond-1",
        "no-token": "cond-1",
    }

    service._handle_ws_message(
        [
            {"event_type": "last_trade_price", "asset_id": "yes-token"},
            {"event_type": "book", "asset_id": "no-token"},
        ]
    )

    assert "cond-1" in service._dirty_conditions


def test_handle_ws_trade_message_inserts_trade_directly(tmp_path):
    db = Database(tmp_path / "collector.db")
    event = EventRecord(
        event_id="evt-1",
        event_slug="btc-updown-5m-1000",
        market_id="mkt-1",
        condition_id="cond-1",
        title="BTC Up or Down - 5 Minutes",
        question="BTC Up or Down - 5 Minutes",
        start_ts=1_000,
        end_ts=1_300,
        yes_token_id="yes-token",
        no_token_id="no-token",
        yes_label="Up",
        no_label="Down",
        status="active",
    )
    db.upsert_event(event)

    service = CollectorService(
        db=db,
        settings=Settings(db_path=tmp_path / "collector.db"),
    )
    service._asset_to_condition = {
        "yes-token": "cond-1",
        "no-token": "cond-1",
    }

    service._handle_ws_message(
        {
            "event_type": "last_trade_price",
            "asset_id": "yes-token",
            "market": "cond-1",
            "price": "0.37",
            "size": "12.5",
            "side": "BUY",
            "timestamp": "1004000",
            "transaction_hash": "0xabc",
        }
    )

    trades = db.list_trades(event_slug=event.event_slug)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.event_slug == event.event_slug
    assert trade.outcome == "Up"
    assert trade.timestamp == 1004
    assert trade.price == 0.37

    candles = build_candles(
        event=event,
        trades=trades,
        asset_id=event.yes_token_id,
        bucket_seconds=1,
    )
    assert candles[0]["time"] == 1004
    assert candles[0]["close"] == 0.37
