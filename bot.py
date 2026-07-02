import os
import asyncio
import logging
import discord
import uvicorn
from discord.ext import commands
from dotenv import load_dotenv
import database
import web_server

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("discord_bot")

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Ensure required directories exist
os.makedirs("sounds", exist_ok=True)
os.makedirs("recordings", exist_ok=True)
os.makedirs("cogs", exist_ok=True)

# Initialize database
database.init_db()

# Configure intents
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True

class ImitatorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load cogs
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"Loaded extension: {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load extension {cog_name}: {e}", exc_info=True)

        # Start Web Server
        web_server.set_bot(self)
        config = uvicorn.Config(web_server.app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        self.loop.create_task(server.serve())
        logger.info("Web UI server started on http://0.0.0.0:8000")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("------")
        
        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, 
                name="/help or /imitate"
            )
        )

        # Sync slash commands globally
        try:
            logger.info("Syncing slash commands globally...")
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application (slash) commands.")
        except Exception as e:
            logger.error(f"Error syncing slash commands: {e}", exc_info=True)

bot = ImitatorBot()

# A general error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Command is on cooldown. Try again in {error.retry_after:.1f}s.", 
            ephemeral=True
        )
    elif isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            f"❌ You do not have the required permissions to run this command: {', '.join(error.missing_permissions)}.", 
            ephemeral=True
        )
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        await interaction.response.send_message(
            f"❌ I am missing permissions needed to execute this command: {', '.join(error.missing_permissions)}.", 
            ephemeral=True
        )
    else:
        logger.error(f"Unhandled app command error: {error}", exc_info=True)
        # Attempt to reply if not already responded
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An unexpected error occurred while executing this command.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An unexpected error occurred while executing this command.", 
                    ephemeral=True
                )
        except Exception:
            pass

def main():
    if not TOKEN:
        logger.error("Error: DISCORD_TOKEN environment variable not set. Please set it in your environment or a .env file.")
        return
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("Error: Invalid Discord token provided. Please double-check your bot token.")
    except Exception as e:
        logger.error(f"Error starting the bot: {e}", exc_info=True)

if __name__ == "__main__":
    main()
