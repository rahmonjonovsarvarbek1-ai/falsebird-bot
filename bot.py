import os, asyncio, logging, uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
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

# --- MUSIQANI YUKLASH FUNKSIYASI ---
def get_audio(url):
    file_id = uuid.uuid4().hex
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = f"{DOWNLOAD_PATH}{file_id}.mp3"
            return filename, info.get('title', 'Musiqa')
        except Exception as e:
            logging.error(f"Xato: {e}")
            return None, None

# --- RENDER UCHUN LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(5) # Conflict'ga qarshi
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()

app = FastAPI(lifespan=lifespan)

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("👋 Salom! Instagram yoki YouTube linkini yuboring, men uni MP3 qilib beraman!")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    status = await message.answer("⏳ Musiqa tayyorlanmoqda (Link tahlil qilinmoqda)...")
    
    loop = asyncio.get_running_loop()
    path, title = await loop.run_in_executor(None, get_audio, message.text)
    
    if path and os.path.exists(path):
        await status.edit_text("📤 Telegramga yuklanmoqda...")
        await message.answer_audio(audio=FSInputFile(path), title=title, caption="@falsebird_bot")
        os.remove(path)
        await status.delete()
    else:
        await status.edit_text("❌ Xato: Bu linkdan musiqa olib bo'lmadi. Linkni tekshiring yoki Instagram bo'lsa, cookies yuklang.")

@app.get("/")
async def root(): return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
