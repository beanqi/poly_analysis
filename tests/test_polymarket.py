import time

import httpx
import pytest

from app.polymarket import PolymarketClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://gamma-api.polymarket.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"http {self.status_code}",
                request=request,
                response=response,
            )

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        for predicate, response in self.handlers:
            if predicate(url, params):
                return response
        return FakeResponse(404, {})


@pytest.mark.anyio
async def test_fetch_active_btc_events_falls_back_to_slug_probing():
    base_ts = int(time.time())
    base_ts -= base_ts % 300
    target_slug = f"btc-updown-5m-{base_ts}"
    target_payload = {
        "id": "345100",
        "slug": target_slug,
        "title": "Bitcoin Up or Down - April 5, 10:45PM-10:50PM ET",
        "markets": [
            {
                "id": "1870700",
                "conditionId": "0xcond",
                "question": "Bitcoin Up or Down - April 5, 10:45PM-10:50PM ET",
                "outcomes": "[\"Up\", \"Down\"]",
                "clobTokenIds": "[\"yes-token\", \"no-token\"]",
                "startDate": "2026-04-06T02:45:00Z",
                "endDate": "2026-04-06T02:50:00Z",
                "active": True,
                "closed": False,
            }
        ],
    }

    client = PolymarketClient(
        gamma_url="https://gamma-api.polymarket.com",
        data_api_url="https://data-api.polymarket.com",
    )
    client._client = FakeAsyncClient(
        handlers=[
            (
                lambda url, params: url.endswith("/events")
                and params == {"active": "true", "closed": "false", "limit": "500"},
                FakeResponse(200, []),
            ),
            (
                lambda url, params: url.endswith(f"/events/slug/{target_slug}"),
                FakeResponse(200, target_payload),
            ),
        ]
    )

    events = await client.fetch_active_btc_events()

    assert [event.event_slug for event in events] == [target_slug]
    assert events[0].start_ts == base_ts
    assert any(
        call[0].endswith(f"/events/slug/{target_slug}")
        for call in client._client.calls
    )
