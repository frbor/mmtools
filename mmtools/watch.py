""" mmtools - watch """

import argparse
import json
import os
import re
import signal
from logging import debug, info
from subprocess import check_output
from typing import Dict, Text

import notify2

from mmtools.mattermost import Mattermost

from . import arguments


def parseargs() -> argparse.Namespace:
    """ Handle arguments """

    parser = arguments.parseargs("mmwatch")

    parser.add_argument(
        "--no-notify", action='store_true', help="Disable notifications")
    parser.add_argument(
        "--pkill", default="i3blocks",
        help="Send SIGUSR1 to process matching value")

    return arguments.handle_args(parser, "mmwatch")


def notify_send(summary: Text, body: Text) -> None:
    """ Send notification message """
    notify2.Notification(summary, body, "notification-message-im").show()


def get_pid(name: Text) -> int:
    """ Get pid from process name """
    return int(check_output(["pidof", "-s", name]))


class EventHandler:
    """ Event Handler """

    def __init__(
            self,
            mm: Mattermost,
            ignore_channels: Text,
            pkill: Text,
            no_notify: bool,
            chat_prefix: Text):

        self.event_map = {
            "posted": self.event_posted,
            "channel_viewed": self.event_channel_viewed,
        }

        self.ignore_channels = ignore_channels
        self.mm = mm
        self.pkill = pkill
        self.no_notify = no_notify
        self.chat_prefix = chat_prefix

    async def event_channel_viewed(self, event: Dict) -> None:
        """ Websocket event handler for channel views """
        data = event.get("data", {})

        channel_id = data.get("channel_id")

        info(json.dumps(data, indent=4, sort_keys=True))

        info(f"channel viewed: {channel_id}")

    async def event_posted(self, event: Dict) -> None:
        """ Websocket event handler for posts """
        data = event["data"]
        post = data.get("post", {})

        # Do not notify on messages sent from myself
        if post.get("user_id") == self.mm.user.id:
            return

        # Do not notify on system join channel/team
        if post.get("type") in ("system_join_channel", "system_join_team"):
            return

        name = data.get("sender_name").rstrip("@")
        channel_name = data.get("channel_name")

        if "__" in channel_name:
            sender_user_id, _ = channel_name.split("__")

            if sender_user_id == self.mm.user.id:
                return

            channel_name = self.mm.get_user(sender_user_id)

        if self.ignore_channels and re.search(self.ignore_channels, channel_name):
            return

        message = post.get("message", "")

        if not self.no_notify:
            notify_send(f"{self.chat_prefix} {channel_name}/{name}", message[:1024])

        if self.pkill:
            pid = get_pid(self.pkill)
            info("kill SIGUSR2 %s (%s)", pid, self.pkill)
            os.kill(pid, signal.SIGUSR2)

    async def event_handler(self, event: Text) -> None:
        """ Websocket event handler """

        debug_event = (
            "status_change",
            "typing",
            "channel_member_updated",
            "user_added",
            None)

        d = json.loads(event)
        if "data" in d:
            for field, value in d["data"].items():
                # Attempt to parse as json in data fields
                if isinstance(field, str):
                    try:
                        d["data"][field] = json.loads(value)
                    except ValueError:
                        pass
                    except TypeError:
                        pass

        event = d.get("event", None)

        if event in self.event_map:
            await self.event_map[event](d)
        elif event in debug_event:
            debug(json.dumps(d, indent=4, sort_keys=True))
        else:
            info(json.dumps(d, indent=4, sort_keys=True))


def main() -> None:
    """ Main module """
    args = parseargs()

    notify2.init('mmtools')

    mm = Mattermost(args)

    handler = EventHandler(mm, args.ignore, args.pkill, args.no_notify, args.chat_prefix)

    mm.init_websocket(handler.event_handler)


if __name__ == "__main__":
    main()
