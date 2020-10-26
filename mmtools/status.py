""" mmtools - status """

import argparse
import re
import sys
from typing import List, Text, Tuple

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


def get_status(args: argparse.Namespace) -> Tuple[List, List]:
    mm = Mattermost(args)
    channels = mm.init_channels()

    # channel.type == D (Direct)
    private = [f"{channel.display_name}:{channel.msg_unread_count}"
               for channel in channels.channels
               if channel.msg_unread_count and channel.type == "D"
               and not (args.ignore and re.search(args.ignore, channel.name))]
    other = [f"{channel.name}:{channel.msg_unread_count}"
             for channel in channels.channels
             if channel.msg_unread_count and channel.type != "D"
             and not (args.ignore and re.search(args.ignore, channel.name))]

    return (private, other)


def i3blocks() -> None:
    """ Output channel status in i3blocks format """

    args = parseargs()

    try:
        (private, other) = get_status(args)
    except requests.exceptions.ConnectionError:
        msg = f"{args.chat_prefix.strip()} Connection error"
        print(f"{msg}\n{msg}\n#FF0000")
        sys.exit(0)

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


def polybar() -> None:
    """ Output channel status in i3blocks format """

    args = parseargs()

    try:
        (private, other) = get_status(args)
    except requests.exceptions.ConnectionError:
        print(f"%{{F#F00}}{args.chat_prefix.strip()} Connection error")
        sys.exit(0)

    out = args.chat_prefix

    private = [f"%{{F{args.user_color}}}{channel}" for channel in private]
    other = [f"%{{F{args.channel_color}}}{channel}" for channel in other]

    # Join all channels with pipe
    msg = " | ".join(other + private)

    # If we have prefix and output - insert space between prefix and output
    if msg and args.chat_prefix:
        msg = " " + msg

    print(out + msg)


def main() -> None:
    """ For backwards compatibility """
    i3blocks()
