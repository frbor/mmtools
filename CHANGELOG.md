# Change Log
All notable changes to this project will be documented in this file. This change log follows the conventions of [keepachangelog.com](http://keepachangelog.com/).

## [Unreleased]
### Added
- Stream Waybar status updates in response to Mattermost websocket events.

### Changed
-

### Fixed
- Use client TLS for Mattermost websocket connections so streaming Waybar updates work on modern Python.
- Refresh Waybar when Mattermost sends `multiple_channels_viewed`, so read messages clear without waiting for another post.

### Removed
