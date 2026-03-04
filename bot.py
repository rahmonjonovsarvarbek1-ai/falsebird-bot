import os
import asyncio
import logging
import uuid
import glob # Faylni topish uchun qo'shildi
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

# --- SOZLAMALAR ---
TOKEN = "8741407408:AAEh6x5uz7p-fsQ0UO0XXFloSnWXAU_aMbg" # .env ga oling!
DOWNLOAD_PATH = "downloads/"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
thread_pool = ThreadPoolExecutor(max_workers=10)
url_storage = {}

def download_media(url, mode="video"):
    file_id = f"{uuid.uuid4().hex}"
    outtmpl = f'{DOWNLOAD_PATH}{file_id}.%(ext)s'
    
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'outtmpl': outtmpl,
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
        
        # Post-processorlardan keyin fayl nomini aniqlash
        # Chunki mp3 bo'lganda kengaytma o'zgaradi
        expected_file = ydl.prepare_filename(info)
        if mode == "audio":
            expected_file = os.path.splitext(expected_file)[0] + ".mp3"
        
        return expected_file, title

# --- HANDLERS ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("🌟 **BlueSave Pro v5.2 Active!**\n\nYouTube, Instagram yoki TikTok linkini yuboring!")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text
    msg = await message.answer("🔍 Tekshirilmoqda...")
    
    try:
        # get_video_info ni alohida chaqirmasdan, download ichida ham qilish mumkin, 
        # lekin oldindan ko'rish uchun quyidagicha qoldiramiz:
        loop = asyncio.get_running_loop()
        ydl_opts = {'quiet': True, 'noplaylist': True}
        
        def fetch_info():
            with YoutubeDL(ydl_opts) as ydl:
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
        
        await msg.delete()
        title = info.get('title', 'Video')[:50] # Sarlavha juda uzun bo'lmasligi uchun
        await message.reply(f"🎬 **Nomi:** {title}\n\nTanlang:", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Info Error: {e}")
        await msg.edit_text("❌ Xatolik: Linkni o'qib bo'lmadi yoki format qo'llab-quvvatlanmaydi.")

@dp.callback_query(F.data.startswith(("v|", "a|")))
async def process_download(callback: types.CallbackQuery):
    prefix, link_id = callback.data.split("|")
    url = url_storage.get(link_id)
    
    if not url:
        await callback.answer("❌ Seans muddati tugagan. Linkni qayta yuboring.", show_alert=True)
        return

    mode = "video" if prefix == "v" else "audio"
    status_msg = await callback.message.edit_text(f"⏳ {mode.capitalize()} tayyorlanmoqda...")
    
    try:
        loop = asyncio.get_running_loop()
        file_path, title = await loop.run_in_executor(thread_pool, download_media, url, mode)
        
        if os.path.exists(file_path):
            await status_msg.edit_text("📤 Telegramga yuklanmoqda...")
            media = FSInputFile(file_path)
            
            if mode == "video":
                await callback.message.answer_video(video=media, caption=f"✅ {title}")
            else:
                await callback.message.answer_audio(audio=media, title=title, caption=f"✅ {title}")
            
            # Tozalash
            if os.path.exists(file_path):
                os.remove(file_path)
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Fayl yuklashda muammo bo'ldi.")
            
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)[:50]}...")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())
