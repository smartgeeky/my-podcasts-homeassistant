# My Podcasts - Home Assistant Add-on

[![English](https://img.shields.io/badge/Language-English-blue)](https://github.com/smartgeeky/my-podcasts-homeassistant/blob/main/README.md) [![Slovenian](https://img.shields.io/badge/Language-Slovenian-green)](https://github.com/smartgeeky/my-podcasts-homeassistant/blob/main/my-podcasts/README.sl.md

My Podcasts is a comprehensive Home Assistant add-on for managing and listening to podcasts within your smart home ecosystem. It provides a complete podcast management solution with multi-user support, automatic updates, and seamless integration with Home Assistant media players.

## 🎯 Key Features

### 📡 Podcast Management
- **RSS Feed Support**: Add podcasts via RSS URLs with automatic episode discovery
- **Manual RSS Import**: Upload XML files to add missing episodes from podcast archives
- **Automatic Updates**: Scheduled automatic updates for all podcasts
- **Smart Episode Tracking**: Automatic detection of new episodes with duplicate prevention

### 👥 Multi-User Support
- **Individual User Accounts**: Each user has their own podcast library
- **Admin Controls**: Admin users can manage all podcasts and users
- **Public/Private Podcasts**: Share podcasts with all users or keep them private
- **Central User Mode**: Special tablet/TV interface for shared devices

### 🎵 Playback Features
- **Built-in Browser Player**: Play episodes directly in the web interface
- **Home Assistant Integration**: Play on any connected media player
- **Playback Position Tracking**: Resume episodes from where you left off
- **Listen Status**: Mark episodes as listened with visual indicators

### 🎨 User Interface
- **Responsive Design**: Optimized for desktop, tablet, and mobile devices
- **Tablet Mode**: Special interface for shared devices (TVs, tablets)
- **Multi-language Support**: English and Slovenian interface
- **Dark/Light Theme**: Automatically adapts to your preferences

### 🔧 Advanced Features
- **Podcast Visibility Control**: Hide unwanted podcasts from your view
- **Episode Descriptions**: Full episode descriptions with expandable text
- **Pagination**: Efficient browsing of large episode lists
- **Search and Filter**: Easy navigation through your podcast library

## 🚀 Installation

### Method 1: Add Repository (Recommended)

1. **Add the Repository**
   - In Home Assistant, go to Settings → Add-ons → Add-on Store
   - Click the three dots in the top right corner and select "Repositories"
   - Add this repository URL and click "Add"
   - Refresh the page

2. **Install the Add-on**
   - Find "My Podcasts" in the add-on store
   - Click on "My Podcasts" and then "Install"
   - Wait for the installation to complete

3. **Start the Add-on**
   - After installation, click "Start"
   - The add-on will appear in the Home Assistant sidebar

### Method 2: Manual Installation

1. Copy the `my_podcasts` folder to your Home Assistant `addons` directory
2. Restart Home Assistant
3. Go to Settings → Add-ons → Add-on Store
4. Refresh the page and install "My Podcasts"

## 📖 Usage Guide

### 🎯 Getting Started

1. **First Login**: The first user to access the add-on automatically becomes an admin
2. **Add Your First Podcast**: Enter the podcast name and RSS URL
3. **Choose Visibility**: Decide if the podcast should be public (visible to all users) or private
4. **Automatic Updates**: Episodes are automatically fetched and updated

### 👤 User Management

#### Admin Users
- Can see and manage all podcasts from all users
- Can delete any podcast or episode
- Can promote other users to admin status
- Can set up central user for shared devices

#### Regular Users
- Can add and manage their own podcasts
- Can see public podcasts from other users
- Can hide unwanted public podcasts
- Cannot delete podcasts owned by others

#### Central User (Tablet Mode)
- Special mode for shared devices like tablets or TVs
- Simplified interface optimized for touch devices
- Can switch between different users' podcast libraries
- Perfect for family use or public spaces

### 🎵 Listening to Podcasts

#### Browser Playback
- Click "Play" on any episode for immediate browser playback
- Playback position is automatically saved
- Resume listening from where you left off
- Episodes are automatically marked as listened when finished

#### Home Assistant Media Players
- Select any configured media player from the dropdown
- Playback starts with saved position (if available)
- Perfect for whole-home audio systems
- Supports all Home Assistant compatible media players

### ⚙️ Settings Configuration

#### Automatic Updates
- **Frequency**: Choose daily or weekly updates
- **Time**: Set preferred update time (default: 3:00 AM)
- **Manual Override**: Force update all podcasts anytime

#### Media Player Selection
- Choose which Home Assistant media players to show
- Supports all types: Sonos, Chromecast, AirPlay, etc.
- Select all or customize your preferred players

#### Language Settings
- Switch between English and Slovenian
- Language preference is saved per browser
- Affects all interface elements and messages

#### User Management (Admin Only)
- Set central user for tablet/TV access
- Promote users to admin status
- View user registration information
- Manage multi-user access permissions

### 📱 Tablet/TV Mode

Access the tablet-optimized interface at `/tablet.html`:

1. **Select User**: Choose whose podcast library to display
2. **Browse Podcasts**: Touch-friendly podcast grid
3. **Quick Access**: See latest episodes and paused content
4. **Episode Playback**: Large, easy-to-tap playback controls

Perfect for:
- Living room tablets
- Kitchen displays
- Family shared devices
- Public waiting areas

### 🔒 Podcast Visibility

#### Public Podcasts
- Visible to all users in the system
- Can be hidden by individual users (but not deleted)
- Perfect for family podcasts or shared interests
- Admins can delete public podcasts

#### Private Podcasts
- Only visible to the owner
- Cannot be seen by other users
- Owner can change to public anytime
- Perfect for personal interests

#### Hidden Podcasts
- Public podcasts that you've chosen to hide
- Remain in the system but don't appear in your list
- Can be restored from Settings → Hidden Podcasts
- Useful for filtering out unwanted content

## 🛠️ Technical Specifications

### System Requirements
- Home Assistant OS, Supervised, or Container
- Minimum 512MB RAM
- 100MB storage space for the add-on
- Additional space for podcast episode metadata

### Supported Architectures
- `amd64` (Intel/AMD 64-bit)
- `aarch64` (ARM 64-bit, Raspberry Pi 4)
- `armv7` (ARM 32-bit, Raspberry Pi 3)
- `armhf` (ARM 32-bit)
- `i386` (Intel 32-bit)

### Database
- SQLite database for reliable data storage
- Automatic database migrations
- Data stored in `/data/mypodcasts.db`
- Regular automatic backups recommended

### API Endpoints
The add-on provides RESTful API endpoints for:
- Podcast management (`/api/podcasts`)
- Episode tracking (`/api/episodes`)
- User management (`/api/users`)
- Media player integration (`/api/media_players`)
- Settings configuration (`/api/settings`)

## 🔧 Configuration Options

```yaml
log_level: info          # Logging level (debug, info, warning, error)
update_interval: 60      # Update check interval in minutes
db_file: "/data/mypodcasts.db"  # Database file location
safe_mode: false         # Enable safe mode for troubleshooting
```

## 📋 Changelog

See [CHANGELOG.md](https://github.com/smartgeeky/my-podcasts-homeassistant/blob/main/CHANGELOG.md) for detailed version history and update notes.

## 🆘 Troubleshooting

### Common Issues

**Episodes not updating**
- Check your internet connection
- Verify RSS URL is still valid
- Check automatic update settings
- Try manual update from the interface

**Media players not appearing**
- Ensure Home Assistant API access is enabled
- Check that media players are discovered in HA
- Refresh the add-on configuration
- Review Home Assistant logs for errors

**Performance issues**
- Consider reducing update frequency
- Check available system resources
- Review database size and consider cleanup
- Ensure adequate storage space

**User access problems**
- Check Home Assistant authentication
- Verify user permissions in HA
- Clear browser cache and cookies
- Check add-on logs for authentication errors

### Debug Mode

Enable debug logging by setting `log_level: debug` in configuration:

1. Go to Settings → Add-ons → My Podcasts
2. Click Configuration tab
3. Set `log_level` to `debug`
4. Restart the add-on
5. Check logs for detailed information

### Getting Help

1. **Check the Logs**: Always check add-on logs first
2. **GitHub Issues**: Report bugs on the project GitHub page
3. **Home Assistant Community**: Ask questions in the HA forums
4. **Documentation**: Review this README and changelog

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request
5. Follow coding standards and documentation

### Development Setup

1. Clone the repository
2. Set up Home Assistant development environment
3. Install the add-on in development mode
4. Make changes and test thoroughly
5. Submit pull request with detailed description

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/smartgeeky/my-podcasts-homeassistant/blob/main/LICENSE) file for details.

## 🙏 Acknowledgments

- Home Assistant team for the excellent platform
- Python community for amazing libraries
- RSS/Podcast ecosystem for standardized feeds
- Contributors and testers who make this project better

## 📞 Support

- **Documentation**: This README and project wiki
- **Issues**: GitHub issue tracker
- **Community**: Home Assistant forums
- **Updates**: Watch the repository for notifications

---

**Enjoy your podcast listening experience with Home Assistant! 🎧**