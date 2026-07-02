# 🎭 Discord Imitator Bot

A powerful Discord bot that allows you to imitate other guild members via webhooks and manage a custom soundboard for voice channels.

## ✨ Features

### 👤 Member Imitation
- **Instant Imitation**: Send a message that looks like it came from another member using their actual name and avatar.
- **Active Mirroring Sessions**: Enter a session where every message you send is automatically deleted and re-sent as a target member.
- **Member Presets**: Save your favorite "copies" as named presets (e.g., `TheBoss`) for instant access without needing to search for the member every time.
- **Attachment Support**: Mirroring sessions support images and file attachments, preserving the original content while mimicking the target.

### 🔊 Custom Soundboard
- **Add Sounds**: Upload audio files directly to the bot or provide a direct URL.
- **Instant Playback**: Play saved sounds in your voice channel with a single command.
- **Sound Management**: List all available sounds, track play counts, and delete unwanted bites.
- **Snap Response**: New sounds automatically interrupt currently playing audio for a true soundboard experience.

## 🚀 Installation

### Prerequisites
- **Python 3.11+** (if running locally)
- **FFmpeg** (Required for voice support)
- **Discord Bot Token** (from the [Discord Developer Portal](https://discord.com/developers/applications))

### ⚙️ Bot Permissions (Required)
To function correctly, the bot needs the following permissions in your server:
- `Manage Webhooks` (Required for imitation)
- `Manage Messages` (Required for session mirroring)
- `Connect` & `Speak` (Required for soundboard)
- `Read Messages/View Channels` & `Send Messages`

**Privileged Gateway Intents (Must be enabled in Developer Portal):**
- `Server Members Intent`
- `Message Content Intent`

---

### 🛠️ Local Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

### 🐳 Docker Setup (Recommended)
1. Create a `.env` file in the root directory:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```
2. Start the bot:
   ```bash
   docker compose up -d
   ```
3. The bot will automatically create `./sounds` and `./data` directories to persist your audio and database.

---

## ⌨️ Commands

### Text Imitation
| Command | Description |
| :--- | :--- |
| `/imitate <member> <message>` | Send a one-off message as the selected member. |
| `/imitate-preset <preset> <message>` | Send a one-off message using a saved preset. |
| `/imitate-session <action> [member/preset]` | Start, stop, or check the status of a real-time mirroring session. |
| `/copy-preset add <name> <member>` | Save a member as a named preset. |
| `/copy-preset list` | List all your saved member presets. |
| `/copy-preset remove <name>` | Delete a saved preset. |

### Soundboard
| Command | Description |
| :--- | :--- |
| `/sound add <name> <file/url>` | Save a new sound bite (upload file or provide URL). |
| `/sound play <name>` | Play a saved sound in your current voice channel. |
| `/sound list` | List all available sound bites and their play counts. |
| `/sound stop` | Stop audio playback and disconnect the bot. |
| `/sound delete <name>` | Remove a sound bite and its local file. |

## 📂 Project Structure
- `bot.py`: Main entry point and bot class.
- `database.py`: SQLite database layer.
- `cogs/`: Modular feature sets (imitation and soundboard).
- `sounds/`: Directory where uploaded audio files are stored.
- `data/`: Directory containing the SQLite database.
