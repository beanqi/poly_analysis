import asyncio

import pytest

from app.realtime import RealtimeHub


@pytest.mark.anyio
async def test_realtime_hub_broadcasts_messages_to_subscribers():
    hub = RealtimeHub()
    queue = await hub.subscribe()

    await hub.publish({"type": "refresh", "event_slug": "btc-updown-5m-1000"})
    message = await asyncio.wait_for(queue.get(), timeout=1)

    assert message["type"] == "refresh"
    assert message["event_slug"] == "btc-updown-5m-1000"
    assert "server_ts" in message

    await hub.unsubscribe(queue)
