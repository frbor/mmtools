"""Tests for streamed unread status and reconciliation."""

import asyncio
import json
import ssl
import threading
from unittest.mock import AsyncMock, Mock

import pytest
import requests
from mattermostdriver import Driver  # type: ignore[import-untyped]
from pydantic import SecretStr

from mmtools import arguments, status
from mmtools.mattermost import Channel, Channels, Mattermost
from mmtools.status import WaybarEventHandler, WaybarRefreshWorker, WaybarStatusWriter


@pytest.fixture
def args() -> status.Config:
    return status.Config(
        server="localhost",
        user="me",
        password=SecretStr("test"),
        chat_prefix="MM",
        ignore=None,
        logfile=None,
        team=None,
        password_pass_entry=None,
    )


def unread_channel(name: str = "alice", kind: str = "D") -> Channel:
    return Channel(
        id=name,
        type=kind,
        name=name,
        display_name=name,
        header="",
        purpose="",
        mention_count=0,
        msg_count=0,
        update_at=0,
        last_post_at=0,
        total_msg_count=1,
    )


def test_waybar_event_handler_retains_affected_channels() -> None:
    refresh = Mock()
    handler = WaybarEventHandler(refresh)
    events = [
        {"event": "posted", "data": {"post": json.dumps({"channel_id": "dm"})}},
        {"event": "channel_viewed", "data": {"channel_id": "dm"}},
        {"event": "multiple_channels_viewed", "data": {"channel_times": {"dm": 123}}},
        {
            "event": "channel_member_updated",
            "data": {"channelMember": json.dumps({"channel_id": "dm"})},
        },
        {"event": "direct_added", "broadcast": {"channel_id": "dm"}},
    ]
    for event in events:
        asyncio.run(handler(json.dumps(event)))
    asyncio.run(handler('{"event": "typing"}'))
    for call in refresh.call_args_list:
        assert call.args[0] == frozenset({"dm"})
    assert refresh.call_count == len(events)


@pytest.mark.parametrize("event", ["not JSON", "[]"])
def test_waybar_event_handler_tolerates_malformed_event(event: str) -> None:
    refresh = Mock()
    asyncio.run(WaybarEventHandler(refresh)(event))
    refresh.assert_not_called()


def test_waybar_event_handler_tolerates_malformed_post() -> None:
    refresh = Mock()
    asyncio.run(
        WaybarEventHandler(refresh)(
            '{"event": "posted", "data": {"post": "invalid JSON"}}'
        )
    )
    refresh.assert_called_once_with(frozenset())


