import os, asyncio, logging, uuid, sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

# --- KONFIGURATSIYA ---
TOKEN = "8741407408:AAHOdJlvXL77wxBl9bNHp6gJw_GtFtIhiGg"
CHANNELS = ["@falsebird"] # O'zingizning kanalingizni yozing (masalan: @uz_python)
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
url_storage = {}

# --- DATABASE SOZLAMALARI ---
def init_db():
    conn = sqlite3.connect('bot_cache.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS cache 
                      (url TEXT, file_id TEXT, mode TEXT)''')
    conn.commit()
    conn.close()

def get_from_cache(url, mode):
    conn = sqlite3.connect('bot_cache.db')
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM cache WHERE url=? AND mode=?", (url, mode))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def add_to_cache(url, file_id, mode):
    conn = sqlite3.connect('bot_cache.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cache VALUES (?, ?, ?)", (url, file_id, mode))
    conn.commit()
    conn.close()

# --- OBUNANI TEKSHIRISH ---
async def check_sub(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False # Bot admin bo'lmasa yoki kanal topilmasa
    return True

# --- YUKLASH FUNKSIYASI ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    ydl_opts = {
        'quiet': True, 'no_warnings': True, 'nocheckcertificate': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...',
    }
    if mode == "video":
        ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if mode == "audio": filename = os.path.splitext(filename)[0] + ".mp3"
            return filename, info.get('title', 'Media'), info.get('webpage_url', url)
        except Exception:
            return None, None, None

# --- RENDER LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db() # Bazani ishga tushirish
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()

app = FastAPI(lifespan=lifespan)

@dp.message(Command("start"))
async def start(m: types.Message):
    if not await check_sub(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Kanalga obuna bo'lish", url=f"https://t.me/{CHANNELS[0][1:]}"),
            InlineKeyboardButton(text="Tekshirish ✅", callback_data="check_again")
        ]])
        return await m.answer(f"Botdan foydalanish uchun {CHANNELS[0]} kanaliga obuna bo'ling!", reply_markup=kb)
    await m.answer("👋 Salom! Link yuboring, men uni Video yoki MP3 qilib beraman!")

@dp.callback_query(F.data == "check_again")
async def check_again(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.edit_text("Rahmat! Endi link yuborishingiz mumkin.")
    else:
        await call.answer("Hali obuna bo'lmadingiz ❌", show_alert=True)

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    if not await check_sub(message.from_user.id):
        return await start(message)

    link_id = uuid.uuid4().hex[:10]
    url_storage[link_id] = message.text
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Video", callback_data=f"dl|v|{link_id}"),
        InlineKeyboardButton(text="🎵 MP3", callback_data=f"dl|a|{link_id}")
    ]])
    await message.answer("📌 Tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("dl|"))
async def process_download(callback: types.CallbackQuery):
    _, mode_code, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    if not url: return await callback.answer("❌ Link topilmadi.")

    mode = "video" if mode_code == "v" else "audio"
    
    # 1. Keshni tekshirish
    cached_id = get_from_cache(url, mode)
    if cached_id:
        await callback.message.edit_text("⚡️ Tezkor yuborish (keshdan)...")
        if mode == "video": await callback.message.answer_video(video=cached_id)
        else: await callback.message.answer_audio(audio=cached_id)
        return await callback.message.delete()

    await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    loop = asyncio.get_running_loop()
    path, title, clean_url = await loop.run_in_executor(None, download_media, url, mode)
    
    if path and os.path.exists(path):
        size = os.path.getsize(path) / (1024 * 1024)
        
        # 50MB dan kattalar uchun yechim
        if size > 49:
            await callback.message.edit_text(f"⚠️ Fayl {size:.1f}MB! Telegram limiti 50MB.\n"
                                             f"Mana yuklash uchun havola: [Havola]({url})", parse_mode="Markdown")
            os.remove(path)
            return

        await callback.message.edit_text("📤 Yuklanmoqda...")
        try:
            if mode == "video":
                msg = await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}")
                add_to_cache(url, msg.video.file_id, mode)
            else:
                msg = await callback.message.answer_audio(audio=FSInputFile(path), title=title)
                add_to_cache(url, msg.audio.file_id, mode)
        finally:
            os.remove(path)
            await callback.message.delete()
    else:
        await callback.message.edit_text("❌ Yuklab bo'lmadi.")

@app.get("/")
async def root(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

