#!/usr/bin/env python3
""" Handle config"""

import os
import sys

import caep
from pkg_resources import resource_string
from pydantic import Field

from mmtools import arguments


class Config(arguments.Config):

    show: bool = Field(False, description="Print default config")
    init: bool = Field(
        False,
        description="Copy default config to {}/{}".format(
            caep.get_config_dir(arguments.CONFIG_ID), arguments.CONFIG_NAME
        ),
    )


def default_ini() -> str:
    """Get content of default ini file"""
    return resource_string("mmtools", f"etc/{arguments.CONFIG_NAME}").decode("utf-8")


def save_config(filename: str) -> None:
    """Save config to specified filename"""
    if os.path.isfile(filename):
        sys.stderr.write(f"Config already exists: {filename}\n")
        sys.exit(1)

    try:
        with open(filename, "w") as f:
            f.write(default_ini())
    except PermissionError as err:
        sys.stderr.write(f"{err}\n")
        sys.exit(2)

    print(f"Config copied to {filename}")


def main() -> None:
    "main function"
    args: Config = arguments.handle_args(Config, "config")

    if args.show:
        print(default_ini())
    elif args.init:
        config_dir = caep.get_config_dir(arguments.CONFIG_ID, create=True)
        save_config(os.path.join(config_dir, arguments.CONFIG_NAME))

    else:
        arguments.fatal("You must specify --show or --init")


if __name__ == "__main__":
    main()
