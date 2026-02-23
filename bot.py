import os
import logging
import tempfile
import datetime
import asyncio
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

import speech_recognition as sr
from pydub import AudioSegment
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm

# ===================== SOZLAMALAR =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "BU_YERGA_TOKEN_QOYING")

LANGUAGES = {
    "🇺🇿 O'zbekcha": "uz-UZ",
    "🇷🇺 Ruscha": "ru-RU",
    "🇬🇧 Inglizcha": "en-US",
    "🇹🇷 Turkcha": "tr-TR",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Foydalanuvchi sozlamalari (xotirada saqlanadi)
user_settings = {}


# ===================== YORDAMCHI FUNKSIYALAR =====================

def get_user_lang(user_id):
    return user_settings.get(user_id, {}).get("lang", "uz-UZ")


def get_user_format(user_id):
    return user_settings.get(user_id, {}).get("format", "DOCX")


def convert_to_wav(input_path):
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)
    tmp = tempfile.mktemp(suffix=".wav")
    audio.export(tmp, format="wav")
    return tmp


def recognize_audio(wav_path, language="uz-UZ"):
    recognizer = sr.Recognizer()
    audio_seg = AudioSegment.from_wav(wav_path)
    duration_ms = len(audio_seg)
    chunk_ms = 30000
    texts = []

    for start in range(0, duration_ms, chunk_ms):
        end = min(start + chunk_ms, duration_ms)
        chunk = audio_seg[start:end]
        tmp_chunk = tempfile.mktemp(suffix=".wav")
        chunk.export(tmp_chunk, format="wav")
        try:
            with sr.AudioFile(tmp_chunk) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language=language)
                texts.append(text)
            except sr.UnknownValueError:
                pass
        finally:
            if os.path.exists(tmp_chunk):
                os.remove(tmp_chunk)

    return " ".join(texts) if texts else None


