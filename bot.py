import os, asyncio, logging, uuid, json
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

# --- KONFIGURATSIYA ---
TOKEN = "8741407408:AAE6E20-Hzt83haYdSBl9Tfx43ILuK5pVqo"
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- PROFESSIONAL YUKLASH VA QIDIRUV FUNKSIYASI ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        # 'cookiefile': 'cookies.txt', # Instagram uchun kerak bo'lsa buni yoqing
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']}, 
            'instagram': {'check_headers': True}
        }
    }

    if mode == "video":
        ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    
    elif mode in ["audio", "search"]:
        # Professional musiqa sifati va qidiruv (YouTube Music manbasi)
        target_url = f"ytsearch1:{url}" if mode == "search" else url
        ydl_opts.update({
            'format': 'bestaudio/best',
            'writethumbnail': True, # Muqovani olish
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                },
                {'key': 'FFmpegMetadata'}, # Metadata qo'shish (Artist, Title)
                {'key': 'EmbedThumbnail'},  # Rasmni MP3 ichiga joylash
            ],
        })
        url = target_url

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info: info = info['entries'][0]
            
            # Fayl nomini olish (mp3 yoki mp4 ekanligini hisobga olgan holda)
            filename = ydl.prepare_filename(info)
            if mode in ["audio", "search"]:
                filename = os.path.splitext(filename)[0] + ".mp3"
                
            return filename, info.get('title', 'Media'), info.get('duration', 0)
        except Exception as e:
            logger.error(f"Yuklashda xato: {e}")
            return None, None, None

# --- FASTAPI LIFESPAN (Render uchun maxsus) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Eski webhookni tozalash
    await bot.delete_webhook(drop_pending_updates=True)
    
    # 2. Conflict xatosiga qarshi 5 soniya kutish
    logger.info("Conflict oldini olish uchun 5 soniya kutilmoqda...")
    await asyncio.sleep(5) 
    
    polling_task = asyncio.create_task(dp.start_polling(bot, drop_pending_updates=True))
    logger.info("Bot ishga tushdi!")
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- BOT HANDLERLARI ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    await m.answer("👋 Salom! Link yuboring yoki musiqa nomini yozing!\nMen eng yaxshi sifatda yuklab beraman.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("http"):
        link_id = uuid.uuid4().hex[:12]
        url_storage[link_id] = message.text
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎬 Video (720p)", callback_data=f"v|{link_id}"),
            InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"a|{link_id}")
        ]])
        await message.answer(f"📌 Media aniqlandi. Tanlang:", reply_markup=kb)
    else:
        # Profesional Musiqa Qidiruv
        status = await message.answer("🔍 Qidirilmoqda...")
        loop = asyncio.get_running_loop()
        path, title, duration = await loop.run_in_executor(thread_pool, download_media, message.text, "search")
        
        if path and os.path.exists(path):
            await status.edit_text("📤 Yuborilmoqda...")
            await message.answer_audio(
                audio=FSInputFile(path), 
                title=title, 
                caption=f"✅ {title}\n@falsebird_bot",
                duration=duration
            )
            os.remove(path)
            await status.delete()
        else:
            await status.edit_text("❌ Hech narsa topilmadi.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def dl_callback(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    if not url:
        await callback.answer("❌ Xatolik: Link eskirgan.")
        return

    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    
    loop = asyncio.get_running_loop()
    path, title, duration = await loop.run_in_executor(thread_pool, download_media, url, mode)
    
    if path and os.path.exists(path):
        if os.path.getsize(path) > 49 * 1024 * 1024:
            await status_msg.edit_text("⚠️ Fayl hajmi 50MB dan katta.")
        else:
            await status_msg.edit_text("📤 Yuklanmoqda...")
            try:
                if mode == "video":
                    await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}\n@falsebird_bot")
                else:
                    await callback.message.answer_audio(audio=FSInputFile(path), title=title, duration=duration)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ Xato: {e}")
        os.remove(path)
    else:
        await status_msg.edit_text("❌ Yuklab bo'lmadi. Linkni tekshiring.")

@app.get("/")
async def root(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
