"""Handle config"""

import sys
from importlib import resources
from pathlib import Path
from typing import cast

import caep
from pydantic import Field

from mmtools import arguments


class Config(arguments.Config):
    show: bool = Field(False, description="Print default config")
    init: bool = Field(
        False,
        description=f"Copy default config to {caep.get_config_dir(arguments.CONFIG_ID)}/{arguments.CONFIG_NAME}",
    )


def default_ini() -> str:
    """Get content of default ini file"""
    return (
        resources.files("mmtools").joinpath(f"etc/{arguments.CONFIG_NAME}").read_text()
    )


def save_config(filename: Path) -> None:
    """Save config to specified filename"""
    if filename.is_file():
        sys.stderr.write(f"Config already exists: {filename}\n")
        sys.exit(1)

    try:
        with Path(filename).open("w") as f:
            f.write(default_ini())
    except PermissionError as err:
        sys.stderr.write(f"{err}\n")
        sys.exit(2)

    print(f"Config copied to {filename}")


def main() -> None:
    "main function"
    args: Config = cast(Config, arguments.handle_args(Config, "config"))

    if args.show:
        print(default_ini())
    elif args.init:
        config_dir = caep.get_config_dir(arguments.CONFIG_ID, create=True)
        save_config(Path(config_dir) / arguments.CONFIG_NAME)

    else:
        arguments.fatal("You must specify --show or --init")


# if __name__ == "__main__":
#     main()
