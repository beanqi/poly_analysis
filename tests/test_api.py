from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Database
from app.models import EventRecord, TradeRecord


def seed(db: Database) -> None:
    event = EventRecord(
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
    db.upsert_event(event)
    db.insert_trades(
        [
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
                asset_id=event.no_token_id,
                outcome="No",
                outcome_index=1,
                side="BUY",
                price=0.17,
                size=7.0,
                timestamp=1_010,
                transaction_hash="0xc",
            ),
        ]
    )


def test_dashboard_endpoints_return_expected_shape(tmp_path):
    db = Database(tmp_path / "app.db")
    seed(db)
    client = TestClient(create_app(database=db, enable_collector=False))

    events_resp = client.get("/api/events")
    assert events_resp.status_code == 200
    events_payload = events_resp.json()
    assert events_payload["events"][0]["event_slug"] == "btc-updown-5m-1000"

    detail_resp = client.get("/api/events/btc-updown-5m-1000")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["event"]["yes_token_id"] == "yes-1"

    trades_resp = client.get("/api/events/btc-updown-5m-1000/trades")
    assert trades_resp.status_code == 200
    assert len(trades_resp.json()["trades"]) == 3

    candles_resp = client.get(
        "/api/events/btc-updown-5m-1000/candles",
        params={"outcome": "Yes", "bucket_seconds": 5},
    )
    assert candles_resp.status_code == 200
    assert candles_resp.json()["candles"][0]["open"] == 0.18

    default_candles_resp = client.get(
        "/api/events/btc-updown-5m-1000/candles",
        params={"outcome": "Yes"},
    )
    assert default_candles_resp.status_code == 200
    default_candles = default_candles_resp.json()["candles"]
    assert len(default_candles) == 299
    assert [candle["time"] for candle in default_candles[:5]] == [
        1001,
        1002,
        1003,
        1004,
        1005,
    ]
    assert default_candles[1]["trade_count"] == 0
    assert default_candles[1]["close"] == 0.18
    assert default_candles[4]["close"] == 0.42

    stats_resp = client.get("/api/stats")
    assert stats_resp.status_code == 200
    stats_payload = stats_resp.json()
    assert stats_payload["meta"]["event_count"] == 1
    assert any(row["buy_threshold_cents"] == 20 for row in stats_payload["rows"])
