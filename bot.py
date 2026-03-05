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
TOKEN = "8741407408:AAHOdJlvXL77wxBl9bNHp6gJw_GtFtIhiGg"
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- PROFESSIONAL YUKLASH VA QIDIRUV ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    if mode == "video":
        ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    
    elif mode in ["audio", "search"]:
        # YouTube Music bazasidan professional qidiruv
        target_url = f"ytsearch1:{url}" if mode == "search" else url
        ydl_opts.update({
            'format': 'bestaudio/best',
            'writethumbnail': True,
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                {'key': 'FFmpegMetadata'},
                {'key': 'EmbedThumbnail'},
            ],
        })
        url = target_url

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info: info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            if mode in ["audio", "search"]:
                filename = os.path.splitext(filename)[0] + ".mp3"
            return filename, info.get('title', 'Media'), info.get('duration', 0)
        except Exception as e:
            logger.error(f"Xato: {e}")
            return None, None, None

# --- FASTAPI LIFESPAN (Conflict'ni "o'ldiradigan" qism) ---
# --- FASTAPI LIFESPAN (Barcha Conflict'larni o'ldiruvchi versiya) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Telegramdagi barcha eski "osilib" qolgan ulanishlarni tozalaymiz
    logger.info("Conflict'larga qarshi majburiy tozalash boshlandi...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    # 2. Render eski nusxani o'chirishi uchun 10 soniya kutamiz
    # Bu vaqt ichida Telegram eski nusxani "yo'qotib" qo'yadi
    await asyncio.sleep(10) 
    
    # 3. Faqat shundan keyin yangi botni ishga tushiramiz
    polling_task = asyncio.create_task(dp.start_polling(bot, drop_pending_updates=True))
    logger.info("Bot yagona nusxada muvaffaqiyatli ishga tushdi!")
    
    yield
    
    # Bot o'chayotganda sessiyani toza yopamiz
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    await m.answer("🎵 Musiqa nomini yozing yoki Instagram/YouTube linkini yuboring!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("http"):
        link_id = uuid.uuid4().hex[:12]
        url_storage[link_id] = message.text
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎬 Video", callback_data=f"v|{link_id}"),
            InlineKeyboardButton(text="🎵 Audio", callback_data=f"a|{link_id}")
        ]])
        await message.answer(f"📌 Tanlang:", reply_markup=kb)
    else:
        status = await message.answer("🔍 Qidirilmoqda...")
        loop = asyncio.get_running_loop()
        path, title, duration = await loop.run_in_executor(thread_pool, download_media, message.text, "search")
        if path and os.path.exists(path):
            await message.answer_audio(
                audio=FSInputFile(path), 
                title=title, 
                caption=f"✅ {title}\n@falsebird_bot",
                duration=duration
            )
            os.remove(path)
            await status.delete()
        else:
            await status.edit_text("❌ Topilmadi.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def dl_callback(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ Tayyorlanmoqda...")
    loop = asyncio.get_running_loop()
    path, title, duration = await loop.run_in_executor(thread_pool, download_media, url, mode)
    if path and os.path.exists(path):
        try:
            if mode == "video":
                await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}")
            else:
                await callback.message.answer_audio(audio=FSInputFile(path), title=title, duration=duration)
            await status_msg.delete()
        except:
            await status_msg.edit_text("❌ Xato.")
        os.remove(path)
    else:
        await status_msg.edit_text("❌ Yuklab bo'lmadi.")

@app.get("/")
async def root(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

