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
TOKEN = "8741407408:AAEh6x5uz7p-fsQ0UO0XXFloSnWXAU_aMbg"
ADMIN_ID = 552671626
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- PROFESSIONAL YUKLASH FUNKSIYASI (KUCHAYTIRILGAN) ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'geo_bypass': True,
        'nocheckcertificate': True,
        # Brauzer simulyatsiyasi (Blokdan qochish uchun)
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        # Maxsus mijozlar simulyatsiyasi (Instagram va YouTube uchun)
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']}, 
            'instagram': {'check_headers': True}
        },
        # HTTP Headerlarni kuchaytirish
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }

    if mode == "video":
        # Sifatni 720p bilan cheklash va MP4 formatini majburlash
        ydl_opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
    elif mode == "audio" or mode == "search":
        ydl_opts['format'] = 'bestaudio/best'
        if mode == "search": url = f"ytsearch1:{url}"
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info: info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            if mode in ["audio", "search"]:
                filename = os.path.splitext(filename)[0] + ".mp3"
            return filename, info.get('title', 'Media')
        except Exception as e:
            logger.error(f"Yuklashda xato: {e}")
            return None, None

# --- FASTAPI LIFESPAN (Conflict xatosini yo'qotadi) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bot yonganda eski webhook va chigalliklarni tozalaydi
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- XABARLARNI QAYTA ISHLASH ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    await m.answer("👋 Salom! Link yuboring (Instagram, YouTube, Pinterest) yoki musiqa nomini yozing!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("http"):
        # Link bo'lsa tanlov tugmalarini chiqarish
        link_id = uuid.uuid4().hex[:12]
        url_storage[link_id] = message.text
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎬 Video (720p)", callback_data=f"v|{link_id}"),
            InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"a|{link_id}")
        ]])
        await message.answer(f"📌 Media aniqlandi. Nima yuklaymiz?", reply_markup=kb)
    else:
        # Link bo'lmasa musiqa deb qidirish
        status = await message.answer("🎵 Musiqa qidirilmoqda...")
        loop = asyncio.get_running_loop()
        path, title = await loop.run_in_executor(thread_pool, download_media, message.text, "search")
        if path and os.path.exists(path):
            await message.answer_audio(audio=FSInputFile(path), title=title, caption="@falsebird_bot")
            os.remove(path)
            await status.delete()
        else:
            await status.edit_text("❌ Musiqa topilmadi.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def dl_callback(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    mode = "video" if prefix == "v" else "audio"
    
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    loop = asyncio.get_running_loop()
    path, title = await loop.run_in_executor(thread_pool, download_media, url, mode)
    
    if path and os.path.exists(path):
        if os.path.getsize(path) > 50 * 1024 * 1024: # 50MB limit tekshiruvi
            await status_msg.edit_text("⚠️ Kechirasiz, fayl 50MB dan katta. Uni yuborib bo'lmaydi.")
        else:
            await status_msg.edit_text("📤 Telegramga yuklanmoqda...")
            try:
                if mode == "video":
                    await callback.message.answer_video(video=FSInputFile(path), caption=f"✅ {title}\n@falsebird_bot")
                else:
                    await callback.message.answer_audio(audio=FSInputFile(path), title=title)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ Telegramga yuborishda xato.")
        os.remove(path)
    else:
        await status_msg.edit_text("❌ Xato: Platforma blokladi yoki link noto'g'ri. Birozdan so'ng qayta urining.")

@app.get("/")
async def root(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
