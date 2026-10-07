"""mmtools - status"""

import asyncio
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from logging import debug, warning
from typing import cast

import requests
import urllib3
from pydantic import Field

from mmtools import arguments
from mmtools.mattermost import Channel, Mattermost


class Config(arguments.Config):
    channel_color: str = Field(
        "#689d6a",
        description="Color to use if unread group messages",
    )
    user_color: str = Field(
        "#fb4934", description="Color to use if unread user messages"
    )
    sleep: int = Field(
        30,
        description="Time to sleep between updates for polybar",
    )


def init_mattermost(args: Config, error: Callable[[Config, str], None]) -> Mattermost:
    while True:
        try:
            return Mattermost(args)
        except requests.exceptions.ReadTimeout as e:
            error(args, f"Timeout {e}")
            time.sleep(5)
        except (
            requests.exceptions.ConnectionError,
            urllib3.exceptions.NewConnectionError,
        ):
            error(args, "Connection error")
            time.sleep(5)
        except Exception as e:
            error(args, f"Unknown exception: {e}")
            sys.exit(1)


def _load_status_channels(
    args: Config,
    mm: Mattermost,
    error: Callable[[Config, str], None],
    *,
    verify_direct: bool = False,
    channel_ids: frozenset[str] = frozenset(),
) -> list[Channel] | None:
    try:
        channels = mm.init_channels(
            verify_direct=verify_direct, channel_ids=channel_ids
        )
        return [
            channel
            for channel in channels.channels
            if channel.msg_unread_count
            and not (args.ignore and re.search(args.ignore, channel.name))
        ]
    except requests.exceptions.ReadTimeout:
        error(args, "Timeout")
    except (
        requests.exceptions.ConnectionError,
        urllib3.exceptions.NewConnectionError,
    ):
        error(args, "Connection error")
    except Exception as e:
        error(args, f"Unknown error: {e}")

    return None


def _format_status(channels: list[Channel]) -> tuple[list[str], list[str]]:
    private: list[str] = []
    other: list[str] = []
    for channel in sorted(
        channels, key=lambda channel: (channel.display_name or "", channel.id or "")
    ):
        target = private if channel.type == "D" else other
        target.append(f"{channel.display_name}:{channel.msg_unread_count}")
    return private, other


def get_status(
    args: Config,
    mm: Mattermost,
    error: Callable[[Config, str], None],
    *,
    verify_direct: bool = False,
    channel_ids: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str], bool]:
    channels = _load_status_channels(
        args, mm, error, verify_direct=verify_direct, channel_ids=channel_ids
    )
    if channels is None:
        return [], [], False
    private, other = _format_status(channels)
    return private, other, True


def i3blocks_fatal(args: Config, message: str) -> None:
    msg = f"{args.chat_prefix.strip()} {message}"
    print(f"{msg}\n{msg}\n#FF0000")
    sys.exit(0)


def i3blocks() -> None:
    """Output channel status in i3blocks format"""

    args: Config = cast(Config, arguments.handle_args(Config, "mmstatus"))
    mm = init_mattermost(args, error=i3blocks_fatal)

    (private, other, _) = get_status(args, mm, error=i3blocks_fatal)

    out = args.chat_prefix

    # Join all channels with pipe
    msg = " | ".join(other + private)

    # If we have prefix and output - insert space between prefix and output
    if msg and args.chat_prefix:
        msg = " " + msg

    print(out + msg)
    print(out + msg)

    if private:
        print(args.user_color)
    elif other:
        print(args.channel_color)


def polybar_error(args: Config, message: str) -> None:
    print(f"%{{F{args.channel_color}}}{args.chat_prefix} {message}")


def polybar() -> None:
    """Output channel status in polybar format"""

    args: Config = cast(Config, arguments.handle_args(Config, "mmstatus"))

    ok = False

    while True:
        if not ok:
            mm = init_mattermost(args, error=polybar_error)

        (private, other, ok) = get_status(args, mm, polybar_error)

        if not ok:
            time.sleep(args.sleep)
            continue

        private = [f"%{{F{args.user_color}}}{channel}" for channel in private]
        other = [f"%{{F{args.channel_color}}}{channel}" for channel in other]

        if other:
            out = f"%{{F{args.channel_color}}}{args.chat_prefix}"
        elif private:
            out = f"%{{F{args.user_color}}}{args.chat_prefix}"
        else:
            out = args.chat_prefix

        # Join all channels with pipe
        msg = " | ".join(other + private)

        # If we have prefix and output - insert space between prefix and output
        if msg and args.chat_prefix:
            msg = " " + msg

        print(out + msg)
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        time.sleep(args.sleep)


def waybar_error(args: Config, message: str) -> None:
    warning("Mattermost initialization failed: %s", message)
    print(json.dumps({"text": message, "class": "error"}), flush=True)


@dataclass
class _RetainedDirectMessage:
    channel: Channel
    read_since: float | None = None


