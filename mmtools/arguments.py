""" mmblocks """

import argparse
import logging
import logging.handlers
import os
import sys
from logging import error, debug
from typing import Any, List, Optional, Text

import caep
import passpy
import requests
from urllib3.exceptions import InsecureRequestWarning

CONFIG_ID = "mmtools"
CONFIG_NAME = "config"


class NotFound(Exception):
    """Item not Found"""

    def __init__(self, *args: Any) -> None:
        Exception.__init__(self, *args)


def fatal(message: Text, exit_code: int = 1) -> None:
    """ send message to error log and exit """
    error(message)
    sys.exit(exit_code)


def passpy_store(gpgbinary: Optional[Text] = None) -> passpy.store.Store:
    """ passpy store """
    if not gpgbinary:
        gpgbinary = whereis(["gpg2", "gpg"])
        if not gpgbinary:
            raise NotFound("gpg not found")

    return passpy.store.Store(gpg_bin=gpgbinary)


def whereis(filenames: List[Text]) -> Optional[Text]:
    "Locate file"
    if isinstance(filenames, type(str)):
        filenames = [filenames]

    for filename in filenames:
        for path in os.environ["PATH"].split(":"):
            if os.path.isfile("%s/%s" % (path, filename)):
                return os.path.realpath("%s/%s" % (path, filename))
    return None


def gettpassentry(key: Text) -> Any:
    """ Get pass entry from passpy """
    return passpy_store().get_key(key).split("\n")[0]


def setup_logging(
        loglevel: Text = "debug",
        logfile: Optional[Text] = None,
        prefix: Text = "mmtools",
        maxBytes: int = 10000000,  # 10 MB
        backupCount: int = 5) -> None:
    """ Setup loglevel and optional log to file """
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)

    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = "[%(asctime)s] app=" + prefix + " level=%(levelname)s msg=%(message)s"

    if logfile:
        # Support strftime in log file names
        handlers = [
            logging.handlers.RotatingFileHandler(
                logfile,
                maxBytes=maxBytes,
                backupCount=backupCount)]

        logging.basicConfig(
            level=numeric_level,
            handlers=handlers,
            format=formatter,
            datefmt=datefmt)
    else:
        logging.basicConfig(
            level=numeric_level,
            stream=sys.stdout,
            format=formatter,
            datefmt=datefmt)


def parseargs(description: Text) -> argparse.ArgumentParser:
    """ Parse arguments """
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=description
    )

    parser.add_argument("--server", help="Mattermost Server")
    parser.add_argument("--user", help="Mattermost User")
    parser.add_argument("--port", type=int, default=443, help="Mattermost port")
    parser.add_argument("--ignore", help="Regular expression of channels to ignore")
    parser.add_argument("--no-verify", action='store_true', help="SSL verify")
    parser.add_argument("--logfile", help="Log to file")
    parser.add_argument("--loglevel", default="info", help="Log level (default=INFO)")
    parser.add_argument("--password", help="Mattermost password")
    parser.add_argument(
        "--chat-prefix",
        default="🗨️ ",
        help="Prefix to show on statusbar and notification messages")
    parser.add_argument("--team", help="Mattermost team (optional)")
    parser.add_argument("--password-pass-entry",
                        help="pass entry to insert into password")

    return parser


def handle_args(parser: argparse.ArgumentParser, section: Text) -> argparse.Namespace:
    """ Verify default arguments """

    args = caep.handle_args(parser, CONFIG_ID, CONFIG_NAME, section)

    setup_logging(args.loglevel, args.logfile)

    debug(args)

    args.chat_prefix = args.chat_prefix.strip()

    if not args.server:
        fatal("--server not specified")

    if not args.user:
        fatal("--user not specified")

    if args.no_verify:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    if args.password_pass_entry:
        args.password = gettpassentry(args.password_pass_entry)

    if not args.password:
        fatal("Must specify either --password or --password-pass-entry")

    return args
