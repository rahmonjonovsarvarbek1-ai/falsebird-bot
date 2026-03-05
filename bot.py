import os, asyncio, logging, uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

# --- KONFIGURATSIYA ---
TOKEN = "8741407408:AAHOdJlvXL77wxBl9bNHp6gJw_GtFtIhiGg"
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
url_storage = {}

# --- YUKLASH FUNKSIYASI (VIDEO VA AUDIO UCHUN) ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    if mode == "video":
        # Eng yaxshi MP4 video (720p gacha)
        ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    else:
        # Faqat MP3 audio
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if mode == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"
            return filename, info.get('title', 'Media')
        except Exception as e:
            logging.error(f"Xato: {e}")
            return None, None

# --- RENDER LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(5)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()

app = FastAPI(lifespan=lifespan)

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("👋 Salom! Instagram/YouTube linkini yuboring, men uni Video yoki MP3 qilib beraman!")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    link_id = uuid.uuid4().hex[:10]
    url_storage[link_id] = message.text
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Video yuklash", callback_data=f"dl|v|{link_id}"),
        InlineKeyboardButton(text="🎵 MP3 yuklash", callback_data=f"dl|a|{link_id}")
    ]])
    
    await message.answer("📌 Nima yuklamoqchisiz?", reply_markup=kb)

@dp.callback_query(F.data.startswith("dl|"))
async def process_download(callback: types.CallbackQuery):
    _, mode_code, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    
    if not url:
        await callback.answer("❌ Xato: Link muddati o'tgan.")
        return

    mode = "video" if mode_code == "v" else "audio"
    await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    
    loop = asyncio.get_running_loop()
    path, title = await loop.run_in_executor(None, download_media, url, mode)
    
    if path and os.path.exists(path):
        # 50MB dan kattaligini tekshirish (Telegram limiti)
        if os.path.getsize(path) > 48 * 1024 * 1024:
            await callback.message.edit_text("⚠️ Fayl juda katta (50MB+). Bepul server yuklay olmaydi.")
            os.remove(path)
            return

        await callback.message.edit_text("📤 Telegramga yuklanmoqda...")
        if mode == "video":
            await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}\n@falsebird_bot")
        else:
            await callback.message.answer_audio(audio=FSInputFile(path), title=title)
        
        os.remove(path)
        await callback.message.delete()
    else:
        await callback.message.edit_text("❌ Yuklab bo'lmadi. Linkni yoki Cookiesni tekshiring.")

@app.get("/")
async def root(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
