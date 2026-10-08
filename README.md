# mmtools - i3 status bar and notification script for Mattermost

mmtools are various tools using the [mattermost](https://mattermost.org) API.

# Changelog

## 1.0.0

Breaking change for `mmwaybar`: it now stays running and listens for Mattermost
websocket events, writing updated JSON status lines as the unread status changes.
Integrations that expect `mmwaybar` to exit after a single status check must be
updated to handle the long-running process.

# Installation

```bash
sudo pip3 install mmtools
```

This will install mmtols from pypi, including the following required packages:

- caep
- pydantic
- mattermostdriver
- passpy
- notify2
- dbus-python
- requests

For dbus-python to build, you need to have the libdbus-1-dev package installed. On debian you can do

```bash
sudo apt install libdbus-1-dev
```

# Tools

The following tools are included:

### mmstatus

`mmstatus` connects to the mattermost API to get unread messages in all channels. It then outputs a statusbar (usable in i3blocks) of unread messages and exits. Supports private/public/user channels and different coloring on group chats and user chats.

Example configuration for i3blocks:

```
[mattermost]
command=/usr/local/bin/mmstatus
separator=true
interval=60
signal=12
```

### mmpolybar

`mmpolybar` same as mmstatus, but with polybar colors.

Example configuration for polybar:

```
[module/mmpolybar]
type = custom/script
exec = mmpolybar
tail = true
```

### mmwaybar

`mmwaybar` outputs the initial unread status and then listens for Mattermost
websocket events, writing a new JSON line whenever messages or channel views
can change the unread status.

Event bursts are combined over 250 ms. A safety refresh runs every 30 seconds
to recover missed updates and stale responses. Direct-message unread
counts are verified separately when a DM is unread, was previously displayed,
or is referenced by an event.

After a displayed direct message is reported read, its last displayed name and
count stay visible for at least 30 seconds. It clears on the next successful
refresh after that period, usually retaining it for 30–60 seconds. Each DM is
retained independently; other channels continue updating normally. If a DM
becomes unread again, its count updates and a later read starts a fresh period.
Retention lasts only while `mmwaybar` is running.

If a refresh fails, the last successful text stays visible with an additional
`stale` CSS class and an error tooltip. Failed refreshes retry on the next event
or 30-second refresh. Slow HTTP requests can delay the next refresh.
Before the first successful refresh, errors appear as status text. Logs go to
stderr unless a logfile is configured; stdout contains JSON status lines.

Example configuration for waybar:

```
"custom/mattermost": {
    "exec": "mmwaybar",
    "return-type": "json"
}
```

To make stale data visible, add a rule to your Waybar CSS, for example:

```css
#custom-mattermost.stale {
    opacity: 0.6;
}
```

### mmwatch

`mmwatch` connects to the mattermost websocket API and can display notification on messages and send SIGUSR2 to i3blocks to update statusbar before next interval.

### mmchannels

`mmchannels` lists joined public and private channels across all your teams,
including channels you have already read, then exits. Use a team's short name
to restrict the listing:

```bash
mmchannels
mmchannels --team my-team
```

Output contains only date/name rows, newest activity first:

```text
2026-10-08 Town Square
2024-02-19 Old Project
never Empty Channel
```

Activity uses the creation time of the latest non-deleted, non-system post,
formatted as a local-calendar date. Replies and bot/integration posts count;
system events such as joins, departures, and channel changes do not. Channels
with the same date are ordered by their full timestamps. Channels with no such
posts in the accessible history appear last as `never`. Display names fall back
to short names when empty. Direct and group messages are excluded.

The command uses the shared authentication settings and a `[mmchannels]` config
section, where `team` can set a default team. The status tools' `ignore` setting
does not affect this listing. An unknown or unjoined team, API failure, or invalid
response produces an error on stderr and a nonzero exit status without partial
stdout. An empty listing exits successfully without output. The command only
reads channel memberships and post history; it does not change subscriptions or
fetch unread counts. It pages backward through each channel until it finds a
qualifying post or exhausts the accessible history, so channels with extensive
system activity can require multiple requests.


## Configuration

All tools can be configured using both command line arguments and a configuration file.

`mmtools` will first look for a configuration in `~/.config/mmtools/config-<HOSTNAME>` with fallback to `~/.config/mmtools/config`.

Use the following command to create the configuration `~/.config/mmtools/config`. The same configuration file is used for all tools.

```bash
mmconfig init
```

In this file you must specify at least:

```
# Mattermost server
server = <SERVER>

# Mattermost user
user = <USERNAME>

# either password
password = <MATTERMOST PASSWORD>

# OR pass entry (https://www.passwordstore.org)
password-pass-entry = <PASS ENTRY>
```

## User service for `mmwatch`

`mmwatch` can be started as a systemd user service by creating the following file:

`.config/systemd/user/mmwatch.service`

with this content:

```
[Unit]
Description=mm watch

[Service]
ExecStart=/usr/local/bin/mmwatch

Restart=always

# time to sleep before restarting a service
RestartSec=30

[Install]
WantedBy=default.target
```

Enable at login

```
systemctl --user enable mmwatch
```

Start manually
```
systemctl --user start mmwatch
```

# Local development

For local development, se [uv](https://docs.astral.sh/uv/).
