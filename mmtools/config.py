#!/usr/bin/env python3
""" Handle config"""

import argparse
import os
import sys
from typing import Text

import caep
from pkg_resources import resource_string

from mmtools import arguments


def parseargs() -> argparse.Namespace:
    """ Parse arguments """

    parser = argparse.ArgumentParser(
        "mmtools config",
        epilog="""
    show - Print default config

    user - Copy default config to {0}/{1}

""".format(caep.get_config_dir(arguments.CONFIG_ID), arguments.CONFIG_NAME),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('action', nargs=1, choices=["show", "user"])

    return parser.parse_args()


def default_ini() -> Text:
    """ Get content of default ini file """
    return resource_string("mmtools", "etc/{}".format(arguments.CONFIG_NAME)).decode('utf-8')


def save_config(filename: Text) -> None:
    """ Save config to specified filename """
    if os.path.isfile(filename):
        sys.stderr.write("Config already exists: {}\n".format(filename))
        sys.exit(1)

    try:
        with open(filename, "w") as f:
            f.write(default_ini())
    except PermissionError as err:
        sys.stderr.write("{}\n".format(err))
        sys.exit(2)

    print("Config copied to {}".format(filename))


def main() -> None:
    "main function"
    args = parseargs()

    if "show" in args.action:
        print(default_ini())

    if "user" in args.action:
        config_dir = caep.get_config_dir(arguments.CONFIG_ID, create=True)
        save_config(os.path.join(config_dir, arguments.CONFIG_NAME))


if __name__ == '__main__':
    main()