def make_docx(text, audio_name):
    doc = Document()
    doc.add_heading("Audio Transkriptsiya", 0).alignment = 1
    doc.add_paragraph(f"Fayl: {audio_name}")
    doc.add_paragraph(f"Sana: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph("─" * 50)
    doc.add_paragraph()
    doc.add_heading("Matn:", level=1)

    sentences = text.split(". ")
    buf = []
    for s in sentences:
        buf.append(s.strip())
        if len(buf) >= 3:
            doc.add_paragraph(". ".join(buf) + ".")
            buf = []
    if buf:
        doc.add_paragraph(". ".join(buf))

    doc.add_paragraph()
    doc.add_paragraph("─" * 50)
    doc.add_paragraph(f"So'zlar: {len(text.split())} | Belgilar: {len(text)}")

    tmp = tempfile.mktemp(suffix=".docx")
    doc.save(tmp)
    return tmp


def make_pdf(text, audio_name):
    tmp = tempfile.mktemp(suffix=".pdf")
    doc_pdf = SimpleDocTemplate(tmp, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=16, alignment=1, spaceAfter=10)
    meta_style = ParagraphStyle("M", parent=styles["Normal"], fontSize=9, textColor="#888888", spaceAfter=5)
    body_style = ParagraphStyle("B", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=8)

    story = [
        Paragraph("Audio Transkriptsiya", title_style),
        Spacer(1, 0.3*cm),
        Paragraph(f"Fayl: {audio_name}", meta_style),
        Paragraph(f"Sana: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", meta_style),
        Spacer(1, 0.4*cm),
        Paragraph("─" * 60, meta_style),
        Spacer(1, 0.4*cm),
        Paragraph("<b>Matn:</b>", body_style),
        Spacer(1, 0.2*cm),
    ]

    sentences = text.split(". ")
    buf = []
    for s in sentences:
        buf.append(s.strip())
        if len(buf) >= 3:
            story.append(Paragraph(". ".join(buf) + ".", body_style))
            buf = []
    if buf:
        story.append(Paragraph(". ".join(buf), body_style))

    story += [
        Spacer(1, 0.4*cm),
        Paragraph("─" * 60, meta_style),
        Paragraph(f"So'zlar: {len(text.split())} | Belgilar: {len(text)}", meta_style),
    ]
    doc_pdf.build(story)
    return tmp


# ===================== BOT HANDLERLARI =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    user_settings.setdefault(uid, {"lang": "uz-UZ", "format": "DOCX"})

    text = (
        f"👋 Salom, *{name}*!\n\n"
        "🎙️ Men audio xabarlarni matnga aylantirib, *PDF* yoki *DOCX* fayl qilib beraman.\n\n"
        "📌 *Qanday foydalanish:*\n"
        "1️⃣ /til — tilni tanlang\n"
        "2️⃣ /format — chiqish formatini tanlang\n"
        "3️⃣ Audio yuboring (ovozli xabar yoki MP3/OGG fayl)\n\n"
        "⚡ Boshlash uchun audio yuboring!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *Yordam*\n\n"
        "/start — Botni ishga tushirish\n"
        "/til — Audio tilini tanlash\n"
        "/format — PDF yoki DOCX tanlash\n"
        "/sozlamalar — Joriy sozlamalar\n\n"
        "📎 Qo'llab-quvvatlanadigan formatlar:\n"
        "• Telegram ovozli xabar (🎤)\n"
        "• MP3, OGG, WAV, M4A, FLAC fayllar",
        parse_mode="Markdown"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang_name = next((k for k, v in LANGUAGES.items() if v == get_user_lang(uid)), "O'zbekcha")
    fmt = get_user_format(uid)
    await update.message.reply_text(
        f"⚙️ *Joriy sozlamalar:*\n\n"
        f"🌐 Til: {lang_name}\n"
        f"📄 Format: {fmt}",
        parse_mode="Markdown"
    )


async def choose_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(lang, callback_data=f"lang:{code}")]
        for lang, code in LANGUAGES.items()
    ]
    await update.message.reply_text(
        "🌐 Tilni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def choose_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📝 Word (DOCX)", callback_data="fmt:DOCX"),
            InlineKeyboardButton("📄 PDF", callback_data="fmt:PDF"),
        ]
    ]
    await update.message.reply_text(
        "📋 Chiqish formatini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    data = query.data
    user_settings.setdefault(uid, {"lang": "uz-UZ", "format": "DOCX"})

    if data.startswith("lang:"):
        code = data.split(":")[1]
        user_settings[uid]["lang"] = code
        lang_name = next((k for k, v in LANGUAGES.items() if v == code), code)
        await query.edit_message_text(f"✅ Til o'rnatildi: *{lang_name}*", parse_mode="Markdown")

    elif data.startswith("fmt:"):
        fmt = data.split(":")[1]
        user_settings[uid]["format"] = fmt
        await query.edit_message_text(f"✅ Format o'rnatildi: *{fmt}*", parse_mode="Markdown")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_settings.setdefault(uid, {"lang": "uz-UZ", "format": "DOCX"})

    # Audio manbasini aniqlash
    audio_obj = None
    file_name = "audio"

    if update.message.voice:
        audio_obj = update.message.voice
        file_name = "voice_message"
    elif update.message.audio:
        audio_obj = update.message.audio
        file_name = update.message.audio.file_name or "audio"
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith("audio"):
            audio_obj = doc
            file_name = doc.file_name or "audio"
        else:
            await update.message.reply_text("❌ Faqat audio fayl yuboring!")
            return
    else:
        await update.message.reply_text("❌ Audio topilmadi!")
        return

    # Fayl hajmini tekshirish (20MB limit)
    if audio_obj.file_size and audio_obj.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Fayl hajmi 20MB dan oshmasligi kerak!")
        return

    msg = await update.message.reply_text("⏳ Audio qabul qilindi, ishlanmoqda...")

    tmp_input = None
    tmp_wav = None
    tmp_output = None

    try:
        # Faylni yuklab olish
        await msg.edit_text("📥 Fayl yuklanmoqda...")
        tg_file = await audio_obj.get_file()
        ext = os.path.splitext(file_name)[1] or ".ogg"
        tmp_input = tempfile.mktemp(suffix=ext)
        await tg_file.download_to_drive(tmp_input)

        # WAV ga aylantirish
        await msg.edit_text("🔄 Audio tayyorlanmoqda...")
        tmp_wav = convert_to_wav(tmp_input)

        # Matnni ajratish
        lang = get_user_lang(uid)
        await msg.edit_text("🎙️ Matn ajratilmoqda... (biroz kuting)")
        text = await asyncio.get_event_loop().run_in_executor(
            None, recognize_audio, tmp_wav, lang
        )

        if not text:
            await msg.edit_text(
                "❌ Matn ajratib bo'lmadi.\n\n"
                "Sabab bo'lishi mumkin:\n"
                "• Audio sifati past\n"
                "• Noto'g'ri til tanlangan (/til)\n"
                "• Audio da ovoz yo'q"
            )
            return

        # Fayl yaratish
        fmt = get_user_format(uid)
        await msg.edit_text(f"📄 {fmt} fayl tayyorlanmoqda...")

        if fmt == "DOCX":
            tmp_output = await asyncio.get_event_loop().run_in_executor(
                None, make_docx, text, file_name
            )
            out_name = os.path.splitext(file_name)[0] + "_matn.docx"
        else:
            tmp_output = await asyncio.get_event_loop().run_in_executor(
                None, make_pdf, text, file_name
            )
            out_name = os.path.splitext(file_name)[0] + "_matn.pdf"

        # Natijani yuborish
        word_count = len(text.split())
        caption = (
            f"✅ *Tayyor!*\n\n"
            f"🌐 Til: `{lang}`\n"
            f"📊 So'zlar: `{word_count}`\n"
            f"📄 Format: `{fmt}`"
        )

        await msg.delete()

        # Matnni ham yuborish (qisqa bo'lsa)
        if len(text) <= 800:
            await update.message.reply_text(
                f"📝 *Ajratilgan matn:*\n\n{text}",
                parse_mode="Markdown"
            )

        with open(tmp_output, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=out_name,
                caption=caption,
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await msg.edit_text(f"❌ Xatolik yuz berdi:\n`{str(e)}`", parse_mode="Markdown")

    finally:
        for tmp in [tmp_input, tmp_wav, tmp_output]:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙️ Iltimos, audio fayl yoki ovozli xabar yuboring!\n\n"
        "Yordam: /help"
    )


# ===================== MAIN =====================

def main():
    if BOT_TOKEN == "BU_YERGA_TOKEN_QOYING":
        print("❌ BOT_TOKEN o'rnatilmagan!")
        print("   .env faylga yoki environment variable ga qo'shing:")
        print("   BOT_TOKEN=1234567890:ABCdef...")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("til", choose_lang))
    app.add_handler(CommandHandler("format", choose_format))
    app.add_handler(CommandHandler("sozlamalar", settings_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
