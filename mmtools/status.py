""" mmtools - status """

import argparse
import requests
import sys

from . import arguments
from .mattermost import Mattermost


def parseargs() -> argparse.Namespace:
    """ Handle arguments """

    parser = arguments.parseargs("mmtools")
    parser.add_argument(
        "--channel-color",
        default="#00FF00",
        help="Color to use if unread group messages")
    parser.add_argument(
        "--user-color",
        default="#FF4488",
        help="Color to use if unread user messages")

    return arguments.handle_args(parser, "mmtools")


def main() -> None:
    """ Main module """

    args = parseargs()

    try:
        mm = Mattermost(args)
        mm.init_channels()

        mm.i3blocks(args.ignore, args.channel_color, args.user_color, args.chat_prefix)
    except requests.exceptions.ConnectionError:
        msg = f"{args.chat_prefix.strip()} Connection error"
        print(f"{msg}\n{msg}\n#FF0000")
        sys.exit(0)


if __name__ == "__main__":
    main()
