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

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

class ImitateRequest(BaseModel):
    member_id: str

class VoiceJoinRequest(BaseModel):
    channel_id: str

class SoundPlayRequest(BaseModel):
    sound_name: str

@app.get("/api/status")
async def get_status():
    bot = app.state.bot
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return JSONResponse(status_code=404, content={"error": "Bot is not in any guild"})
    
    # Check active sessions for the bot user (or just a general status)
    # Since the bot doesn't 'imitate' itself, we'll report the first active session it finds
    # or just the voice status.
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    
    return {
        "guild_name": guild.name,
        "voice_channel": voice_client.channel.name if voice_client and voice_client.channel else None,
        "is_connected": voice_client is not None
    }

@app.get("/api/members")
async def get_members():
    bot = app.state.bot
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        raise HTTPException(status_code=404, detail="Bot is not in any guild")
    
    members = []
    async for member in guild.fetch_members(limit=None):
        members.append({
            "id": str(member.id),
            "name": member.display_name,
            "avatar": str(member.display_avatar.url)
        })
    
    return members

@app.post("/api/imitate")
async def imitate_member(req: ImitateRequest):
    bot = app.state.bot
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        raise HTTPException(status_code=404, detail="Bot is not in any guild")
    
    try:
        member = await guild.fetch_member(int(req.member_id))
        # Use a dummy user_id for the "Web UI" controller
        # In a real app, you'd authenticate the user.
        # We'll use the bot's own ID or a fixed "admin" ID.
        database.start_imitation_session("web_admin", member.id, guild.id)
        return {"status": "success", "message": f"Now imitating {member.display_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/sounds")
async def list_sounds():
    sounds = database.get_all_soundbites()
    return [dict(s) for s in sounds]

@app.post("/api/sound/play")
async def play_sound(req: SoundPlayRequest):
    bot = app.state.bot
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        raise HTTPException(status_code=404, detail="Bot is not in any guild")
    
    sound = database.get_soundbite(req.sound_name)
    if not sound:
        raise HTTPException(status_code=404, detail="Sound not found")
    
    # We need a voice channel to play in. 
    # If the bot isn't in one, it can't play.
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if not voice_client:
        raise HTTPException(status_code=400, detail="Bot is not in a voice channel. Join one first via the UI.")

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
    # Save file locally
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{name.lower()}{ext}"
    file_path = os.path.join("sounds", filename)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    success = database.add_soundbite(name, file_path, "WebUI Admin")
    if not success:
        # Cleanup
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Sound name already exists")
    
    return {"status": "success", "message": f"Uploaded {name}"}

@app.get("/api/channels")
async def get_voice_channels():
    bot = app.state.bot
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        raise HTTPException(status_code=404, detail="Bot is not in any guild")
    
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
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        raise HTTPException(status_code=404, detail="Bot is not in any guild")
    
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

# Serve static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")
