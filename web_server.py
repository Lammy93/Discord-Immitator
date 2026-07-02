import os
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import database
import discord

logger = logging.getLogger("discord_bot.web_server")

app = FastAPI(title="Discord Imitator Web UI")

# We will inject the bot instance into the app state on startup
def set_bot(bot_instance):
    app.state.bot = bot_instance

async def get_or_create_webhook(bot, channel):
    """Helper to find or create the imitation webhook."""
    webhooks = await channel.webhooks()
    for webhook in webhooks:
        if webhook.user == bot.user or webhook.name == "BotImitator":
            return webhook
    return await channel.create_webhook(name="BotImitator")

class ImitateRequest(BaseModel):
    guild_id: str
    member_id: str

class ImitateSendMessageRequest(BaseModel):
    guild_id: str
    member_id: str
    channel_id: str
    message: str

class VoiceJoinRequest(BaseModel):
    guild_id: str
    channel_id: str = None

class SoundPlayRequest(BaseModel):
    guild_id: str
    sound_name: str

class PresenceRequest(BaseModel):
    status: str  # online, idle, dnd, invisible
    activity_type: str  # playing, watching, listening, competing
    activity_name: str

@app.get("/api/status")
async def get_status():
    bot = app.state.bot
    guilds = bot.guilds
    if not guilds:
        return JSONResponse(status_code=404, content={"error": "Bot is not in any guild", "guilds": []})
    
    guild_list = []
    for g in guilds:
        voice_client = discord.utils.get(bot.voice_clients, guild=g)
        target_id = database.get_imitation_session("web_admin", g.id)
        target_name = None
        target_avatar_url = None
        target_member_id = None
        if target_id:
            try:
                tm = g.get_member(int(target_id)) or await g.fetch_member(int(target_id))
                if tm:
                    target_name = tm.display_name
                    target_avatar_url = str(tm.display_avatar.url)
                    target_member_id = str(tm.id)
            except Exception:
                target_name = f"ID: {target_id}"

        guild_list.append({
            "id": str(g.id),
            "name": g.name,
            "voice_channel": voice_client.channel.name if voice_client and voice_client.channel else None,
            "is_connected": voice_client is not None,
            "imitating": target_name,
            "imitating_avatar_url": target_avatar_url,
            "imitating_member_id": target_member_id
        })
    
    return {
        "guilds": guild_list
    }

@app.post("/api/status/update")
async def update_presence(req: PresenceRequest):
    bot = app.state.bot
    
    # Map status string to discord.Status
    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    
    # Map activity type string to discord.ActivityType
    type_map = {
        "playing": discord.ActivityType.playing,
        "watching": discord.ActivityType.watching,
        "listening": discord.ActivityType.listening,
        "competing": discord.ActivityType.competing
    }
    
    try:
        status = status_map.get(req.status, discord.Status.online)
        act_type = type_map.get(req.activity_type, discord.ActivityType.playing)
        
        await bot.change_presence(
            status=status,
            activity=discord.Activity(type=act_type, name=req.activity_name)
        )
        return {"status": "success", "message": "Presence updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/members")
