from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    event_slug: str
    market_id: str
    condition_id: str
    title: str
    question: str
    start_ts: int
    end_ts: int
    yes_token_id: str
    no_token_id: str
    status: str
    yes_label: str = "Yes"
    no_label: str = "No"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_slug": self.event_slug,
            "market_id": self.market_id,
            "condition_id": self.condition_id,
            "title": self.title,
            "question": self.question,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "yes_token_id": self.yes_token_id,
            "no_token_id": self.no_token_id,
            "yes_label": self.yes_label,
            "no_label": self.no_label,
            "status": self.status,
        }


@dataclass(frozen=True)
class TradeRecord:
    trade_key: str
    event_slug: str
    condition_id: str
    asset_id: str
    outcome: str
    outcome_index: int
    side: str
    price: float
    size: float
    timestamp: int
    transaction_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_key": self.trade_key,
            "event_slug": self.event_slug,
            "condition_id": self.condition_id,
            "asset_id": self.asset_id,
            "outcome": self.outcome,
            "outcome_index": self.outcome_index,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "timestamp": self.timestamp,
            "transaction_hash": self.transaction_hash,
        }

