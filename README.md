# mmtools - i3 status bar and notification script for Mattermost

mmtools are various tools using the [mattermost](https://mattermost.org) API.

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

### mmwatch

`mmwatch` connects to the mattermost websocket API and can display notification on messages and send SIGUSR2 to i3blocks to update statusbar before next interval.


## Configuration

All tools can be configured using both command line arguments and a configuration file.

Use the following command to create the configuration `~/.config/mmtools/config`. The same configuration file is used for both tools.

```bash
mmconfig user
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

For local development, execute:

```bash
pip3 install -e .
```
