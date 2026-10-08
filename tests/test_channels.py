"""Observable behavior of the one-shot channel listing."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest
import requests

from mmtools import arguments, channels
from mmtools.mattermost import Mattermost, User


@pytest.fixture(autouse=True)
def local_timezone(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with monkeypatch.context() as context:
        context.setenv("TZ", "UTC-02")
        time.tzset()
        yield
    time.tzset()


@pytest.fixture
def args() -> arguments.Config:
    return arguments.Config(
        server="mattermost.example.com",
        user="me",
        password="test",
        password_pass_entry=None,
        ignore="Town|Private",
        logfile=None,
        team=None,
    )


@pytest.fixture
def mm(args: arguments.Config, monkeypatch: pytest.MonkeyPatch) -> Mattermost:
    mm = Mattermost.__new__(Mattermost)
    mm.api = Mock()
    mm.user = User(id="me", username="me", first_name="", last_name="")
    mm.teams = [{"id": "one", "name": "first"}, {"id": "two", "name": "second"}]
    mm.api.channels.get_channels_for_user.return_value = []
    mm.api.posts.get_posts_for_channel.return_value = {"order": [], "posts": {}}
    monkeypatch.setattr(channels, "Mattermost", Mock(return_value=mm))
    monkeypatch.setattr(arguments, "handle_args", Mock(return_value=args))
    return mm


def payload(
    name: str, kind: str = "O", last_post_at: int | None = 0
) -> dict[str, object]:
    return {
        "id": name,
        "type": kind,
        "name": name.lower(),
        "display_name": name,
        "last_post_at": last_post_at,
    }


def test_lists_read_public_and_private_channels_across_teams(
    mm: Mattermost, capsys: pytest.CaptureFixture[str]
) -> None:
    public = payload("Town")
    public.update(total_msg_count=5, msg_count=5)
    mm.api.channels.get_channels_for_user.side_effect = [
        [public, payload("Direct", "D")],
        [payload("Private", "P"), payload("Group", "G")],
    ]

    channels.main()

    assert capsys.readouterr().out == "never Private\nnever Town\n"
    assert mm.api.channels.get_channels_for_user.call_args_list == [
        call("me", "one"),
        call("me", "two"),
    ]
    mm.api.channels.get_channel_members_for_user.assert_not_called()
    mm.api.channels.get_channel_member.assert_not_called()
    mm.api.channels.get_unread_messages.assert_not_called()
    assert {
        request.args[0] for request in mm.api.posts.get_posts_for_channel.call_args_list
    } == {"Town", "Private"}


def test_full_timestamp_order_local_dates_and_name_fallback(
    mm: Mattermost, capsys: pytest.CaptureFixture[str]
) -> None:
    midnight = int(datetime(2026, 10, 8, 22, tzinfo=UTC).timestamp() * 1000)
    fallback = payload("short-name", last_post_at=midnight)
    fallback["display_name"] = ""
    missing = payload("Missing")
    del missing["last_post_at"]
    mm.api.channels.get_channels_for_user.side_effect = [
        [
            payload("Earlier", last_post_at=midnight + 1),
            payload("Zero"),
            payload("Zebra", last_post_at=midnight + 2),
        ],
        [
            missing,
            fallback,
            payload("Alpha", last_post_at=midnight + 2),
            payload("Null", last_post_at=None),
        ],
    ]

    def history(channel_id: str, params: dict[str, str | int]) -> dict[str, object]:
        timestamp = {
            "Earlier": midnight + 1,
            "Zebra": midnight + 2,
            "Alpha": midnight + 2,
            "short-name": midnight,
        }.get(channel_id)
        if timestamp is None:
            return {"order": [], "posts": {}}
        return {
            "order": ["post"],
            "posts": {"post": {"type": "", "create_at": timestamp, "delete_at": 0}},
        }

    mm.api.posts.get_posts_for_channel.side_effect = history

    channels.main()

    assert capsys.readouterr().out.splitlines() == [
        "2026-10-09 Alpha",
        "2026-10-09 Zebra",
        "2026-10-09 Earlier",
        "2026-10-09 short-name",
        "never Missing",
        "never Null",
        "never Zero",
    ]


def test_team_selection(
    mm: Mattermost, args: arguments.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    args.team = "second"
    mm.api.channels.get_channels_for_user.return_value = [payload("Private", "P")]

    channels.main()

    assert capsys.readouterr().out == "never Private\n"
    mm.api.channels.get_channels_for_user.assert_called_once_with("me", "two")


def test_system_only_channel_is_never_despite_last_post_at(
    mm: Mattermost, args: arguments.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    args.team = "first"
    mm.api.channels.get_channels_for_user.return_value = [
        payload("TRS|MSS Purple Team", last_post_at=1790899200000)
    ]
    mm.api.posts.get_posts_for_channel.side_effect = [
        {
            "order": ["join"],
            "posts": {
                "join": {
                    "type": "system_join_channel",
                    "create_at": 1790899200000,
                    "delete_at": 0,
                }
            },
        },
        {"order": [], "posts": {}},
    ]

    channels.main()

    assert capsys.readouterr().out == "never TRS|MSS Purple Team\n"
    assert (
        mm.api.posts.get_posts_for_channel.call_args.kwargs["params"]["before"]
        == "join"
    )


def test_finds_message_after_system_and_deleted_posts(
    mm: Mattermost, args: arguments.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    args.team = "first"
    mm.api.channels.get_channels_for_user.return_value = [payload("Project")]
    mm.api.posts.get_posts_for_channel.side_effect = [
        {
            "order": ["rename", "deleted"],
            "posts": {
                "rename": {
                    "type": "system_displayname_change",
                    "create_at": 3000,
                    "delete_at": 0,
                },
                "deleted": {"type": "", "create_at": 2000, "delete_at": 4000},
                # Thread context outside order must not influence the date.
                "context": {"type": "", "create_at": 1500, "delete_at": 0},
            },
        },
        {
            "order": ["reply"],
            "posts": {
                "reply": {
                    "type": "slack_attachment",
                    "create_at": 1000,
                    "delete_at": 0,
                    "root_id": "root",
                    "props": {"from_bot": "true"},
                }
            },
        },
    ]

    channels.main()

    assert capsys.readouterr().out == "1970-01-01 Project\n"
    requests_made = mm.api.posts.get_posts_for_channel.call_args_list
    assert requests_made[-1].kwargs["params"]["before"] == "deleted"
    assert requests_made[0].kwargs["params"]["collapsed_threads"] == "false"


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.ReadTimeout(),
        {"posts": {}},
        {
            "order": ["bad"],
            "posts": {"bad": {"type": "", "create_at": 10**30, "delete_at": 0}},
        },
    ],
)
def test_history_failure_leaves_no_partial_stdout(
    mm: Mattermost,
    args: arguments.Config,
    capsys: pytest.CaptureFixture[str],
    failure: object,
) -> None:
    args.team = "first"
    mm.api.channels.get_channels_for_user.return_value = [
        payload("One"),
        payload("Two"),
    ]
    mm.api.posts.get_posts_for_channel.side_effect = [
        {"order": [], "posts": {}},
        failure,
    ]

    with pytest.raises(SystemExit) as error:
        channels.main()

    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("mmchannels: ")


def test_unknown_team_fails_before_fetching_channels(
    mm: Mattermost, args: arguments.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    args.team = "unknown"

    with pytest.raises(SystemExit) as error:
        channels.main()

    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Team 'unknown' is not among your joined teams" in output.err
    mm.api.channels.get_channels_for_user.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.ReadTimeout(),
        RuntimeError("Second team failed"),
        {"unexpected": "response"},
        [{"id": "invalid"}],
    ],
)
def test_failure_leaves_no_partial_stdout(
    mm: Mattermost, capsys: pytest.CaptureFixture[str], failure: object
) -> None:
    mm.api.channels.get_channels_for_user.side_effect = [[payload("Valid")], failure]

    with pytest.raises(SystemExit) as error:
        channels.main()

    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("mmchannels: ")
    assert len(output.err.splitlines()) == 1


def test_authentication_failure_is_reported_on_stderr(
    mm: Mattermost, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        channels, "Mattermost", Mock(side_effect=RuntimeError("Login failed"))
    )
    with pytest.raises(SystemExit) as error:
        channels.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "mmchannels: Login failed\n"


@pytest.mark.parametrize("teams", [[], [{"id": "one", "name": "first"}]])
def test_empty_listing_succeeds_without_output(
    mm: Mattermost, capsys: pytest.CaptureFixture[str], teams: list[dict[str, str]]
) -> None:
    mm.teams = teams
    channels.main()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""
