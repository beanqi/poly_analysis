import sqlite3
import threading
from pathlib import Path
from typing import Iterable, List, Optional

from app.models import EventRecord, TradeRecord


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT NOT NULL,
                    event_slug TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    condition_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL,
                    start_ts INTEGER NOT NULL,
                    end_ts INTEGER NOT NULL,
                    yes_token_id TEXT NOT NULL,
                    no_token_id TEXT NOT NULL,
                    yes_label TEXT NOT NULL,
                    no_label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                );

                CREATE TABLE IF NOT EXISTS trades (
                    trade_key TEXT PRIMARY KEY,
                    event_slug TEXT NOT NULL,
                    condition_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    outcome_index INTEGER NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    size REAL NOT NULL,
                    timestamp INTEGER NOT NULL,
                    transaction_hash TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_time ON events(end_ts DESC, start_ts DESC);
                CREATE INDEX IF NOT EXISTS idx_trades_event_time ON trades(event_slug, timestamp ASC);
                CREATE INDEX IF NOT EXISTS idx_trades_condition_time ON trades(condition_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_trades_asset_time ON trades(asset_id, timestamp ASC);
                """
            )

    def upsert_event(self, event: EventRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, event_slug, market_id, condition_id, title, question,
                    start_ts, end_ts, yes_token_id, no_token_id, yes_label, no_label, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_slug) DO UPDATE SET
                    event_id = excluded.event_id,
                    market_id = excluded.market_id,
                    condition_id = excluded.condition_id,
                    title = excluded.title,
                    question = excluded.question,
                    start_ts = excluded.start_ts,
                    end_ts = excluded.end_ts,
                    yes_token_id = excluded.yes_token_id,
                    no_token_id = excluded.no_token_id,
                    yes_label = excluded.yes_label,
                    no_label = excluded.no_label,
                    status = excluded.status,
                    updated_at = strftime('%s', 'now')
                """,
                (
                    event.event_id,
                    event.event_slug,
                    event.market_id,
                    event.condition_id,
                    event.title,
                    event.question,
                    event.start_ts,
                    event.end_ts,
                    event.yes_token_id,
                    event.no_token_id,
                    event.yes_label,
                    event.no_label,
                    event.status,
                ),
            )

    def update_event_status(self, event_slug: str, status: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE events SET status = ?, updated_at = strftime('%s', 'now') WHERE event_slug = ?",
                (status, event_slug),
            )

    def insert_trades(self, trades: Iterable[TradeRecord]) -> int:
        trade_rows = [
            (
                trade.trade_key,
                trade.event_slug,
                trade.condition_id,
                trade.asset_id,
                trade.outcome,
                trade.outcome_index,
                trade.side,
                trade.price,
                trade.size,
                trade.timestamp,
                trade.transaction_hash,
            )
            for trade in trades
        ]
        if not trade_rows:
            return 0
        with self._lock, self._connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO trades (
                    trade_key, event_slug, condition_id, asset_id, outcome, outcome_index,
                    side, price, size, timestamp, transaction_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                trade_rows,
            )
            return conn.total_changes - before

    def get_event(self, event_slug: str) -> Optional[EventRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE event_slug = ?",
                (event_slug,),
            ).fetchone()
        return _row_to_event(row) if row else None

    def get_event_by_condition(self, condition_id: str) -> Optional[EventRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE condition_id = ?",
                (condition_id,),
            ).fetchone()
        return _row_to_event(row) if row else None

    def list_events(self, limit: int = 100) -> List[EventRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY start_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_events_for_stats(self, now_ts: Optional[int] = None) -> List[EventRecord]:
        query = "SELECT * FROM events WHERE status = 'closed'"
        params = ()
        if now_ts is not None:
            query = (
                "SELECT * FROM events WHERE status = 'closed' OR end_ts <= ?"
            )
            params = (now_ts,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_active_events(self, now_ts: Optional[int] = None) -> List[EventRecord]:
        if now_ts is None:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = 'active' ORDER BY start_ts ASC"
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = 'active' OR end_ts >= ? ORDER BY start_ts ASC",
                    (now_ts,),
                ).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_trades(
        self,
        event_slug: Optional[str] = None,
        condition_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: Optional[int] = None,
        ascending: bool = True,
    ) -> List[TradeRecord]:
        clauses = []
        params = []
        if event_slug is not None:
            clauses.append("event_slug = ?")
            params.append(event_slug)
        if condition_id is not None:
            clauses.append("condition_id = ?")
            params.append(condition_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if outcome is not None:
            clauses.append("LOWER(outcome) = LOWER(?)")
            params.append(outcome)
        where_sql = ""
        if clauses:
            where_sql = "WHERE " + " AND ".join(clauses)
        order_sql = "ASC" if ascending else "DESC"
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM trades {where_sql} ORDER BY timestamp {order_sql}{limit_sql}",
                params,
            ).fetchall()
        return [_row_to_trade(row) for row in rows]

    def count_trades_for_event(self, event_slug: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM trades WHERE event_slug = ?",
                (event_slug,),
            ).fetchone()
        return int(row["count"]) if row else 0

    def count_trades_by_asset(self, event_slug: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT asset_id, COUNT(*) AS count
                FROM trades
                WHERE event_slug = ?
                GROUP BY asset_id
                """,
                (event_slug,),
            ).fetchall()
        return {row["asset_id"]: int(row["count"]) for row in rows}


def _row_to_event(row: sqlite3.Row) -> EventRecord:
    return EventRecord(
        event_id=row["event_id"],
        event_slug=row["event_slug"],
        market_id=row["market_id"],
        condition_id=row["condition_id"],
        title=row["title"],
        question=row["question"],
        start_ts=int(row["start_ts"]),
        end_ts=int(row["end_ts"]),
        yes_token_id=row["yes_token_id"],
        no_token_id=row["no_token_id"],
        yes_label=row["yes_label"],
        no_label=row["no_label"],
        status=row["status"],
    )


def _row_to_trade(row: sqlite3.Row) -> TradeRecord:
    return TradeRecord(
        trade_key=row["trade_key"],
        event_slug=row["event_slug"],
        condition_id=row["condition_id"],
        asset_id=row["asset_id"],
        outcome=row["outcome"],
        outcome_index=int(row["outcome_index"]),
        side=row["side"],
        price=float(row["price"]),
        size=float(row["size"]),
        timestamp=int(row["timestamp"]),
        transaction_hash=row["transaction_hash"],
    )

