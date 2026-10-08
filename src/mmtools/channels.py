"""List joined public and private channels by their latest activity."""

import sys
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mmtools import arguments
from mmtools.mattermost import Mattermost


class Channel(BaseModel):
    """The channel fields needed for a subscription listing."""

    model_config = ConfigDict(strict=True)

    id: str
    type: str
    name: str
    display_name: str | None = None
    last_message_at: int | None = Field(None, ge=0)


class Team(BaseModel):
    """A joined team, identified by its short name."""

    model_config = ConfigDict(strict=True)

    id: str
    name: str


class Post(BaseModel):
    """Post metadata used to distinguish messages from system activity."""

    model_config = ConfigDict(strict=True)

    type: str
    create_at: int = Field(ge=1)
    delete_at: int = Field(ge=0)


class PostPage(BaseModel):
    """Ordered channel posts; the map may also contain thread context."""

    model_config = ConfigDict(strict=True)

    order: list[str]
    posts: dict[str, Post]


def latest_message_at(mm: Mattermost, channel_id: str) -> int | None:
    """Find the newest surviving message, including replies and bot posts."""
    params: dict[str, str | int] = {"per_page": 100, "collapsed_threads": "false"}
    cursors: set[str] = set()
    while True:
        page = PostPage.model_validate(
            mm.api.posts.get_posts_for_channel(channel_id, params=params.copy())
        )
        if not page.order:
            return None
        posts = [page.posts[post_id] for post_id in page.order]
        timestamps = [
            post.create_at
            for post in posts
            if not post.type.startswith("system_") and post.delete_at == 0
        ]
        if timestamps:
            return max(timestamps)
        cursor = page.order[-1]
        if cursor in cursors:
            raise ValueError("Post history pagination did not advance")
        cursors.add(cursor)
        params["before"] = cursor


def get_channels(mm: Mattermost, team: str | None = None) -> list[Channel]:
    """Fetch subscriptions and resolve their latest actual message dates."""
    teams = TypeAdapter(list[Team]).validate_python(mm.teams)
    if team is not None:
        teams = [joined for joined in teams if joined.name == team]
        if not teams:
            raise ValueError(f"Team {team!r} is not among your joined teams")

    channels: list[Channel] = []
    adapter = TypeAdapter(list[Channel])
    for joined in teams:
        response = mm.api.channels.get_channels_for_user(mm.user.id, joined.id)
        channels.extend(
            channel
            for channel in adapter.validate_python(response)
            if channel.type in {"O", "P"}
        )
    for channel in channels:
        channel.last_message_at = latest_message_at(mm, channel.id)
    return channels


def format_channels(channels: list[Channel]) -> list[str]:
    """Render the complete listing using local calendar dates."""
    ordered = sorted(
        channels,
        key=lambda channel: (
            -(channel.last_message_at or 0),
            channel.display_name or channel.name,
            channel.name,
            channel.id,
        ),
    )
    rows: list[str] = []
    for channel in ordered:
        date = (
            datetime.fromtimestamp(channel.last_message_at / 1000).strftime("%Y-%m-%d")
            if channel.last_message_at
            else "never"
        )
        rows.append(f"{date} {channel.display_name or channel.name}")
    return rows


def main() -> None:
    """Print one listing, with errors on stderr and no partial output."""
    try:
        args = arguments.handle_args(arguments.Config, "mmchannels")
        mm = Mattermost(args)
        rows = format_channels(get_channels(mm, args.team))
    except ValidationError:
        sys.stderr.write(
            "mmchannels: Invalid channel, team, or post data from Mattermost\n"
        )
        raise SystemExit(1) from None
    except Exception as error:
        message = " ".join(str(error).splitlines()) or type(error).__name__
        sys.stderr.write(f"mmchannels: {message}\n")
        raise SystemExit(1) from None

    if rows:
        print("\n".join(rows))
