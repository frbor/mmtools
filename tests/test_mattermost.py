"""Tests for Mattermost integration helpers."""

import asyncio
from unittest.mock import Mock

import pytest
import requests

from mmtools.mattermost import Channel, Channels, Mattermost, User


@pytest.fixture
def mm() -> Mattermost:
    mattermost = Mattermost.__new__(Mattermost)
    mattermost.api = Mock()
    mattermost.user = User(id="me", username="me", first_name="", last_name="")
    mattermost.teams = [{"id": "team"}]
    mattermost.channels = Channels()
    mattermost.api.channels.get_channel_members_for_user.return_value = [
        {"channel_id": "dm", "msg_count": 0}
    ]
    mattermost.api.channels.get_channel_member.return_value = {
        "channel_id": "dm",
        "msg_count": 0,
    }
    direct = Channel(
        id="dm",
        type="D",
        name="me__alice-id",
        display_name="",
        header="",
        purpose="",
        mention_count=0,
        msg_count=None,
        update_at=0,
        last_post_at=0,
        total_msg_count=1,
    ).model_dump()
    mattermost.api.channels.get_channels_for_user.return_value = [direct]
    mattermost.api.channels.get_channel.return_value = direct
    mattermost.api.channels.get_unread_messages.return_value = {"msg_count": 1}
    mattermost.api.users.get_user.return_value = {"username": "alice"}
    return mattermost


@pytest.mark.parametrize("name", ["me__alice-id", "alice-id__me"])
def test_direct_message_resolves_the_other_user(mm: Mattermost, name: str) -> None:
    mm.api.channels.get_channels_for_user.return_value[0]["name"] = name
    channels = mm.init_channels(verify_direct=True)
    assert channels.channels[0].display_name == "alice"
    mm.api.users.get_user.assert_called_once_with("alice-id")


def test_direct_message_survives_stale_bulk_counts_until_verified_read(
    mm: Mattermost,
) -> None:
    mm.init_channels(verify_direct=True)
    mm.api.channels.get_channels_for_user.return_value[0]["total_msg_count"] = 0
    channels = mm.init_channels(verify_direct=True)
    assert channels.channels[0].msg_unread_count == 1

    mm.api.channels.get_unread_messages.return_value = {"msg_count": 0}
    assert not mm.init_channels(verify_direct=True).channels


def test_event_direct_message_is_verified_even_when_missing_from_bulk_list(
    mm: Mattermost,
) -> None:
    mm.api.channels.get_channels_for_user.return_value = []
    mm.api.channels.get_channel.return_value["total_msg_count"] = 0
    channels = mm.init_channels(verify_direct=True, channel_ids=frozenset({"dm"}))
    assert channels.channels[0].display_name == "alice"
    assert channels.channels[0].msg_unread_count == 1


def test_previously_unread_direct_message_missing_from_bulk_list_is_verified(
    mm: Mattermost,
) -> None:
    mm.init_channels(verify_direct=True)
    mm.api.channels.get_channels_for_user.return_value = []
    assert mm.init_channels(verify_direct=True).channels[0].msg_unread_count == 1


def test_missing_membership_recovers_and_failed_refresh_keeps_snapshot(
    mm: Mattermost,
) -> None:
    mm.api.channels.get_channel_members_for_user.return_value = []
    assert mm.init_channels().channels[0].display_name == "alice"
    mm.api.channels.get_channel_member.assert_called_once_with("dm", "me")

    mm.api.channels.get_channel_member.side_effect = requests.exceptions.ReadTimeout()
    with pytest.raises(requests.exceptions.ReadTimeout):
        mm.init_channels()
    assert mm.channels.channels[0].display_name == "alice"
    assert mm.channels.channels[0].msg_unread_count == 1


def test_negative_bulk_count_is_clamped_and_verified_for_direct_messages(
    mm: Mattermost,
) -> None:
    mm.api.channels.get_channels_for_user.return_value[0]["total_msg_count"] = 0
    mm.api.channels.get_channel_members_for_user.return_value[0]["msg_count"] = 1
    assert not mm.init_channels().channels
    assert mm.init_channels(verify_direct=True).channels[0].msg_unread_count == 1


def test_init_websocket_creates_event_loop_when_missing() -> None:
    mattermost = Mattermost.__new__(Mattermost)
    mattermost.api = Mock()
    asyncio.set_event_loop(None)

    try:
        mattermost.init_websocket(Mock())
        mattermost.api.init_websocket.assert_called_once()
        assert asyncio.get_event_loop().is_closed() is False
    finally:
        loop = asyncio.get_event_loop()
        loop.close()
        asyncio.set_event_loop(None)
