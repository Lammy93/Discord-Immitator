import os
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
    message: str

class VoiceJoinRequest(BaseModel):
    guild_id: str
    channel_id: str

class SoundPlayRequest(BaseModel):
    guild_id: str
    sound_name: str

@app.get("/api/status")
async def get_status():
    bot = app.state.bot
    guilds = bot.guilds
    if not guilds:
        return JSONResponse(status_code=404, content={"error": "Bot is not in any guild", "guilds": []})
    
    guild_list = []
    for g in guilds:
        voice_client = discord.utils.get(bot.voice_clients, guild=g)
        guild_list.append({
            "id": str(g.id),
            "name": g.name,
            "voice_channel": voice_client.channel.name if voice_client and voice_client.channel else None,
            "is_connected": voice_client is not None
        })
    
    return {
        "guilds": guild_list
    }

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
        database.start_imitation_session("web_admin", member.id, guild.id)
        return {"status": "success", "message": f"Now imitating {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/imitate-send")
async def imitate_send(req: ImitateSendMessageRequest):
    bot = app.state.bot
    guild = bot.get_guild(int(req.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    try:
        member = await guild.fetch_member(int(req.member_id))
        
        # Find a text channel to send to. We'll send it to the first available text channel.
        # In a real scenario, you'd pass the channel_id in the request.
        channel = guild.text_channels[0] if guild.text_channels else None
        if not channel:
            raise HTTPException(status_code=404, detail="No text channels found in guild")
            
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
        await voice_client.disconnect()
        return {"status": "success", "message": "Disconnected from voice channel"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
