"""Tests for Mattermost integration helpers."""

import asyncio
from unittest.mock import Mock

from mmtools.mattermost import Mattermost


def test_init_websocket_creates_event_loop_when_missing() -> None:
    mattermost = Mattermost.__new__(Mattermost)
    mattermost.api = Mock()
    asyncio.set_event_loop(None)

    try:
        mattermost.init_websocket(Mock())
        mattermost.api.init_websocket.assert_called_once()
        assert asyncio.get_event_loop().is_closed() is False
    finally:
        loop = asyncio.get_event_loop()
        loop.close()
        asyncio.set_event_loop(None)
