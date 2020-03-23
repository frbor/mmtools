""" mmtools - status """

import argparse
import re
import sys
from typing import Text

import requests

from . import arguments
from .mattermost import Channels, Mattermost


def parseargs() -> argparse.Namespace:
    """ Handle arguments """

    parser = arguments.parseargs("mmstatus")
    parser.add_argument(
        "--channel-color",
        default="#00FF00",
        help="Color to use if unread group messages")
    parser.add_argument(
        "--user-color",
        default="#FF4488",
        help="Color to use if unread user messages")

    return arguments.handle_args(parser, "mmstatus")


def i3blocks(
        channels: Channels,
        ignore: Text,
        channel_color: Text,
        user_color: Text,
        chat_prefix: Text) -> None:
    """ Output channel status in i3blocks format """

    private = [f"{channel.display_name}:{channel.msg_unread_count}"
               for channel in channels.channels
               if channel.msg_unread_count and channel.type == "D"
               and not (ignore and re.search(ignore, channel.name))]
    other = [f"{channel.name}:{channel.msg_unread_count}"
             for channel in channels.channels
             if channel.msg_unread_count and channel.type != "D"
             and not (ignore and re.search(ignore, channel.name))]

    out = chat_prefix

    # Join all channels with pipe
    msg = " | ".join(other + private)

    # If we have prefix and output - insert space between prefix and output
    if msg and chat_prefix:
        msg = " " + msg

    print(out + msg)
    print(out + msg)

    if private:
        print(user_color)
    elif other:
        print(channel_color)


def main() -> None:
    """ Main module """

    args = parseargs()

    try:
        mm = Mattermost(args)

        i3blocks(
            mm.init_channels(),
            args.ignore,
            args.channel_color,
            args.user_color,
            args.chat_prefix)
    except requests.exceptions.ConnectionError:
        msg = f"{args.chat_prefix.strip()} Connection error"
        print(f"{msg}\n{msg}\n#FF0000")
        sys.exit(0)


if __name__ == "__main__":
    main()
