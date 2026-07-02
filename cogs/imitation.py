import logging
import discord
from discord import app_commands
from discord.ext import commands
import database

logger = logging.getLogger("discord_bot.imitation")

class Imitation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook:
        """Finds an existing webhook created by the bot or creates a new one."""
        try:
            # Check for existing webhooks in this channel
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                # If the bot is the creator of the webhook or it's named 'Imitator'
                if webhook.user == self.bot.user or webhook.name == "BotImitator":
                    return webhook
            
            # Create a new webhook if none exist
            logger.info(f"Creating new webhook 'BotImitator' in channel: {channel.name} ({channel.id})")
            return await channel.create_webhook(name="BotImitator", reason="Used for member imitation features.")
        except Exception as e:
            logger.error(f"Failed to get/create webhook in channel {channel.id}: {e}", exc_info=True)
            raise

    # --- Listener for active sessions ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages and system messages
        if message.author.bot or not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        # Check if this user has an active imitation session in this guild
        target_id = database.get_imitation_session(message.author.id, message.guild.id)
        if not target_id:
            return

        # We have an active session! Let's forward this message as the target
        try:
            # Try to fetch target member
            target_member = message.guild.get_member(int(target_id))
            if not target_member:
                target_member = await message.guild.fetch_member(int(target_id))

            if not target_member:
                # If member left or can't be found, end the session
                database.stop_imitation_session(message.author.id, message.guild.id)
                logger.warning(f"Target member {target_id} not found in guild {message.guild.id}. Ended session for {message.author.id}.")
                return

            # Get or create webhook for this channel
            webhook = await self.get_or_create_webhook(message.channel)

            # Delete original message
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(f"Missing Manage Messages permission in guild {message.guild.id} channel {message.channel.id}")

            # Prepare files if there are attachments
            files = []
            if message.attachments:
                for attachment in message.attachments:
                    try:
                        file_obj = await attachment.to_file()
                        files.append(file_obj)
                    except Exception as e:
                        logger.error(f"Failed to download attachment {attachment.url}: {e}")

            # Send message via webhook mimicking the target
            # If the user typed nothing but sent files, content might be empty/None
            content = message.content if message.content else None
            
            await webhook.send(
                content=content,
                username=target_member.display_name,
                avatar_url=target_member.display_avatar.url,
                files=files,
                embeds=message.embeds,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
            )
            logger.info(f"Forwarded message from {message.author} (imitating {target_member}) in channel {message.channel.id}")

        except Exception as e:
            logger.error(f"Error in on_message imitation forwarding: {e}", exc_info=True)


    # --- Slash Commands ---
    @app_commands.command(
        name="imitate",
        description="Send a single message imitating another member."
    )
    @app_commands.describe(
        member="The guild member you want to imitate",
        message="The message content to send"
    )
    async def imitate(self, interaction: discord.Interaction, member: discord.Member, message: str):
        # Must be in a text channel
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in server text channels.", ephemeral=True)
            return

        # Check bot permissions in this channel
        permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not permissions.manage_webhooks:
            await interaction.response.send_message("❌ I need the **Manage Webhooks** permission in this channel to imitate members.", ephemeral=True)
            return

        # Acknowledge immediately (since webhook creation/sending might take > 3 seconds)
        await interaction.response.defer(ephemeral=True)

        try:
            webhook = await self.get_or_create_webhook(interaction.channel)
            await webhook.send(
                content=message,
                username=member.display_name,
                avatar_url=member.display_avatar.url,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
            )
            await interaction.followup.send(f"✅ Successfully sent message imitating **{member.display_name}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to run /imitate command: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to send the imitated message. Make sure I have webhook permissions.", ephemeral=True)


    # --- Imitation Sessions Commands ---
    @app_commands.default_permissions(manage_messages=True)  # Restrict to moderators/admins by default
    @app_commands.command(
        name="imitate-session",
        description="Manage your real-time member imitation session."
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Start - Speak as a target member in real-time", value="start"),
            app_commands.Choice(name="Stop - End your current active imitation session", value="stop"),
            app_commands.Choice(name="Status - Check current session status", value="status")
        ]
    )
    @app_commands.describe(
        action="The session action to perform",
        member="The guild member to imitate (Only required for 'Start')"
    )
    async def imitate_session(
        self, 
        interaction: discord.Interaction, 
        action: str, 
        member: discord.Member = None
    ):
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        if action == "start":
            if not member:
                await interaction.response.send_message("❌ You must specify a member to start imitating.", ephemeral=True)
                return
            
            # Check bot permissions
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ Sessions can only be managed in server text channels.", ephemeral=True)
                return

            permissions = interaction.channel.permissions_for(interaction.guild.me)
            if not permissions.manage_webhooks or not permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ I need **Manage Webhooks** and **Manage Messages** permissions in this channel to run an imitation session.", 
                    ephemeral=True
                )
                return

            # Start session in database
            database.start_imitation_session(user_id, member.id, guild_id)
            await interaction.response.send_message(
                f"🎭 **Imitation Session Started!**\n"
                f"Every message you send in this server will now be deleted and sent as **{member.display_name}**.\n"
                f"To end this session, run `/imitate-session action:Stop`.", 
                ephemeral=True
            )
            logger.info(f"User {interaction.user} (ID: {user_id}) started imitating {member} (ID: {member.id}) in guild {guild_id}")

        elif action == "stop":
            was_stopped = database.stop_imitation_session(user_id, guild_id)
            if was_stopped:
                await interaction.response.send_message("🎭 **Imitation Session Stopped.** You are now speaking as yourself.", ephemeral=True)
                logger.info(f"User {interaction.user} stopped their imitation session in guild {guild_id}")
            else:
                await interaction.response.send_message("❌ You do not have an active imitation session in this server.", ephemeral=True)

        elif action == "status":
            target_id = database.get_imitation_session(user_id, guild_id)
            if target_id:
                try:
                    target_member = interaction.guild.get_member(int(target_id))
                    if not target_member:
                        target_member = await interaction.guild.fetch_member(int(target_id))
                    name = target_member.display_name if target_member else f"User ID: {target_id}"
                except Exception:
                    name = f"User ID: {target_id}"
                
                await interaction.response.send_message(
                    f"🎭 You are currently imitating: **{name}**.\n"
                    f"All your messages in this server are forwarded as them. Run `/imitate-session action:Stop` to end.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("🎭 You do not have any active imitation session. You are speaking as yourself.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Imitation(bot))