def test_waybar_status_preserves_text_and_recovers(
    args: status.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    mm = Mattermost.__new__(Mattermost)
    mm.init_channels = Mock(  # type: ignore[method-assign]
        side_effect=[
            Channels(channels=[unread_channel()]),
            requests.exceptions.ReadTimeout(),
            requests.exceptions.ReadTimeout(),
            Channels(channels=[unread_channel()]),
            Channels(),
        ]
    )
    writer = WaybarStatusWriter(args, mm)
    assert [writer.refresh() for _ in range(5)] == [True, False, False, True, True]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output == [
        {"text": "MM alice:1", "class": "private"},
        {"text": "MM alice:1", "class": ["private", "stale"], "tooltip": "Timeout"},
        {"text": "MM alice:1", "class": "private"},
        {"text": "MM", "class": "other"},
    ]


def test_waybar_initial_failure_shows_error(
    args: status.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    mm = Mattermost.__new__(Mattermost)
    mm.init_channels = Mock(side_effect=requests.exceptions.ReadTimeout())  # type: ignore[method-assign]
    assert not WaybarStatusWriter(args, mm).refresh()
    assert json.loads(capsys.readouterr().out) == {"text": "Timeout", "class": "error"}


def test_waybar_order_is_stable_and_direct_messages_come_first(
    args: status.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    mm = Mattermost.__new__(Mattermost)
    channels = [
        unread_channel("zebra"),
        unread_channel("Town Square", "O"),
        unread_channel(),
    ]
    mm.init_channels = Mock(  # type: ignore[method-assign]
        side_effect=[
            Channels(channels=channels),
            Channels(channels=list(reversed(channels))),
        ]
    )
    writer = WaybarStatusWriter(args, mm)
    writer.refresh()
    writer.refresh()
    assert json.loads(capsys.readouterr().out) == {
        "text": "MM alice:1 | zebra:1 | Town Square:1",
        "class": "private",
    }


def test_worker_preserves_events_during_slow_refresh_and_coalesces_bursts() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        results: asyncio.Queue[frozenset[str]] = asyncio.Queue()
        first = True

        def refresh(ids: frozenset[str]) -> bool:
            nonlocal first
            if first:
                first = False
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(2):
                    raise TimeoutError("Test did not release HTTP request")
            loop.call_soon_threadsafe(results.put_nowait, ids)
            return True

        worker = WaybarRefreshWorker(refresh, debounce=0.005)
        task = asyncio.create_task(worker.run())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            handler = WaybarEventHandler(worker.request)
            await asyncio.wait_for(
                handler('{"event": "posted", "data": {"channel_id": "dm"}}'), 1
            )
            await handler(
                '{"event": "channel_viewed", "data": {"channel_id": "other"}}'
            )
            release.set()
            await asyncio.wait_for(results.get(), 2)
            assert await asyncio.wait_for(results.get(), 2) == frozenset(
                {"dm", "other"}
            )
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_worker_periodically_repairs_missed_events() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        results: asyncio.Queue[bool] = asyncio.Queue()
        unread = False

        def refresh(ids: frozenset[str]) -> bool:
            loop.call_soon_threadsafe(results.put_nowait, unread)
            return True

        worker = WaybarRefreshWorker(refresh, interval=0.01)
        task = asyncio.create_task(worker.run())
        try:
            assert await asyncio.wait_for(results.get(), 2) is False
            unread = True
            assert await asyncio.wait_for(results.get(), 2) is True
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_stream_recovers_failed_channel_on_periodic_refresh_and_cleans_up(
    args: status.Config,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mm = Mattermost.__new__(Mattermost)
    mm.init_channels = Mock(  # type: ignore[method-assign]
        side_effect=[
            Channels(channels=[unread_channel()]),
            requests.exceptions.ReadTimeout(),
            Channels(channels=[unread_channel()]),
        ]
    )

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        outputs: asyncio.Queue[tuple[frozenset[str], bool]] = asyncio.Queue()

        class RecordingWriter(WaybarStatusWriter):
            def refresh(self, channel_ids: frozenset[str] = frozenset()) -> bool:
                ok = super().refresh(channel_ids)
                loop.call_soon_threadsafe(outputs.put_nowait, (channel_ids, ok))
                return ok

        async def listen(handler: WaybarEventHandler) -> None:
            assert (await asyncio.wait_for(outputs.get(), 2))[1]
            await handler('{"event": "posted", "data": {"channel_id": "dm"}}')
            assert await asyncio.wait_for(outputs.get(), 2) == (
                frozenset({"dm"}),
                False,
            )
            assert await asyncio.wait_for(outputs.get(), 2) == (frozenset({"dm"}), True)

        monkeypatch.setattr(status, "WaybarStatusWriter", RecordingWriter)
        monkeypatch.setattr(
            status,
            "WaybarRefreshWorker",
            lambda refresh: WaybarRefreshWorker(refresh, debounce=0, interval=0.05),
        )
        monkeypatch.setattr(mm, "listen", listen)
        await status.stream_waybar(args, mm)
        assert not [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]

    asyncio.run(scenario())
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [entry["text"] for entry in output] == ["MM alice:1"] * 3
    assert output[1]["class"] == ["private", "stale"]
    assert output[-1]["class"] == "private"


def test_waybar_ignores_keyboard_interrupt(
    args: status.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(status, "init_mattermost", Mock(return_value=Mock()))
    monkeypatch.setattr(arguments, "handle_args", Mock(return_value=args))
    stream = AsyncMock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(status, "stream_waybar", stream)
    status.waybar()
    stream.assert_awaited_once()


@pytest.mark.parametrize("verify", [True, False])
def test_async_listener_dispatches_events_over_client_tls(
    monkeypatch: pytest.MonkeyPatch, verify: bool
) -> None:
    mm = Mattermost.__new__(Mattermost)
    mm.api = Driver({"url": "localhost", "token": "test", "verify": verify})
    events = iter(
        [
            '{"event": "hello", "seq": 0}',
            '{"event": "posted"}',
            '{"event": "channel_viewed"}',
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
    refresh = Mock()
    asyncio.run(mm.listen(WaybarEventHandler(refresh)))
    context = connector.call_args.kwargs["ssl"]
    assert isinstance(context, ssl.SSLContext)
    context.wrap_bio(
        ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=False, server_hostname="localhost"
    )
    assert context.check_hostname is verify
    assert context.verify_mode == (ssl.CERT_REQUIRED if verify else ssl.CERT_NONE)
    assert refresh.call_count == 3
    for call in refresh.call_args_list:
        assert call.args == (frozenset(),)
