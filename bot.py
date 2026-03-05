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
# Tokenni bu yerda qoldirishingiz yoki Render Environment'ga BOT_TOKEN deb kiritishingiz mumkin
TOKEN = "8741407408:AAEh6x5uz7p-fsQ0UO0XXFloSnWXAU_aMbg"
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- FASTAPI QISMI (Render uchun shart) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Falsebird Bot v5.2 Professional Mode Active!")
    # Botni polling rejimida alohida task qilib ishga tushiramiz
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- YUKLASH LOGIKASI ---
def download_media(url, mode="video"):
    file_id = f"{uuid.uuid4().hex}"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    if mode == "video":
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'Media')
        filename = ydl.prepare_filename(info)
        
        # Audio rejimda kengaytmani .mp3 ga to'g'irlash
        if mode == "audio":
            base, _ = os.path.splitext(filename)
            filename = f"{base}.mp3"
            
        return filename, title

# --- HANDLERS ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("🌟 **BlueSave Pro v5.2 Active!**\n\nYouTube, Instagram, TikTok yoki Pinterest linkini yuboring!")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text
    msg = await message.answer("🔍 Havola tekshirilmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        def fetch_info():
            with YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(thread_pool, fetch_info)
        
        link_id = uuid.uuid4().hex[:10]
        url_storage[link_id] = url
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Video MP4", callback_data=f"v|{link_id}"),
                InlineKeyboardButton(text="🎵 Musiqa MP3", callback_data=f"a|{link_id}")
            ]
        ])
        
        title = info.get('title', 'Video')[:50]
        await msg.delete()
        await message.reply(f"📌 **Nomi:** {title}\n\nFormatni tanlang:", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Info Error: {e}")
        await msg.edit_text("❌ Xatolik: Linkni o'qib bo'lmadi yoki media yopiq.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def process_download(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    
    if not url:
        await callback.answer("❌ Seans muddati tugagan. Linkni qayta yuboring.", show_alert=True)
        return

    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} yuklanmoqda (kutib turing)...")
    
    try:
        loop = asyncio.get_running_loop()
        file_path, title = await loop.run_in_executor(thread_pool, download_media, url, mode)
        
        if os.path.exists(file_path):
            await status_msg.edit_text("📤 Telegramga yuborilmoqda...")
            media = FSInputFile(file_path)
            
            if mode == "video":
                await callback.message.answer_video(video=media, caption=f"✅ {title}")
            else:
                await callback.message.answer_audio(audio=media, title=title, caption=f"✅ {title}")
            
            os.remove(file_path) # Faylni o'chirish
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Xato: Fayl topilmadi.")
            
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:50]}...")

@app.get("/")
async def root():
    return {"status": "online", "bot": "Falsebird"}

# --- SERVERNI ISHGA TUSHIRISH ---
if __name__ == "__main__":
    # Render PORT muhit o'zgaruvchisini avtomatik beradi
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
