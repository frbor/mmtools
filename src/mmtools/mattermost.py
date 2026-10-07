"""Mattermost module"""

import asyncio
import functools
import ssl
from collections.abc import Awaitable, Callable
from logging import debug, warning
from typing import cast

from mattermostdriver import Driver  # type: ignore
from mattermostdriver.websocket import Websocket  # type: ignore
from pydantic import BaseModel, SecretStr
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from mmtools import arguments


class ClientWebsocket(Websocket):  # type: ignore[misc]
    """Use client TLS with the Mattermost driver's event dispatch."""

    async def connect(self, event_handler: Callable[[str], Awaitable[None]]) -> None:
        # mattermostdriver 7.3 creates a CLIENT_AUTH (server) context, which
        # modern Python cannot use for an outgoing TLS connection.
        context = None
        scheme = "ws"
        if self.options["scheme"] == "https":
            scheme = "wss"
            context = ssl.create_default_context()
            if not self.options["verify"]:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

        url = (
            f"{scheme}://{self.options['url']}:{self.options['port']}"
            f"{self.options['basepath']}/websocket"
        )
        self._alive = True
        while self._alive:
            try:
                async with connect(
                    url, ssl=context, **(self.options["websocket_kw_args"] or {})
                ) as websocket:
                    await self._authenticate_websocket(websocket, event_handler)
                    try:
                        await self._start_loop(websocket, event_handler)
                    except ConnectionClosed:
                        pass
                if not self.options["keepalive"]:
                    break
            except Exception as error:
                warning("Failed to establish websocket connection: %s", error)
            if self._alive:
                await asyncio.sleep(self.options["keepalive_delay"])


class Channel(BaseModel):
    """Mattermost channel model"""

    id: str | None
    type: str | None
    header: str | None
    purpose: str | None
    display_name: str | None
    name: str = ""
    mention_count: int | None
    msg_count: int | None
    update_at: int | None
    last_post_at: int | None
    total_msg_count: int | None
    dirty: bool | None = None
    unread_count: int | None = None

    @property
    def msg_unread_count(self) -> int:
        if self.unread_count is not None:
            return max(0, self.unread_count)
        if self.total_msg_count is None or self.msg_count is None:
            return 0

        return max(0, self.total_msg_count - self.msg_count)


class Mattermost:
    """Mattermost helper class"""

    def __init__(self, args: arguments.Config) -> None:
        self.api = Driver(
            {
                "url": args.server,
                "login_id": args.user,
                "password": cast(SecretStr, args.password).get_secret_value(),
                "scheme": "https",
                "port": args.port,
                "basepath": "/api/v4",
                "verify": not args.no_verify,
                "timeout": 30,
                "request_timeout": 30,
            }
        )

        debug("login()")
        self.api.login()
        debug("get_user_by_username(%s)", args.user)
        self.user = User(**self.api.users.get_user_by_username(args.user))
        debug("Channels()")
        self.channels = Channels()
        debug("get_user_teams(%s", self.user.id)
        self.teams = self.api.teams.get_user_teams(self.user.id)

    @functools.lru_cache(128)
    def get_user(self, user_id: str) -> str:
        """Get username from user_id"""
        debug("get_user(%s)", user_id)
        user = self.api.users.get_user(user_id)

        if user:
            return cast(str, user["username"])
        return "Unknown"

    # Channels is not defined yet, and Channels depends on Mattermost in typing
    # so we need to quote the return definition
    # https://mypy.readthedocs.io/en/latest/kinds_of_types.html#class-name-forward-references
    def init_channels(
        self,
        *,
        verify_direct: bool = False,
        channel_ids: frozenset[str] = frozenset(),
    ) -> "Channels":
        """Initialize channels"""

        debug("channels()")

        self.channels.update(
            self,
            self.user.id,
            self.teams[0]["id"],
            verify_direct=verify_direct,
            channel_ids=channel_ids,
        )

        return self.channels

    def init_websocket(self, func: Callable[[str], Awaitable[None]]) -> None:
        """Initialize websocket"""

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.api.init_websocket(func, websocket_cls=ClientWebsocket)

    async def listen(self, func: Callable[[str], Awaitable[None]]) -> None:
        """Listen in the caller's event loop, alongside background refreshes."""
        self.api.websocket = ClientWebsocket(self.api.options, self.api.client.token)
        await self.api.websocket.connect(func)


class Channels(BaseModel):
    """Channels model Keeps a list of channels"""

    channels: list[Channel] = []

    def update(
        self,
        mm: Mattermost,
        user_id: str,
        team_id: str,
        *,
        verify_direct: bool = False,
        channel_ids: frozenset[str] = frozenset(),
    ) -> None:
        """
        Get list of channels for user. We have to subtract msg_count
        from total_msg_count to get unread message count

        https://mattermost.uservoice.com/forums/306457-general/suggestions/38632564-api-add-new-msg-count-to-users-me-teams-team-i
        """
        channel_members = {
            channel["channel_id"]: channel
            for channel in mm.api.channels.get_channel_members_for_user(
                user_id, team_id
            )
        }

        verify_ids = set(channel_ids)
        if verify_direct:
            verify_ids.update(
                channel.id
                for channel in self.channels
                if channel.type == "D" and channel.id is not None
            )
        raw_channels = {
            channel["id"]: channel
            for channel in mm.api.channels.get_channels_for_user(user_id, team_id)
        }
        if verify_direct:
            for channel_id in verify_ids - raw_channels.keys():
                # A new or previously unread DM may be missing from a stale list.
                channel = mm.api.channels.get_channel(channel_id)
                if channel["type"] == "D":
                    raw_channels[channel_id] = channel

        updated: list[Channel] = []
        for channel_id, raw_channel in raw_channels.items():
            # Merge results from channel_members_for_user and channels_for_user
            member = channel_members.get(channel_id)
            if member is None:
                member = mm.api.channels.get_channel_member(channel_id, user_id)
            channel = Channel(**(raw_channel | member))

            if (
                verify_direct
                and channel.type == "D"
                and (
                    channel_id in verify_ids
                    or channel.msg_unread_count
                    or (
                        channel.total_msg_count is not None
                        and channel.msg_count is not None
                        and channel.total_msg_count < channel.msg_count
                    )
                )
            ):
                unread = mm.api.channels.get_unread_messages(user_id, channel_id)
                channel.unread_count = int(unread["msg_count"])

            if not channel.msg_unread_count:
                continue

            if not channel.display_name and "__" in channel.name:
                # for 1-1 chats, the channel name is "<user_id>__<user_id>" where
                # one of the user1 is yours (probably depends on who opened the
                # private chat we need to check which user id is yours, and then
                # lookup the username of the other user

                user1, user2 = channel.name.split("__")

                if user2 == user_id:
                    channel.display_name = mm.get_user(user1)
                else:
                    channel.display_name = mm.get_user(user2)

            updated.append(channel)

        # Do not discard the last complete snapshot if any request fails.
        self.channels = updated

    def debug(self) -> None:
        """Debug output of channels"""
        for channel in self.channels:
            print(channel)


class User(BaseModel):
    """User model"""

    id: str
    username: str
    first_name: str
    last_name: str
