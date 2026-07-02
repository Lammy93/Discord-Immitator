import os
import logging
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import database

logger = logging.getLogger("discord_bot.soundboard")

class Soundboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Allowed audio formats
        self.allowed_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.webm', '.aac'}

    async def download_file(self, url: str, destination: str) -> bool:
        """Downloads a file from a URL to a local destination using aiohttp."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download file: HTTP status {response.status}")
                        return False
                    
                    with open(destination, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Error downloading file from {url}: {e}", exc_info=True)
            return False

    # --- Slash Commands Group ---
    sound_group = app_commands.Group(name="sound", description="Manage and play custom sound bites")

    @sound_group.command(
        name="add",
        description="Add a new sound bite (either upload an audio file or provide a direct download URL)."
    )
    @app_commands.describe(
        name="The unique name for this sound bite (letters, numbers, underscores)",
        file="An audio file attachment (mp3, wav, ogg, m4a, etc.)",
        url="A direct HTTP link to an audio file"
    )
    async def sound_add(
        self, 
        interaction: discord.Interaction, 
        name: str, 
        file: discord.Attachment = None, 
        url: str = None
    ):
        # Validate name
        clean_name = name.strip().lower()
        if not clean_name.isalnum() and "_" not in clean_name:
            await interaction.response.send_message(
                "❌ Sound name can only contain letters, numbers, and underscores.", 
                ephemeral=True
            )
            return

        if not file and not url:
            await interaction.response.send_message(
                "❌ You must either attach an audio file or provide a direct URL.", 
                ephemeral=True
            )
            return

        # Check if already exists in DB
        existing = database.get_soundbite(clean_name)
        if existing:
            await interaction.response.send_message(
                f"❌ A sound bite named `{clean_name}` already exists. Use another name or delete it first.", 
                ephemeral=True
            )
            return

        # Defer reply as downloading might take time
        await interaction.response.defer(ephemeral=True)

        target_url = None
        filename = None

        if file:
            # Validate extension
            _, ext = os.path.splitext(file.filename.lower())
            if ext not in self.allowed_extensions:
                await interaction.followup.send(
                    f"❌ Unsupported file format `{ext}`. Supported formats: {', '.join(self.allowed_extensions)}", 
                    ephemeral=True
                )
                return
            target_url = file.url
            filename = f"{clean_name}{ext}"
        elif url:
            # Check URL extension or simple heuristic
            _, ext = os.path.splitext(url.split('?')[0].lower())
            if ext not in self.allowed_extensions:
                # If no clear audio extension, default to mp3
                ext = ".mp3"
            target_url = url
            filename = f"{clean_name}{ext}"

        file_path = os.path.join("sounds", filename)

        # Download the file
        success = await self.download_file(target_url, file_path)
        if not success:
            await interaction.followup.send("❌ Failed to download and save the audio file. Make sure the URL is valid.", ephemeral=True)
            return

        # Register in database
        added_by = interaction.user.display_name
        db_success = database.add_soundbite(clean_name, file_path, added_by)

        if db_success:
            await interaction.followup.send(
                f"✅ **Sound bite added successfully!**\n"
                f"• Name: `{clean_name}`\n"
                f"• Added By: `{added_by}`\n"
                f"• Play using: `/sound play name:{clean_name}`", 
                ephemeral=True
            )
            logger.info(f"User {interaction.user} added sound bite '{clean_name}' saving to '{file_path}'")
        else:
            # Cleanup downloaded file if db insert failed
            if os.path.exists(file_path):
                os.remove(file_path)
            await interaction.followup.send("❌ A sound bite with that name already exists in the database.", ephemeral=True)

    @sound_group.command(
        name="play",
        description="Join your voice channel and play a saved sound bite."
    )
    @app_commands.describe(
        name="The name of the sound bite to play"
    )
    async def sound_play(self, interaction: discord.Interaction, name: str):
        clean_name = name.strip().lower()

        # Check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel to play sound bites!", 
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        # Retrieve sound bite from DB
        sound = database.get_soundbite(clean_name)
        if not sound:
            await interaction.response.send_message(
                f"❌ Sound bite `{clean_name}` not found. Use `/sound list` to see available sounds.", 
                ephemeral=True
            )
            return

        file_path = sound["file_path"]
        if not os.path.exists(file_path):
            await interaction.response.send_message(
                f"❌ Audio file for `{clean_name}` is missing on the server. Deleting record.", 
                ephemeral=True
            )
            database.delete_soundbite(clean_name)
            return

        # Defer response since connecting and playing can take a moment
        await interaction.response.defer(ephemeral=False)

        try:
            # Handle voice connection
            voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
            if not voice_client:
                voice_client = await channel.connect()
                logger.info(f"Connected to voice channel: {channel.name} ({channel.id})")
            elif voice_client.channel != channel:
                await voice_client.move_to(channel)
                logger.info(f"Moved to voice channel: {channel.name} ({channel.id})")

            # Play audio
            if voice_client.is_playing():
                voice_client.stop()

            # Create an audio source using FFmpeg
            audio_source = discord.FFmpegPCMAudio(file_path)
            # Wrap in VolumeTransformer if volume adjustment is ever needed
            # audio_source = discord.PCMVolumeTransformer(audio_source, volume=0.8)

            voice_client.play(audio_source)
            database.increment_soundbite_count(clean_name)
            
            await interaction.followup.send(f"🔊 Playing sound bite: **{clean_name}**")
            logger.info(f"Playing sound '{clean_name}' in guild {interaction.guild.id}")

        except Exception as e:
            logger.error(f"Failed to play sound '{clean_name}': {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to join voice channel or play the sound bite.", ephemeral=True)

    @sound_group.command(
        name="stop",
        description="Stop playing audio and disconnect the bot from voice."
    )
    async def sound_stop(self, interaction: discord.Interaction):
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("❌ I am not currently connected to any voice channel.", ephemeral=True)
            return

        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ Stopped audio playback and disconnected from the voice channel.")
        logger.info(f"Disconnected from voice in guild {interaction.guild.id}")

    @sound_group.command(
        name="list",
        description="List all available sound bites."
    )
    async def sound_list(self, interaction: discord.Interaction):
        sounds = database.get_all_soundbites()
        
        if not sounds:
            await interaction.response.send_message(
                "🎵 No sound bites available yet!\nAdd some with `/sound add name:<name> file:<file>`", 
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎵 Available Sound Bites",
            description="Use `/sound play name:<sound_name>` to play them in your voice channel!",
            color=discord.Color.blurple()
        )

        names_list = []
        added_by_list = []
        plays_list = []

        for sound in sounds:
            names_list.append(f"`{sound['name']}`")
            added_by_list.append(sound['added_by'])
            plays_list.append(str(sound['play_count']))

        # Format list neatly using embed fields
        embed.add_field(name="Sound Name", value="\n".join(names_list), inline=True)
        embed.add_field(name="Added By", value="\n".join(added_by_list), inline=True)
        embed.add_field(name="Play Count", value="\n".join(plays_list), inline=True)
        
        embed.set_footer(text=f"Total: {len(sounds)} sound bites")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @sound_group.command(
        name="delete",
        description="Delete a saved sound bite."
    )
    @app_commands.describe(
        name="The name of the sound bite to delete"
    )
    async def sound_delete(self, interaction: discord.Interaction, name: str):
        clean_name = name.strip().lower()

        sound = database.get_soundbite(clean_name)
        if not sound:
            await interaction.response.send_message(f"❌ Sound bite `{clean_name}` does not exist.", ephemeral=True)
            return

        file_path = sound["file_path"]

        # Delete database record
        database.delete_soundbite(clean_name)

        # Delete local file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")

        await interaction.response.send_message(f"🗑️ Successfully deleted sound bite `{clean_name}`.")
        logger.info(f"Deleted sound bite '{clean_name}' and file '{file_path}'")

async def setup(bot: commands.Bot):
    await bot.add_cog(Soundboard(bot))
