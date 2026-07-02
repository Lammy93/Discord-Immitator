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
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                if webhook.user == self.bot.user or webhook.name == "BotImitator":
                    return webhook
            
            logger.info(f"Creating new webhook 'BotImitator' in channel: {channel.name} ({channel.id})")
            return await channel.create_webhook(name="BotImitator", reason="Used for member imitation features.")
        except Exception as e:
            logger.error(f"Failed to get/create webhook in channel {channel.id}: {e}", exc_info=True)
            raise

    # --- Listener for active sessions ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        target_id = database.get_imitation_session(message.author.id, message.guild.id)
        if not target_id:
            return

        try:
            target_member = message.guild.get_member(int(target_id))
            if not target_member:
                target_member = await message.guild.fetch_member(int(target_id))

            if not target_member:
                database.stop_imitation_session(message.author.id, message.guild.id)
                logger.warning(f"Target member {target_id} not found. Ended session for {message.author.id}.")
                return

            webhook = await self.get_or_create_webhook(message.channel)

            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(f"Missing Manage Messages permission in guild {message.guild.id}")

            files = []
            if message.attachments:
                for attachment in message.attachments:
                    try:
                        files.append(await attachment.to_file())
                    except Exception as e:
                        logger.error(f"Failed to download attachment {attachment.url}: {e}")

            content = message.content if message.content else None
            
            await webhook.send(
                content=content,
                username=target_member.display_name,
                avatar_url=target_member.display_avatar.url,
                files=files,
                embeds=message.embeds,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
            )
        except Exception as e:
            logger.error(f"Error in on_message imitation forwarding: {e}", exc_info=True)


    # --- Direct Imitation Commands ---
    @app_commands.command(
        name="imitate",
        description="Send a single message imitating another member."
    )
    @app_commands.describe(member="The guild member to imitate", message="Message to send")
    async def imitate(self, interaction: discord.Interaction, member: discord.Member, message: str):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in server text channels.", ephemeral=True)
            return

        permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not permissions.manage_webhooks:
            await interaction.response.send_message("❌ I need **Manage Webhooks** permission in this channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            webhook = await self.get_or_create_webhook(interaction.channel)
            await webhook.send(
                content=message,
                username=member.display_name,
                avatar_url=member.display_avatar.url,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
            )
            await interaction.followup.send(f"✅ Sent message imitating **{member.display_name}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to run /imitate: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to send the imitated message.", ephemeral=True)

    @app_commands.command(
        name="imitate-preset",
        description="Send a single message imitating a saved member preset."
    )
    @app_commands.describe(preset_name="The name of the saved preset", message="Message to send")
    async def imitate_preset(self, interaction: discord.Interaction, preset_name: str, message: str):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in server text channels.", ephemeral=True)
            return

        # Retrieve preset
        member_id = database.get_member_preset(preset_name, interaction.user.id, interaction.guild.id)
        if not member_id:
            await interaction.response.send_message(f"❌ Preset `{preset_name}` not found. Create one with `/copy-preset add`.", ephemeral=True)
            return

        permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not permissions.manage_webhooks:
            await interaction.response.send_message("❌ I need **Manage Webhooks** permission in this channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            target_member = interaction.guild.get_member(int(member_id))
            if not target_member:
                target_member = await interaction.guild.fetch_member(int(member_id))

            webhook = await self.get_or_create_webhook(interaction.channel)
            await webhook.send(
                content=message,
                username=target_member.display_name if target_member else f"Preset: {preset_name}",
                avatar_url=target_member.display_avatar.url if target_member else None,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
            )
            await interaction.followup.send(f"✅ Sent message imitating preset **{preset_name}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to run /imitate-preset: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to send the imitated message.", ephemeral=True)

    # --- Imitation Sessions Commands ---
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.command(
        name="imitate-session",
        description="Manage your real-time member imitation session."
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Start (Direct Member)", value="start"),
            app_commands.Choice(name="Start (Saved Preset)", value="start_preset"),
            app_commands.Choice(name="Stop", value="stop"),
            app_commands.Choice(name="Status", value="status")
        ]
    )
    @app_commands.describe(
        action="The session action to perform",
        member="The member to imitate (for 'Start Direct')",
        preset_name="The preset to use (for 'Start Preset')"
    )
    async def imitate_session(
        self, 
        interaction: discord.Interaction, 
        action: str, 
        member: discord.Member = None,
        preset_name: str = None
    ):
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        if action == "start":
            if not member:
                await interaction.response.send_message("❌ You must specify a member for direct start.", ephemeral=True)
                return
            target_id = member.id
        
        elif action == "start_preset":
            if not preset_name:
                await interaction.response.send_message("❌ You must specify a preset name.", ephemeral=True)
                return
            target_id = database.get_member_preset(preset_name, user_id, guild_id)
            if not target_id:
                await interaction.response.send_message(f"❌ Preset `{preset_name}` not found.", ephemeral=True)
                return

        elif action == "stop":
            was_stopped = database.stop_imitation_session(user_id, guild_id)
            if was_stopped:
                await interaction.response.send_message("🎭 **Session Stopped.** You are now yourself.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ No active session found.", ephemeral=True)
            return

        elif action == "status":
            target_id = database.get_imitation_session(user_id, guild_id)
            if target_id:
                try:
                    target_member = interaction.guild.get_member(int(target_id)) or await interaction.guild.fetch_member(int(target_id))
                    name = target_member.display_name if target_member else f"ID: {target_id}"
                except Exception:
                    name = f"ID: {target_id}"
                await interaction.response.send_message(f"🎭 Imitating: **{name}**.", ephemeral=True)
            else:
                await interaction.response.send_message("🎭 No active session.", ephemeral=True)
            return

        # Logic for starting session (shared by both direct and preset)
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Text channels only.", ephemeral=True)
            return

        permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not permissions.manage_webhooks or not permissions.manage_messages:
            await interaction.response.send_message("❌ I need **Manage Webhooks** and **Manage Messages** permissions.", ephemeral=True)
            return

        database.start_imitation_session(user_id, target_id, guild_id)
        
        # Find display name for the response
        display_name = "Unknown"
        try:
            tm = interaction.guild.get_member(int(target_id)) or await interaction.guild.fetch_member(int(target_id))
            display_name = tm.display_name if tm else "Unknown"
        except Exception: pass

        await interaction.response.send_message(
            f"🎭 **Imitation Session Started!**\n"
            f"You are now speaking as **{display_name}**. Run `/imitate-session action:Stop` to end.", 
            ephemeral=True
        )

    # --- Member Preset Management ---
    @app_commands.group(name="copy-preset", description="Manage your saved member 'copies' (presets)")
    async def copy_preset_group(self, interaction: discord.Interaction):
        pass

    @copy_preset_group.command(
        name="add",
        description="Save a member as a named preset."
    )
    @app_commands.describe(name="Name for the preset (e.g. 'TheBoss')", member="Member to save")
    async def preset_add(self, interaction: discord.Interaction, name: str, member: discord.Member):
        success = database.add_member_preset(name, member.id, interaction.guild.id, interaction.user.id)
        if success:
            await interaction.response.send_message(f"✅ Saved **{member.display_name}** as preset `{name}`!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Preset name `{name}` is already taken by you in this server.", ephemeral=True)

    @copy_preset_group.command(
        name="list",
        description="List all your saved member presets."
    )
    async def preset_list(self, interaction: discord.Interaction):
        presets = database.get_user_presets(interaction.user.id, interaction.guild.id)
        if not presets:
            await interaction.response.send_message("📂 You haven't saved any member presets yet. Use `/copy-preset add`.", ephemeral=True)
            return

        list_text = "\n".join([f"• `{p['preset_name']}` (ID: {p['member_id']})" for p in presets])
        await interaction.response.send_message(f"📂 **Your Saved Member Copies:**\n{list_text}", ephemeral=True)

    @copy_preset_group.command(
        name="remove",
        description="Remove a saved member preset."
    )
    @app_commands.describe(name="The name of the preset to delete")
    async def preset_remove(self, interaction: discord.Interaction, name: str):
        success = database.delete_member_preset(name, interaction.user.id, interaction.guild.id)
        if success:
            await interaction.response.send_message(f"🗑️ Removed preset `{name}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Preset `{name}` not found.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Imitation(bot))
