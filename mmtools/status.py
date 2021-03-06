""" mmtools - status """

import argparse
import re
import sys
import time
from typing import List, Tuple, Callable

import requests

from . import arguments
from .mattermost import Mattermost


def parseargs() -> argparse.Namespace:
    """ Handle arguments """

    parser = arguments.parseargs("mmstatus")
    parser.add_argument(
        "--channel-color",
        default="#689d6a",
        help="Color to use if unread group messages")
    parser.add_argument(
        "--user-color",
        default="#fb4934",
        help="Color to use if unread user messages")
    parser.add_argument(
        "--sleep",
        type=int,
        default=30,
        help="Time to sleep between updates for polybar")

    return arguments.handle_args(parser, "mmstatus")


def init_mattermost(args: argparse.Namespace, error: Callable) -> Mattermost:
    try:
        return Mattermost(args)
    except requests.exceptions.ReadTimeout:
        error(args, "Timeout")
    except requests.exceptions.ConnectionError:
        error(args, "Connection error")


def get_status(args: argparse.Namespace, mm: Mattermost, error: Callable) -> Tuple[List, List]:
    try:
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
    except requests.exceptions.ReadTimeout:
        error(args, "Timeout")
    except requests.exceptions.ConnectionError:
        error(args, "Connection error")


def i3blocks_fatal(args, message):
    msg = f"{args.chat_prefix.strip()} {message}"
    print(f"{msg}\n{msg}\n#FF0000")
    sys.exit(0)


def i3blocks() -> None:
    """ Output channel status in i3blocks format """

    args = parseargs()
    mm = init_mattermost(args, error=i3blocks_fatal)

    (private, other) = get_status(args, mm, error=i3blocks_fatal)

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


def polybar_fatal(args, message):
    print(f"%{{F{args.channel_color}}}{args.chat_prefix} {message}")
    sys.exit(0)


def polybar() -> None:
    """ Output channel status in i3blocks format """

    args = parseargs()
    mm = init_mattermost(args, error=polybar_fatal)

    while True:
        (private, other) = get_status(args, mm, polybar_fatal)

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
        sys.stdout.flush()
        time.sleep(args.sleep)


def main() -> None:
    """ For backwards compatibility """
    i3blocks()
