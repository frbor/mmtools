"""Tests for status output event handling."""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, Mock

import pytest
from mattermostdriver import Driver  # type: ignore[import-untyped]
from pydantic import SecretStr

from mmtools import arguments, status
from mmtools.mattermost import Channel, Channels, Mattermost
from mmtools.status import WaybarEventHandler


def test_waybar_event_handler_refreshes_for_unread_updates() -> None:
    refresh = Mock()
    handler = WaybarEventHandler(refresh)

    asyncio.run(handler('{"event": "posted"}'))
    asyncio.run(handler('{"event": "channel_viewed"}'))
    asyncio.run(handler('{"event": "typing"}'))

    assert refresh.call_count == 2


def test_waybar_event_handler_ignores_malformed_event() -> None:
    refresh = Mock()

    asyncio.run(WaybarEventHandler(refresh)("not JSON"))

    refresh.assert_not_called()


@pytest.mark.parametrize("verify", [True, False])
def test_waybar_streams_post_and_read_over_client_tls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], verify: bool
) -> None:
    mm = Mattermost.__new__(Mattermost)
    mm.api = Driver({"url": "localhost", "token": "test", "verify": verify})
    unread = Channel(
        id="channel",
        type="O",
        name="town-square",
        display_name="Town Square",
        header="",
        purpose="",
        mention_count=0,
        msg_count=0,
        update_at=0,
        last_post_at=0,
        total_msg_count=1,
    )
    monkeypatch.setattr(
        mm,
        "init_channels",
        Mock(side_effect=[Channels(), Channels(channels=[unread]), Channels()]),
    )
    monkeypatch.setattr(status, "init_mattermost", Mock(return_value=mm))
    monkeypatch.setattr(
        arguments,
        "handle_args",
        Mock(
            return_value=status.Config(
                server="localhost",
                user="test",
                password=SecretStr("test"),
                chat_prefix="MM",
                ignore=None,
                logfile=None,
                team=None,
                password_pass_entry=None,
            )
        ),
    )

    events = iter(
        [
            '{"event": "hello", "seq": 0}',
            '{"event": "posted"}',
            '{"event": "multiple_channels_viewed", "data": {"channel_times": {"channel": 1234}}}',
        ]
    )

    async def receive() -> str:
        if (event := next(events, None)) is not None:
            return event
        mm.api.disconnect()
        return '{"event": "typing"}'

    socket = AsyncMock()
    socket.recv.side_effect = receive
    connection = AsyncMock()
    connection.__aenter__.return_value = socket
    connector = Mock(return_value=connection)
    monkeypatch.setattr("mmtools.mattermost.connect", connector)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        status.waybar()
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    context = connector.call_args.kwargs["ssl"]
    assert isinstance(context, ssl.SSLContext)
    # Exercise Python's client TLS setup: the driver's server context fails here.
    context.wrap_bio(
        ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=False, server_hostname="localhost"
    )
    assert context.check_hostname is verify
    assert context.verify_mode == (ssl.CERT_REQUIRED if verify else ssl.CERT_NONE)
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output == [
        {"text": "MM", "class": "other"},
        {"text": "MM Town Square:1", "class": "other"},
        {"text": "MM", "class": "other"},
    ]
