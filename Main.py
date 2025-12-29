import asyncio
import os
import shutil
from collections import deque
from typing import Dict, Deque

# 🔥 CRITICAL FIX: Inject missing error to prevent import crash
import pyrogram.errors
if not hasattr(pyrogram.errors, 'GroupcallForbidden'):
    class GroupcallForbidden(pyrogram.errors.Unauthorized):
        pass
    pyrogram.errors.GroupcallForbidden = GroupcallForbidden

from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant, ChatAdminRequired, BadRequest, UserNotParticipant
import yt_dlp
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped
from pytgcalls.types.stream import StreamAudioEnded
from pytgcalls.exceptions import NoActiveGroupCall, AlreadyJoinedError

# █████████████████ CONFIG — ALL IN ONE FILE (NO ENV!) █████████████████
API_ID = 29732403
API_HASH = "1ba2e95b98a862d07e8af0bd56e1f0fb"
SESSION_STRING = "BQHFrjMAZIzSc4kwDLfgZubobLO42XxLFlQPO_HaG-Exhcswq7mraIsV7Z_NzeohbkGjSIy1j4lbzmc1Fj8VOlBMDe0ZRVUumi_cF1fV0JvtsJhq5a1VmGScVMB21KawV7u_USKSkYxCV3VYtlNP-00pt-BFQTYQo11bCBxTR2erEd0Pd-3soC5_3V-SRM93JD9O0QLk4Zt7imtUiqWDGNPgN1h7-DyevhZDfF8wR7BLcvuBuz8024fkqT5d7hrKkOV6eZ7MOogmo0i8LWdgUHqhtlKckGSuAzDtFg0DC4NWnR0wTY4zDLsYfV3Yj-pHJ9HYSsEOl7Q7oE3VjQJn9wJgXcGNEAAAAAHWyj9cAA"
BOT_TOKEN = "8215252608:AAGmCUZAaRCR1oW6UTPEo_ecTd8I8BbH3Jc"
# █████████████████ END CONFIG — DO NOT SHARE THIS FILE PUBLICLY █████████

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
pytgcalls = PyTgCalls(user)

queues: Dict[int, Deque[dict]] = {}
active_chats: Dict[int, bool] = {}
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def safe_join_chat(chat_id: int):
    try:
        await user.get_chat_member(chat_id, (await user.get_me()).id)
    except UserNotParticipant:
        try:
            invite = await bot.create_chat_invite_link(chat_id, member_limit=1)
            await user.join_chat(invite.invite_link)
        except Exception:
            pass

async def join_vc(chat_id: int):
    await safe_join_chat(chat_id)
    try:
        await pytgcalls.join_group_call(
            chat_id,
            AudioPiped("https://raw.githubusercontent.com/umairshahid123/Telegram-MusicBot/main/silence.mp3"),
            muted=True
        )
        active_chats[chat_id] = True
    except AlreadyJoinedError:
        pass
    except NoActiveGroupCall:
        raise NoActiveGroupCall
    except Exception as e:
        raise e

async def download_song(query: str) -> dict:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if 'entries' in info:
            info = info['entries'][0]
        return {
            'id': info['id'],
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'file': ydl.prepare_filename(info),
        }

def format_duration(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02}"

@bot.on_message(filters.command("play") & filters.group)
async def play(_, message: Message):
    chat_id = message.chat.id
    if len(message.command) < 2:
        return await message.reply("UsageId: `/play <song name>`")
    query = " ".join(message.command[1:])
    msg = await message.reply("🔍 Searching...")
    try:
        song = await download_song(query)
    except Exception:
        return await msg.edit("❌ Song not found.")
    if chat_id not in queues:
        queues[chat_id] = deque()
    queues[chat_id].append(song)
    await msg.edit(f"📥 **Queued**: `{song['title']}`")
    if chat_id not in active_chats or not active_chats[chat_id]:
        try:
            await join_vc(chat_id)
        except NoActiveGroupCall:
            queues[chat_id].pop()
            return await msg.edit("🔈 Start a voice chat first!")
        except Exception as e:
            queues[chat_id].pop()
            return await msg.edit(f"⚠️ Join failed: `{str(e)}`")
    if len(queues[chat_id]) == 1:
        await play_next(chat_id, msg)

