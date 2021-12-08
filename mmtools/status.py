""" mmtools - status """

import argparse
import json
import re
import sys
import time
from typing import Callable, List, Tuple

import requests
import urllib3

from mmtools import arguments
from mmtools.mattermost import Mattermost


def parseargs() -> argparse.Namespace:
    """Handle arguments"""

    parser = arguments.parseargs("mmstatus")
    parser.add_argument(
        "--channel-color",
        default="#689d6a",
        help="Color to use if unread group messages",
    )
    parser.add_argument(
        "--user-color", default="#fb4934", help="Color to use if unread user messages"
    )
    parser.add_argument(
        "--sleep",
        type=int,
        default=30,
        help="Time to sleep between updates for polybar",
    )

    return arguments.handle_args(parser, "mmstatus")


def init_mattermost(args: argparse.Namespace, error: Callable) -> Mattermost:
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


def get_status(
    args: argparse.Namespace, mm: Mattermost, error: Callable
) -> Tuple[List, List, bool]:
    try:
        channels = mm.init_channels()

        # channel.type == D (Direct)
        private = [
            f"{channel.display_name}:{channel.msg_unread_count}"
            for channel in channels.channels
            if channel.msg_unread_count
            and channel.type == "D"
            and not (args.ignore and re.search(args.ignore, channel.name))
        ]
        other = [
            f"{channel.name}:{channel.msg_unread_count}"
            for channel in channels.channels
            if channel.msg_unread_count
            and channel.type != "D"
            and not (args.ignore and re.search(args.ignore, channel.name))
        ]

        return (private, other, True)
    except requests.exceptions.ReadTimeout:
        error(args, "Timeout")
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError):
        error(args, "Connection error")
    except Exception as e:
        error(args, f"Unknown error: {e}")

    return ([], [], False)


def i3blocks_fatal(args, message):
    msg = f"{args.chat_prefix.strip()} {message}"
    print(f"{msg}\n{msg}\n#FF0000")
    sys.exit(0)


def i3blocks() -> None:
    """Output channel status in i3blocks format"""

    args = parseargs()
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


def polybar_error(args, message):
    print(f"%{{F{args.channel_color}}}{args.chat_prefix} {message}")


def polybar() -> None:
    """Output channel status in i3blocks format"""

    args = parseargs()

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


def waybar_error(args, message):
    print(json.dumps({"text": message, "class": "error"}))


def waybar() -> None:
    """Output channel status in i3blocks format"""

    args = parseargs()

    mm = init_mattermost(args, error=waybar_error)

    (private, other, ok) = get_status(args, mm, waybar_error)

    if private:
        klass = "private"
    else:
        klass = "other"

    # Join all channels with pipe
    msg = f"{args.chat_prefix}" + " | ".join(other + private)

    # If we have prefix and output - insert space between prefix and output
    if msg and args.chat_prefix:
        msg = " " + msg

    print(json.dumps({"text": msg, "class": klass}))
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        pass


def main() -> None:
    """For backwards compatibility"""
    i3blocks()
