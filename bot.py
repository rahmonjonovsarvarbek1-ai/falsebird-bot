import os
import asyncio
import logging
import uuid
import json
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
ADMIN_ID = 552671626  # Sizning ID raqamingiz
DOWNLOAD_PATH = "downloads/"
USER_DB = "users.json"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

# --- STATISTIKA VA FOYDALANUVCHILARNI BOSHQARISH ---
def get_users():
    if not os.path.exists(USER_DB):
        return []
    try:
        with open(USER_DB, "r") as f:
            return json.load(f)
    except:
        return []

def save_user(user_id):
    users = get_users()
    if user_id not in users:
        users.append(user_id)
        with open(USER_DB, "w") as f:
            json.dump(users, f)

# --- FASTAPI / LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*30)
    print("🚀 FALSEBIRD-BOT ISHGA TUSHDI!")
    print("🌍 Platformalar: YouTube, Instagram, TikTok, Pinterest")
    print("="*30 + "\n")
    
    # Conflict xatosini oldini olish uchun avvalgi sessiyalarni yopish
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- YUKLASH LOGIKASI (Professional Update) ---
def download_media(url, mode="video"):
    file_id = uuid.uuid4().hex
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': f'{DOWNLOAD_PATH}{file_id}.%(ext)s',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        'ignoreerrors': True,
        'cookiefile': None, # Kelajakda cookie qo'shish uchun joy
    }
    
    if mode == "video":
        # Barcha platformalar uchun eng mos formatni tanlash
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None
            filename = ydl.prepare_filename(info)
            return filename, info.get('title', 'Video')
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None
            filename = ydl.prepare_filename(info)
            final_name = os.path.splitext(filename)[0] + ".mp3"
            return final_name, info.get('title', 'Audio')

# --- HANDLERS ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    save_user(message.from_user.id)
    await message.answer("👋 Salom! Menga link yuboring men sizga bir zumda jo'nataman!")

@dp.message(Command("stat"))
async def stat_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        users = get_users()
        await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Jami foydalanuvchilar: **{len(users)}** ta")
    else:
        await message.answer("❌ Bu buyruq faqat bot admini uchun.")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text
    save_user(message.from_user.id)
    status = await message.answer("🔍 Havola tekshirilmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        def fetch_info():
            opts = {'quiet': True, 'nocheckcertificate': True, 'noplaylist': True}
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(thread_pool, fetch_info)
        if not info:
            raise Exception("Ma'lumot topilmadi")

        link_id = uuid.uuid4().hex[:12]
        url_storage[link_id] = url
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎬 Video", callback_data=f"v|{link_id}"),
            InlineKeyboardButton(text="🎵 Audio", callback_data=f"a|{link_id}")
        ]])
        
        title = info.get('title', 'Media')[:50]
        await status.edit_text(f"📌 **Nomi:** {title}...\n\nTanlang:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Xato: {e}")
        await status.edit_text("❌ Xato: Havolani o'qib bo'lmadi. Havola noto'g'ri yoki platforma cheklov qo'ygan.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def process_download(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    if not url:
        await callback.answer("❌ Seans muddati tugagan.", show_alert=True)
        return

    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        file_path, title = await loop.run_in_executor(thread_pool, download_media, url, mode)
        
        if file_path and os.path.exists(file_path):
            # Fayl hajmini tekshirish (Telegram free limit: 50MB)
            if os.path.getsize(file_path) > 50 * 1024 * 1024:
                 await status_msg.edit_text("⚠️ Fayl juda katta (50MB dan ortiq). Uni yuborib bo'lmaydi.")
                 os.remove(file_path)
                 return

            await status_msg.edit_text("📤 Telegramga yuborilmoqda...")
            media = FSInputFile(file_path)
            if mode == "video":
                await callback.message.answer_video(video=media, caption=f"✅ {title}\n\n@falsebird_bot")
            else:
                await callback.message.answer_audio(audio=media, title=title, caption=f"✅ {title}\n\n@falsebird_bot")
            
            await status_msg.delete()
            os.remove(file_path)
        else:
            await status_msg.edit_text("❌ Faylni yuklab bo'lmadi. Platforma himoyasi juda kuchli.")
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")

@app.get("/")
async def root():
    return {"status": "active", "bot": "Falsebird-bot", "users": len(get_users())}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