async def get_members(guild_id: str):
    bot = app.state.bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    members = []
    try:
        async for member in guild.fetch_members(limit=None):
            members.append({
                "id": str(member.id),
                "name": member.display_name,
                "avatar": str(member.display_avatar.url)
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch members: {e}")
    
    return members

@app.post("/api/imitate")
async def imitate_member(req: ImitateRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    try:
        member = await guild.fetch_member(int(req.member_id))
        
        # Attempt to change bot's nickname in this server to match the target
        try:
            await guild.me.edit(nick=member.display_name)
        except discord.Forbidden:
            logger.warning(f"Could not change nickname in guild {guild.id} (Missing Manage Nicknames)")

        database.start_imitation_session("web_admin", member.id, guild.id)
        return {"status": "success", "message": f"Now imitating {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/imitate/reset")
async def reset_imitation(guild_id: str):
    bot = app.state.bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    try:
        # Reset nickname to None (returns it to the default bot name)
        await guild.me.edit(nick=None)
        database.stop_imitation_session("web_admin", guild.id) # This is a bit vague, maybe a better function?
        # Wait, stop_imitation_session needs user_id. a general "clear all" for the admin would be:
        # Let's just clear the specific admin session.
        database.stop_imitation_session("web_admin", guild.id)
        
        return {"status": "success", "message": "Identity reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/imitate-send")
async def imitate_send(req: ImitateSendMessageRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    try:
        member = await guild.fetch_member(int(req.member_id))
        
        # Use the provided channel_id
        channel = guild.get_channel(int(req.channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            raise HTTPException(status_code=400, detail="Invalid text channel")
            
        webhook = await get_or_create_webhook(bot, channel)
        await webhook.send(
            content=req.message,
            username=member.display_name,
            avatar_url=member.display_avatar.url,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
        )
        return {"status": "success", "message": f"Sent message as {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/sounds")
async def list_sounds():
    sounds = database.get_all_soundbites()
    return [dict(s) for s in sounds]

@app.post("/api/sound/play")
async def play_sound(req: SoundPlayRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    sound = database.get_soundbite(req.sound_name)
    if not sound:
        raise HTTPException(status_code=404, detail="Sound not found")
    
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if not voice_client:
        raise HTTPException(status_code=400, detail="Bot is not in a voice channel in this guild. Join one first via the UI.")

    try:
        if voice_client.is_playing():
            voice_client.stop()
        
        audio_source = discord.FFmpegPCMAudio(sound["file_path"])
        voice_client.play(audio_source)
        database.increment_soundbite_count(req.sound_name)
        return {"status": "success", "message": f"Playing {req.sound_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sound/upload")
async def upload_sound(
    name: str = Form(...), 
    file: UploadFile = File(...)
):
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{name.lower()}{ext}"
    file_path = os.path.join("sounds", filename)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    success = database.add_soundbite(name, file_path, "WebUI Admin")
    if not success:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Sound name already exists")
    
    return {"status": "success", "message": f"Uploaded {name}"}

@app.post("/api/sound/upload-multiple")
async def upload_multiple_sounds(files: List[UploadFile] = File(...)):
    results = {"success": [], "failed": []}
    for file in files:
        name = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1].lower()
        filename = f"{name.lower()}{ext}"
        file_path = os.path.join("sounds", filename)

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        ok = database.add_soundbite(name, file_path, "WebUI Admin")
        if ok:
            results["success"].append(name)
        else:
            results["failed"].append(file.filename)

    return {"results": results, "message": f"Uploaded {len(results['success'])} sound(s)"}

@app.get("/api/text-channels")
async def get_text_channels(guild_id: str):
    bot = app.state.bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    channels = []
    for channel in guild.text_channels:
        channels.append({
            "id": str(channel.id),
            "name": channel.name
        })
    return channels

@app.get("/api/channels")
async def get_voice_channels(guild_id: str):
    bot = app.state.bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    channels = []
    for channel in guild.voice_channels:
        channels.append({
            "id": str(channel.id),
            "name": channel.name
        })
    return channels

@app.post("/api/voice/join")
async def join_voice(req: VoiceJoinRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    try:
        channel = guild.get_channel(int(req.channel_id))
        if not channel or not isinstance(channel, discord.VoiceChannel):
            raise HTTPException(status_code=400, detail="Invalid voice channel")
        
        voice_client = discord.utils.get(bot.voice_clients, guild=guild)
        if not voice_client:
            await channel.connect()
        else:
            await voice_client.move_to(channel)
            
        return {"status": "success", "message": f"Joined {channel.name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/disconnect")
async def disconnect_voice(req: VoiceJoinRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if not voice_client:
        raise HTTPException(status_code=400, detail="Bot is not connected to any voice channel")
    
    try:
        if voice_client.is_playing():
            voice_client.stop()
        await voice_client.disconnect()
        return {"status": "success", "message": "Disconnected from voice channel"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
