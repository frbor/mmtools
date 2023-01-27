""" Mattermost module """
import functools
from logging import debug
from typing import Callable, List, Optional, cast

from mattermostdriver import Driver
from pydantic import BaseModel, SecretStr

from mmtools import arguments


class Channel(BaseModel):
    """Mattermost channel model"""

    id: Optional[str]
    type: Optional[str]
    header: Optional[str]
    purpose: Optional[str]
    display_name: Optional[str]
    name: str = ""
    mention_count: Optional[int]
    msg_count: Optional[int]
    update_at: Optional[int]
    last_post_at: Optional[int]
    total_msg_count: Optional[int]
    dirty: Optional[bool]

    @property
    def msg_unread_count(self) -> int:
        if self.total_msg_count is None or self.msg_count is None:
            return 0

        return self.total_msg_count - self.msg_count


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
    def init_channels(self) -> "Channels":
        """Initialize channels"""

        debug("channels()")

        self.channels.update(self, self.user.id, self.teams[0]["id"])

        return self.channels

    def init_websocket(self, func: Callable) -> None:  # type: ignore
        """Initialize websocket"""

        self.api.init_websocket(func)


class Channels(BaseModel):
    """Channels model Keeps a list of channels"""

    channels: List[Channel] = []

    def update(self, mm: Mattermost, user_id: str, team_id: str) -> None:
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

        self.channels = []
        for channel in mm.api.channels.get_channels_for_user(user_id, team_id):

            # Merge results from channel_members_for_user and channels_for_user
            channel.update(channel_members[channel["id"]])
            channel = Channel(**channel)

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

            self.channels.append(channel)

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
