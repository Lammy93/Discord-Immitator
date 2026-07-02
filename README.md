# Discord Imitator Bot

A powerful Discord bot that imitates other guild members via webhooks, manages a custom soundboard with voice recording, and provides a Web UI dashboard for control.

## Features

### Web UI Dashboard
- **Server Selector** — choose which guild to control
- **Member Grid** — browse all members with avatars, download avatar images
- **Quick Mirror** — select a member, type a message, send it as them via webhook (includes @ mention support)
- **Soundboard Tab** — upload single or multiple audio files, play sounds in voice
- **Voice Tab** — join/leave voice channels, record audio from speakers, view recent recordings
- **Settings Tab** — change bot presence (status, activity type, activity text)
- **Status Bar** — shows current voice channel connection, active imitation target with avatar

### Member Imitation
- **Instant Imitation** — `/imitate <member> <message>` sends a message as another member using their name and avatar via webhook
- **Mirroring Sessions** — `/imitate-session` mirrors all your messages as a target member (auto-deletes originals, supports attachments and embeds)
- **Member Presets** — `/copy-preset add/list/remove` saves favorite targets as named presets for quick access

### Custom Soundboard
- **Add Sounds** — upload audio files or provide a URL via `/sound add` or the Web UI
- **Bulk Upload** — upload multiple files at once through the dashboard
- **Instant Playback** — `/sound play` or click play in the UI; new sounds interrupt current playback
- **Sound Management** — list all sounds with play counts, delete unwanted ones
- **Auto-Connect** — bot joins your voice channel automatically when playing a sound

### Slash Commands

| Command | Description |
| :--- | :--- |
| `/imitate <member> <message>` | Send a one-off message as another member |
| `/imitate-session action:[start\|stop\|status]` | Start, stop, or check a mirroring session |
| `/imitate-preset <preset> <message>` | Send a message using a saved preset |
| `/copy-preset add <name> <member>` | Save a member as a named preset |
| `/copy-preset list` | List your saved presets |
| `/copy-preset remove <name>` | Delete a preset |
| `/sound add <name> [file] [url]` | Add a sound bite (file upload or URL) |
| `/sound play <name>` | Play a sound in your voice channel |
| `/sound list` | List all sounds with play counts |
| `/sound stop` | Stop audio and disconnect from voice |
| `/sound delete <name>` | Delete a sound bite |

## Setup

### Prerequisites
- Python 3.11+
- FFmpeg (included in Docker image; required locally for voice)
- Discord Bot Token from the [Developer Portal](https://discord.com/developers/applications)

### Discord Developer Portal Setup
1. Create a new application at https://discord.com/developers/applications
2. Go to **Bot** > **Build-A-Bot** > **Reset Token** — copy the token
3. Enable **Privileged Gateway Intents**:
   - `Server Members Intent`
   - `Message Content Intent`
4. Go to **OAuth2** > **URL Generator**:
   - Scopes: `bot` `applications.commands`
   - Bot Permissions: `Manage Webhooks` `Manage Messages` `Send Messages` `Read Messages/View Channels` `Connect` `Speak` `Change Nickname`
5. Use the generated URL to invite the bot to your server

### Bot Permissions Required
- `Manage Webhooks` — webhook-based imitation
- `Manage Messages` — auto-delete originals during sessions
- `Connect` & `Speak` — soundboard playback
- `Read Messages/View Channels` & `Send Messages`
- `Change Nickname` — update nickname to match imitated member

### Local Setup
```bash
git clone <repo>
cd discord-bot-imitator
pip install -r requirements.txt
echo DISCORD_TOKEN=your_token > .env
python bot.py
```

The Web UI is available at http://localhost:8000.

### Docker Setup
```bash
echo DISCORD_TOKEN=your_token > .env
docker compose up -d
```

The bot pulls from `ghcr.io/ozzyzboi/discord-bot-imitator:latest`.

### Portainer Deployment
1. Add a new **Stack** with the `docker-compose.yml` contents
2. Set `DISCORD_TOKEN` as an environment variable in the Portainer UI
3. Enable **Pull and Redeploy** on git push for automatic updates

### GitHub Actions CI/CD
Push to the `master` branch triggers an automatic Docker build and push to GHCR (`ghcr.io/ozzyzboi/discord-bot-imitator`).

## Project Structure
```
bot.py              Main entry point — loads cogs, starts uvicorn
database.py         SQLite layer (soundbites, imitation_sessions, member_presets)
web_server.py       FastAPI router + all API endpoints
cogs/
  imitation.py      Webhook-based text imitation, sessions, presets
  soundboard.py     FFmpeg audio playback, voice management
static/
  index.html        Tailwind CSS dashboard UI
sounds/             Uploaded audio files (Docker volume)
data/               SQLite database file (Docker volume)
```

## Architecture Notes
- **Text imitation** uses Discord webhooks to spoof display name and avatar per message
- **Voice identity** is limited to nickname changes; profile pictures cannot be spoofed in voice
- **Voice audio** streams are tied to the bot account ID; cannot be spoofed as another user
- Bot and webhook messages always show an "APP" tag (Discord-enforced)
- Recording requires `PyNaCl` (included via `discord.py[voice]`) for decrypting incoming voice packets
