"""mmblocks"""

import logging
import logging.handlers
import os
import socket
import sys
from logging import error, info
from pathlib import Path
from typing import Any, cast

import caep
import passpy
import requests
from pydantic import BaseModel, Field, SecretStr, model_validator
from urllib3.exceptions import InsecureRequestWarning

CONFIG_ID = "mmtools"
CONFIG_NAME = "config"


class ArgumentError(Exception):
    pass


class NotFound(Exception):
    """Item not Found"""

    def __init__(self, *args: Any) -> None:
        Exception.__init__(self, *args)


def fatal(message: str, exit_code: int = 1) -> None:
    """send message to error log and exit"""
    error(message)
    sys.exit(exit_code)


def passpy_store(gpgbinary: str | None = None) -> passpy.store.Store:
    """passpy store"""
    if not gpgbinary:
        gpgbinary = whereis(["gpg2", "gpg"])
        if not gpgbinary:
            raise NotFound("gpg not found")

    return passpy.store.Store(gpg_bin=gpgbinary)


def whereis(filenames: list[str]) -> str | None:
    "Locate file"
    if isinstance(filenames, type(str)):
        filenames = [filenames]

    for filename in filenames:
        for path in os.environ["PATH"].split(":"):
            file = Path(path) / filename
            if file.is_file():
                return str(file)
    return None


def gettpassentry(key: str) -> Any:
    """Get pass entry from passpy"""
    entry = passpy_store().get_key(key)

    if not entry:
        fatal(f"pass entry {key} not found")
    else:
        return entry.split("\n")[0]


def setup_logging(
    loglevel: str = "debug",
    logfile: str | None = None,
    prefix: str = "mmtools",
    maxBytes: int = 10000000,  # 10 MB
    backupCount: int = 5,
) -> None:
    """Setup loglevel and optional log to file"""
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {loglevel}")

    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = "[%(asctime)s] app=" + prefix + " level=%(levelname)s msg=%(message)s"

    if logfile:
        logdir = Path(logfile).parent

        if not logdir.is_dir():
            logdir.mkdir(parents=True)

        # Support strftime in log file names
        handlers = [
            logging.handlers.RotatingFileHandler(
                logfile, maxBytes=maxBytes, backupCount=backupCount
            )
        ]

        logging.basicConfig(
            level=numeric_level, handlers=handlers, format=formatter, datefmt=datefmt
        )
    else:
        logging.basicConfig(
            level=numeric_level, stream=sys.stdout, format=formatter, datefmt=datefmt
        )


class Config(BaseModel):
    server: str = Field(description="Mattermost Server")
    user: str = Field(description="Mattermost User")
    port: int = Field(443, description="Mattermost port")
    ignore: str | None = Field(description="Regular expression of channels to ignore")
    no_verify: bool = Field(False, description="SSL verify")
    logfile: str | None = Field(description="Log to file")
    loglevel: str = Field("info", description="Log level (default=INFO)")
    password: SecretStr | None = Field(description="Mattermost password")
    chat_prefix: str = Field(
        "🗨️ ",
        description="Prefix to show on statusbar and notification messages",
    )
    team: str | None = Field(description="Mattermost team (optional)")
    password_pass_entry: str | None = Field(
        description="pass entry to insert into password"
    )

    @model_validator(mode="before")
    def check_arguments(cls, values: dict[str, Any]) -> dict[str, Any]:
        password = values.get("password")
        password_pass_entry = values.get("password_pass_entry")
        if not (password or password_pass_entry):
            raise ArgumentError("Specify --password or --password-pass-entry")

        return values


def handle_args(model: type[caep.schema.BaseModelType], section: str) -> Config:
    """Verify default arguments"""

    hostname = socket.gethostname()
    hostname_short = socket.gethostname().split(".")[0]

    host_config_name = f"{CONFIG_NAME}-{hostname}"
    host_short_config_name = f"{CONFIG_NAME}-{hostname_short}"

    if (Path(caep.get_config_dir(CONFIG_ID)) / host_config_name).is_file():
        config_name = host_config_name

    elif (Path(caep.get_config_dir(CONFIG_ID)) / host_short_config_name).is_file():
        config_name = host_short_config_name
    else:
        config_name = CONFIG_NAME

    try:
        args: Config = cast(
            Config,
            caep.load(
                model,
                section,
                CONFIG_ID,
                config_name,
                section,
            ),
        )
    except ArgumentError as e:
        fatal(str(e))

    setup_logging(args.loglevel, args.logfile)

    info(f"args: {args}")
    info(f"config: {CONFIG_ID}/{config_name}")

    args.chat_prefix = args.chat_prefix.strip()

    if not args.server:
        fatal("--server not specified")

    if not args.user:
        fatal("--user not specified")

    if args.no_verify:
        requests.packages.urllib3.disable_warnings(  # type: ignore
            category=InsecureRequestWarning
        )

    if args.password_pass_entry:
        args.password = SecretStr(gettpassentry(args.password_pass_entry))

    if not args.password:
        fatal("Must specify either --password or --password-pass-entry")

    return args
