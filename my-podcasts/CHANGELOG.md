
# Changelog

## [1.1] - 10. 06. 2025
### Added
- **Smart position resumption** - episodes now automatically start from saved position when playing on Home Assistant media players
- **Active session tracking** - real-time monitoring of playback sessions on Home Assistant devices
- **Improved seek functionality** - intelligent waiting for media to load before seeking to saved position
- **Enhanced playback monitoring** - automatic position saving during playback on HA devices
- **Session cleanup** - automatic cleanup of tracking sessions when playback stops or pauses

### Improved
- **Home Assistant media player integration** - eliminated the issue where episodes would start from beginning and then jump to saved position
- **Position tracking accuracy** - better detection of playback state changes
- **User experience** - seamless continuation of episodes across browser and HA device playback
- **Error handling** - improved robustness when communicating with Home Assistant API

### Technical Changes
- **New database table**: `ActiveTrackingSessions` for tracking active playback sessions
- **Enhanced API endpoints**: improved `play_episode` endpoint with smart seek logic
- **Background monitoring**: dedicated thread for monitoring Home Assistant media player states
- **WebSocket integration**: better communication with Home Assistant for real-time player state
- **Async improvements**: enhanced async handling for media player operations

### Bug Fixes
- Fixed issue where episodes would briefly play from beginning before jumping to saved position
- Improved reliability of position saving during Home Assistant device playback
- Better handling of media player state transitions

## [1.0] - 01. 06. 2025
### Added
- **Complete podcast management system** for Home Assistant
- **Multi-user support** with admin and regular user roles
- **Public and private podcasts** - share with all users or keep private
- **Automatic RSS feed updates** with configurable schedules
- **Built-in web player** for direct browser playback
- **Home Assistant media player integration** - play on any connected device
- **Playback position tracking** - resume episodes where you left off
- **Episode listening status** - mark episodes as listened with visual indicators
- **Tablet/TV interface** - optimized interface for shared devices (tablet.html)
- **Multi-language support** - English and Slovenian interface
- **RSS XML import** - upload XML files to add missing episodes
- **Podcast visibility controls** - hide unwanted public podcasts
- **Responsive design** - works on desktop, tablet, and mobile devices
- **Episode descriptions** - full episode descriptions with expandable text
- **Pagination support** - efficient browsing of large episode lists
- **Admin user management** - promote users and manage permissions
- **Automatic database migrations** - safe upgrades from any previous version

### Technical Features
- **SQLite database** for reliable data storage
- **RESTful API** for all podcast operations
- **Gunicorn production server** for optimal performance
- **Docker multi-architecture support** (amd64, aarch64, armv7, armhf, i386)
- **Home Assistant Supervisor integration** with ingress support
- **Configurable logging** and error handling
- **Thread-safe operations** for concurrent user access

---

**Initial Release Notes:**
- First user to access the add-on automatically becomes administrator
- Default language is English - can be changed to Slovenian in settings
- Supports all RSS 2.0 compatible podcast feeds
- Compatible with all Home Assistant installation methods
- Minimum 512MB RAM recommended for optimal performance