import os, asyncio, logging, uuid, sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

# --- KONFIGURATSIYA ---
TOKEN = "8741407408:AAGI--KXvxpKbjXeXYPu5OXYhM3s43p5jQ4"
CHANNELS = ["@falsebird"] 
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
url_storage = {}

# --- DATABASE TIZIMI (SQLite) ---
def init_db():
    with sqlite3.connect('bot_cache.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS cache 
                      (url TEXT, file_id TEXT, mode TEXT)''')
        conn.commit()

def get_from_cache(url, mode):
    with sqlite3.connect('bot_cache.db') as conn:
        cursor = conn.execute("SELECT file_id FROM cache WHERE url=? AND mode=?", (url, mode))
        result = cursor.fetchone()
        return result[0] if result else None

def add_to_cache(url, file_id, mode):
    with sqlite3.connect('bot_cache.db') as conn:
        conn.execute("INSERT INTO cache VALUES (?, ?, ?)", (url, file_id, mode))
        conn.commit()

# --- MAJBURIY OBUNA ---
async def check_sub(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logging.error(f"Obuna tekshirishda xato: {e}")
            return False 
    return True

# --- PROFESSIONAL YUKLASH FUNKSIYASI ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        # Blokdan qochish uchun maxsus sozlamalar
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        'geo_bypass': True,
        'retries': 3,
        'socket_timeout': 30,
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    }

    if mode == "video":
        # RAMni tejash va renderda "crash" bermaslik uchun tayyor mp4 qidiradi
        ydl_opts['format'] = 'best[ext=mp4]/bestvideo[height<=720]+bestaudio/best'
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    with YoutubeDL(ydl_opts) as ydl:
        for attempt in range(2): # 2 marta urinish
            try:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if mode == "audio":
                    filename = os.path.splitext(filename)[0] + ".mp3"
                return filename, info.get('title', 'Media'), info.get('webpage_url', url)
            except Exception as e:
                logging.error(f"Urinish {attempt+1} xatosi: {e}")
                continue
        return None, None, None

# --- RENDER LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()

app = FastAPI(lifespan=lifespan)

# --- HANDLERS ---
@dp.message(Command("start"))
async def start(m: types.Message):
    if not await check_sub(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Kanalga obuna bo'lish", url=f"https://t.me/{CHANNELS[0][1:]}"),
            InlineKeyboardButton(text="Tekshirish ✅", callback_data="check_again")
        ]])
        return await m.answer(f"Botdan foydalanish uchun {CHANNELS[0]} kanaliga obuna bo'ling!", reply_markup=kb)
    await m.answer("👋 Salom! Ijtimoiy tarmoq linkini yuboring, men uni Video yoki MP3 qilib beraman!")

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
    if not url: return await callback.answer("❌ Link muddati o'tgan.")

    mode = "video" if mode_code == "v" else "audio"
    
    # 1. Keshni tekshirish (Tezlik va resurs tejamkorligi)
    cached_id = get_from_cache(url, mode)
    if cached_id:
        try:
            if mode == "video": await callback.message.answer_video(video=cached_id, caption="⚡️ Keshdan yuborildi")
            else: await callback.message.answer_audio(audio=cached_id, caption="⚡️ Keshdan yuborildi")
            return await callback.message.delete()
        except:
            pass # Agar keshdagi file_id o'chib ketgan bo'lsas qaytadan yuklaydi

    await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    loop = asyncio.get_running_loop()
    path, title, _ = await loop.run_in_executor(None, download_media, url, mode)
    
    if path and os.path.exists(path):
        size = os.path.getsize(path) / (1024 * 1024)
        if size > 49:
            await callback.message.edit_text(f"⚠️ Telegram limiti 50MB. Fayl esa {size:.1f}MB.\n"
                                             f"Link: {url}")
            os.remove(path)
            return

        await callback.message.edit_text("📤 Yuklanmoqda...")
        try:
            if mode == "video":
                msg = await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}\n@falsebird_bot")
                add_to_cache(url, msg.video.file_id, mode)
            else:
                msg = await callback.message.answer_audio(audio=FSInputFile(path), title=title)
                add_to_cache(url, msg.audio.file_id, mode)
        finally:
            if os.path.exists(path): os.remove(path)
            await callback.message.delete()
    else:
        await callback.message.edit_text("❌ Xato: Videoni yuklab bo'lmadi. IP bloklangan bo'lishi mumkin yoki link noto'g'ri. Birozdan so'ng qayta urinib ko'ring!")

@app.get("/")
async def root(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