class WaybarStatusWriter:
    """Write changed status, retaining read DMs and successful text on failure."""

    read_retention = 30

    def __init__(self, args: Config, mm: Mattermost) -> None:
        self.args = args
        self.mm = mm
        self.last_good: dict[str, str] | None = None
        self.previous_output: str | None = None
        self.direct_messages: dict[str, _RetainedDirectMessage] = {}

    def _retain_direct_messages(self, channels: list[Channel]) -> list[Channel]:
        now = time.monotonic()
        unread_ids: set[str] = set()
        other: list[Channel] = []
        for channel in channels:
            if channel.type == "D":
                channel_id = channel.id or channel.name
                unread_ids.add(channel_id)
                self.direct_messages[channel_id] = _RetainedDirectMessage(
                    channel.model_copy()
                )
            else:
                other.append(channel)

        for channel_id, retained in list(self.direct_messages.items()):
            if channel_id not in unread_ids:
                if retained.read_since is None:
                    retained.read_since = now
                if now - retained.read_since >= self.read_retention:
                    del self.direct_messages[channel_id]

        return other + [entry.channel for entry in self.direct_messages.values()]

    def refresh(self, channel_ids: frozenset[str] = frozenset()) -> bool:
        message = "Unable to refresh Mattermost"

        def error(args: Config, detail: str) -> None:
            nonlocal message
            message = detail
            warning("Mattermost status refresh failed: %s", detail)

        channels = _load_status_channels(
            self.args, self.mm, error, verify_direct=True, channel_ids=channel_ids
        )
        payload: dict[str, str | list[str]]
        if channels is not None:
            private, other = _format_status(self._retain_direct_messages(channels))
            # Keep DM names visible when Waybar truncates the text.
            channel_status = " | ".join(private + other)
            message = self.args.chat_prefix
            if channel_status:
                message += f" {channel_status}"
            self.last_good = {
                "text": message,
                "class": "private" if private else "other",
            }
            payload = dict(self.last_good)
        elif self.last_good is not None:
            payload = {
                **self.last_good,
                "class": [self.last_good["class"], "stale"],
                "tooltip": message,
            }
        else:
            payload = {"text": message, "class": "error"}

        output = json.dumps(payload)
        if output != self.previous_output:
            debug("Mattermost status changed: %s", output)
            print(output, flush=True)
        self.previous_output = output
        return channels is not None


class WaybarRefreshWorker:
    """Serialize HTTP refreshes without blocking websocket event reception."""

    def __init__(
        self,
        refresh: Callable[[frozenset[str]], bool],
        *,
        debounce: float = 0.25,
        interval: float = 30,
    ) -> None:
        self.refresh = refresh
        self.debounce = debounce
        self.interval = interval
        self.pending = asyncio.Event()
        self.channel_ids: set[str] = set()

    def request(self, channel_ids: frozenset[str] = frozenset()) -> None:
        """Queue an update, retaining events received during an HTTP request."""
        self.channel_ids.update(channel_ids)
        self.pending.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_periodic = loop.time()

        while True:
            delay = max(0, next_periodic - loop.time())
            if delay:
                try:
                    await asyncio.wait_for(self.pending.wait(), delay)
                    # Coalesce bursts without delaying the periodic refresh.
                    await asyncio.sleep(
                        min(self.debounce, max(0, next_periodic - loop.time()))
                    )
                except TimeoutError:
                    pass

            channel_ids, self.channel_ids = self.channel_ids, set()
            self.pending.clear()
            now = loop.time()
            if now >= next_periodic:
                next_periodic = now + self.interval

            if not await asyncio.to_thread(self.refresh, frozenset(channel_ids)):
                # Retry these IDs on the next event or periodic refresh.
                self.channel_ids.update(channel_ids)


def _channel_id(value: object) -> str | None:
    """Read a channel ID from an event object or embedded JSON string."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict) and isinstance(
        channel_id := value.get("channel_id"), str
    ):
        return channel_id or None
    return None


class WaybarEventHandler:
    """Refresh Waybar when a websocket event can change unread state."""

    refresh_events = frozenset(
        {
            "hello",
            "posted",
            "channel_viewed",
            "multiple_channels_viewed",
            "direct_added",
            "channel_member_updated",
        }
    )

    def __init__(self, refresh: Callable[[frozenset[str]], None]) -> None:
        self.refresh = refresh

    async def __call__(self, event: str) -> None:
        try:
            payload = json.loads(event)
        except (json.JSONDecodeError, TypeError):
            warning("Ignoring malformed Mattermost websocket event")
            return

        if isinstance(payload, dict) and payload.get("event") in self.refresh_events:
            channel_ids: set[str] = set()
            data = payload.get("data", {})
            if isinstance(data, dict):
                for value in (
                    data,
                    data.get("post"),
                    data.get("channelMember"),
                    data.get("channel_member"),
                ):
                    if channel_id := _channel_id(value):
                        channel_ids.add(channel_id)
                times = data.get("channel_times", {})
                if isinstance(times, dict):
                    channel_ids.update(key for key in times if isinstance(key, str))
            if channel_id := _channel_id(payload.get("broadcast")):
                channel_ids.add(channel_id)
            channel_ids.discard("")
            debug("Queued Mattermost status refresh: %s", payload["event"])
            self.refresh(frozenset(channel_ids))


async def stream_waybar(args: Config, mm: Mattermost) -> None:
    """Run event reception and a single refresh worker with shared lifetime."""
    writer = WaybarStatusWriter(args, mm)
    worker = WaybarRefreshWorker(writer.refresh)
    tasks = [
        asyncio.create_task(worker.run()),
        asyncio.create_task(mm.listen(WaybarEventHandler(worker.request))),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def waybar() -> None:
    """Stream channel status updates in Waybar's JSON format."""

    args: Config = cast(Config, arguments.handle_args(Config, "mmstatus"))

    mm = init_mattermost(args, error=waybar_error)
    try:
        asyncio.run(stream_waybar(args, mm))
    except KeyboardInterrupt:
        pass


def main() -> None:
    """For backwards compatibility"""
    i3blocks()