async def play_next(chat_id: int, msg: Message = None):
    if not queues.get(chat_id):
        active_chats.pop(chat_id, None)
        return
    song = queues[chat_id][0]
    file_path = song['file']
    if not os.path.exists(file_path):
        queues[chat_id].popleft()
        await play_next(chat_id)
        return
    try:
        await pytgcalls.change_stream(chat_id, AudioPiped(file_path))
        text = f"🎧 **Now Playing**: `{song['title']}`\n⏱️ `{format_duration(song['duration'])}`"
        await (msg.edit(text) if msg else bot.send_message(chat_id, text))
    except Exception:
        queues[chat_id].popleft()
        await (msg.edit("⚠️ Skipped.") if msg else bot.send_message(chat_id, "⚠️ Skipped."))
        await play_next(chat_id)

@pytgcalls.on_stream_end()
async def on_stream_end(_, update: StreamAudioEnded):
    chat_id = update.chat_id
    if chat_id in queues:
        queues[chat_id].popleft()
    await play_next(chat_id)

@bot.on_message(filters.command("pause") & filters.group)
async def pause(_, message: Message):
    chat_id = message.chat.id
    if chat_id not in active_chats:
        return await message.reply("❌ Not playing.")
    try:
        await pytgcalls.pause_stream(chat_id)
        await message.reply("⏸️ Paused.")
    except Exception:
        await message.reply("❌ Already paused.")

@bot.on_message(filters.command("resume") & filters.group)
async def resume(_, message: Message):
    chat_id = message.chat.id
    if chat_id not in active_chats:
        return await message.reply("❌ Nothing paused.")
    try:
        await pytgcalls.resume_stream(chat_id)
        await message.reply("▶️ Resumed.")
    except Exception:
        await message.reply("❌ Already playing.")

@bot.on_message(filters.command("stop") & filters.group)
async def stop(_, message: Message):
    chat_id = message.chat.id
    queues.pop(chat_id, None)
    active_chats.pop(chat_id, None)
    try:
        await pytgcalls.leave_group_call(chat_id)
        await message.reply("⏹️ Left voice chat.")
    except Exception:
        await message.reply("⏹️ Stopped.")

@bot.on_message(filters.command("skip") & filters.group)
async def skip(_, message: Message):
    chat_id = message.chat.id
    if not queues.get(chat_id) or not queues[chat_id]:
        return await message.reply("❌ Nothing to skip.")
    queues[chat_id].popleft()
    await message.reply("⏭️ Skipped.")
    await play_next(chat_id)

@bot.on_message(filters.command("queue") & filters.group)
async def queue_list(_, message: Message):
    chat_id = message.chat.id
    q = queues.get(chat_id)
    if not q:
        return await message.reply("📭 Queue is empty.")
    text = f"**\Queue:**\n▶️ **Now**: `{q[0]['title']}`\n"
    for i, song in enumerate(list(q)[1:6], 1):
        text += f"`{i}.` `{song['title']}`\n"
    await message.reply(text)

@bot.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    await message.reply("✨ Add me to a group, start a voice chat, then use `/play <song>`.")

async def cleanup():
    shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)

async def main():
    await bot.start()
    await user.start()
    await pytgcalls.start()
    me = await bot.get_me()
    print(f"✅ Bot: @{me.username}")
    print("🎶 Ready! Use /play in a group with active voice chat.")
    await idle()
    await cleanup()
    await bot.stop()
    await user.stop()
    await pytgcalls.stop()

if __name__ == "__main__":
    asyncio.run(main())
