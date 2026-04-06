import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    gamma_url: str = "https://gamma-api.polymarket.com"
    data_api_url: str = "https://data-api.polymarket.com"
    market_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    discovery_interval_seconds: int = 15
    trade_sync_interval_seconds: int = 5
    trade_fetch_limit: int = 500
    ws_reconnect_seconds: int = 5


def load_settings() -> Settings:
    db_path = Path(os.getenv("POLY_DB_PATH", "data/polymarket.sqlite3"))
    return Settings(
        db_path=db_path,
        discovery_interval_seconds=int(
            os.getenv("POLY_DISCOVERY_INTERVAL_SECONDS", "15")
        ),
        trade_sync_interval_seconds=int(
            os.getenv("POLY_TRADE_SYNC_INTERVAL_SECONDS", "5")
        ),
        trade_fetch_limit=int(os.getenv("POLY_TRADE_FETCH_LIMIT", "500")),
        ws_reconnect_seconds=int(os.getenv("POLY_WS_RECONNECT_SECONDS", "5")),
    )

