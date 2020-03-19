""" Mattermost module """
import argparse
import functools
import re
from typing import Callable, List, Optional, Text, cast

from mattermostdriver import Driver
from pydantic import BaseModel


class Mattermost:

    def __init__(self, args: argparse.Namespace) -> None:

        self.api = Driver({
            'url': args.server,
            'login_id': args.user,
            'password': args.password,
            'scheme': 'https',
            'port': args.port,
            'basepath': '/api/v4',
            'verify': not args.no_verify,
            'timeout': 30,
            'request_timeout': 30,

        })

        self.api.login()
        self.user = User(**self.api.users.get_user_by_username(args.user))
        self.channels = Channels()

    @functools.lru_cache(128)
    def get_user(self, user_id: Text) -> Text:
        """ Get username from user_id """
        user = self.api.users.get_user(user_id)

        if user:
            return cast(Text, user["username"])
        return "Unknown"

    def init_channels(self) -> None:
        """ Initialize channels """

        teams = self.api.teams.get_user_teams(self.user.id)
        self.channels.update(self, self.user.id, teams[0]["id"])

    def i3blocks(
            self,
            ignore: Text,
            channel_color: Text,
            user_color: Text,
            chat_prefix: Text) -> None:
        """ Output channel status in i3blocks format """
        self.channels.i3blocks(ignore, channel_color, user_color, chat_prefix)

    def init_websocket(self, func: Callable) -> None:
        """ Initialize websocket """

        self.api.init_websocket(func)


class Channel(BaseModel):
    """ Mattermost channel model """
    id: Optional[Text]
    type: Optional[Text]
    header: Optional[Text]
    purpose: Optional[Text]
    display_name: Optional[Text]
    name: Text = ""
    mention_count: Optional[int]
    msg_count: Optional[int]
    msg_unread_count: Optional[int]
    update_at: Optional[int]
    last_post_at: Optional[int]
    total_msg_count: Optional[int]
    dirty: Optional[bool]


class Channels(BaseModel):
    """ Channels model Keeps a list of channels """

    channels: List[Channel] = []

    def update(self, mm: Mattermost, user_id: Text, team_id: Text) -> None:
        """
        Get list of channels for user. We have to subtract msg_count
        from total_msg_count to get unread message count

        https://mattermost.uservoice.com/forums/306457-general/suggestions/38632564-api-add-new-msg-count-to-users-me-teams-team-i
        """
        channel_members = {
            channel["channel_id"]: channel
            for channel
            in mm.api.channels.get_channel_members_for_user(user_id, team_id)
        }

        self.channels = []
        for channel in mm.api.channels.get_channels_for_user(user_id, team_id):
            # Merge results from channel_members_for_user and channels_for_user
            channel.update(channel_members[channel["id"]])
            channel = Channel(**channel)

            if not channel.display_name and "__" in channel.name:
                sender, recipient = channel.name.split("__")

                if recipient == user_id:
                    channel.display_name = mm.get_user(sender)
                else:
                    channel.display_name = mm.get_user(recipient)

            channel.msg_unread_count = channel.total_msg_count - channel.msg_count

            self.channels.append(channel)

    def debug(self) -> None:
        """ Debug output of channels """
        for channel in self.channels:
            print(channel)

    def i3blocks(
            self,
            ignore: Text,
            channel_color: Text,
            user_color: Text,
            chat_prefix: Text) -> None:
        """ Output channel status in i3blocks format """

        private = [f"{channel.display_name}:{channel.msg_unread_count}"
                   for channel in self.channels
                   if channel.msg_unread_count and channel.type == "D"
                   and not (ignore and re.search(ignore, channel.name))]
        other = [f"{channel.name}:{channel.msg_unread_count}"
                 for channel in self.channels
                 if channel.msg_unread_count and channel.type != "D"
                 and not (ignore and re.search(ignore, channel.name))]

        out = chat_prefix

        print(out + " | ".join(other + private))
        print(out + " | ".join(other + private))

        if private:
            print(user_color)
        elif other:
            print(channel_color)


class User(BaseModel):
    """ User model """
    id: Text
    username: Text
    first_name: Text
    last_name: Text
