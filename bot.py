import os
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

# --- SOZLAMALAR ---
TOKEN = "8741407408:AAEh6x5uz7p-fsQ0UO0XXFloSnWXAU_aMbg"
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- FASTAPI / LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "-"*30)
    print("✅ Falsebird-bot siz uchun tayyor!")
    print("🚀 Video yoki post linkini yuboring, men uni topaman!")
    print("-"*30 + "\n")
    
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()
    print("🛑 Falsebird-bot to'xtatildi.")

app = FastAPI(lifespan=lifespan)

# --- YUKLASH LOGIKASI (Professional Update) ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    # YouTube blokirovkalarini chetlab o'tish uchun kengaytirilgan sozlamalar
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    
    if mode == "video":
        ydl_opts['format'] = 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info.get('title', 'Video')
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Mp3 kengaytmasini aniq ko'rsatish
            final_name = os.path.splitext(filename)[0] + ".mp3"
            return final_name, info.get('title', 'Audio')

# --- HANDLERS ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("👋 Salom! Men **Falsebird-bot**man.\n\nYouTube, Instagram, TikTok yoki Pinterest linkini yuboring!")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text
    status = await message.answer("🔍 Havola tekshirilmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        def fetch_info():
            # Ma'lumot olishda ham sarlavhalar muhim
            opts = {
                'quiet': True, 
                'nocheckcertificate': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(thread_pool, fetch_info)
        link_id = uuid.uuid4().hex[:12]
        url_storage[link_id] = url
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎬 Video", callback_data=f"v|{link_id}"),
            InlineKeyboardButton(text="🎵 Audio", callback_data=f"a|{link_id}")
        ]])
        
        await status.delete()
        title = info.get('title', 'Media')[:50]
        await message.reply(f"📌 **Nomi:** {title}...\n\nTanlang:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Xato: {e}")
        await status.edit_text("❌ Xato: Havolani o'qib bo'lmadi. (YouTube cheklovi bo'lishi mumkin)")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def process_download(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    if not url:
        await callback.answer("❌ Seans muddati tugagan.", show_alert=True)
        return

    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} yuklanmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        file_path, title = await loop.run_in_executor(thread_pool, download_media, url, mode)
        
        if os.path.exists(file_path):
            await status_msg.edit_text("📤 Telegramga yuborilmoqda...")
            media = FSInputFile(file_path)
            if mode == "video":
                await callback.message.answer_video(video=media, caption=f"✅ {title}\n\n@falsebird_bot")
            else:
                await callback.message.answer_audio(audio=media, title=title, caption=f"✅ {title}\n\n@falsebird_bot")
            
            await status_msg.delete()
            os.remove(file_path)
        else:
            await status_msg.edit_text("❌ Fayl yaratilmadi.")
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text(f"❌ Xatolik: Yuklash rad etildi (YouTube/Instagram blokirovkasi).")

@app.get("/")
async def root():
    return {"status": "active", "bot": "Falsebird-bot"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
