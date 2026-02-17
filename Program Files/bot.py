import os
import re
import uuid
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import whisper

# ======================
# CONFIG
# ======================
TOKEN = os.getenv("7854875573:AAE6UvQhrBNpVvl2N_j--6-Vv8qKmOTF_60")
if not TOKEN:
    raise ValueError("Set TELEGRAM_TOKEN environment variable")

whisper_model = None


# ======================
# WHISPER LOADING
# ======================
def get_model():
    global whisper_model
    if whisper_model is None:
        print("Loading Whisper model...")
        whisper_model = whisper.load_model("base")
    return whisper_model


def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except:
        return False


# ======================
# PARAMETER EXTRACTION
# ======================
def extract_expense_details(text: str):
    """
    Extract:
    - amount
    - bank
    - expense name
    """

    text_lower = text.lower()

    # -------- Amount --------
    amount_match = re.search(r"\b\d+(?:\.\d+)?\b", text_lower)
    amount = amount_match.group() if amount_match else None

    # -------- Known banks --------
    banks = [
        "hdfc", "sbi", "icici", "axis",
        "kotak", "idfc", "yes bank",
        "paytm", "phonepe", "gpay"
    ]

    bank = None
    for b in banks:
        if b in text_lower:
            bank = b.upper()
            break

    # -------- Expense name --------
    expense = text_lower

    if amount:
        expense = expense.replace(amount, "")

    if bank:
        expense = expense.replace(bank.lower(), "")

    # Remove filler words
    fillers = ["paid", "for", "using", "from", "spent", "rupees", "rs"]
    for f in fillers:
        expense = expense.replace(f, "")

    expense = expense.strip().title()

    return {
        "amount": amount,
        "expense": expense if expense else None,
        "bank": bank,
    }


# ======================
# TELEGRAM HANDLERS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Text", callback_data="text"),
            InlineKeyboardButton("Voice", callback_data="voice"),
        ]
    ]
    await update.message.reply_text(
        "How do you want to add expense?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "voice":
        if not check_ffmpeg():
            await query.edit_message_text(
                "FFmpeg not installed. Voice won't work."
            )
            return

        context.user_data["mode"] = "voice"
        await query.edit_message_text(
            "Send voice like:\n'Lunch 250 HDFC'"
        )

    elif query.data == "text":
        context.user_data["mode"] = "text"
        await query.edit_message_text(
            "Type like:\nLunch 250 HDFC"
        )


# ======================
# VOICE HANDLER
# ======================
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != "voice":
        await update.message.reply_text("Use /start first.")
        return

    await update.message.reply_text("Processing voice...")

    try:
        file_id = str(uuid.uuid4())
        file_path = f"voice_{file_id}.ogg"

        file = await update.message.voice.get_file()
        await file.download_to_drive(file_path)

        model = get_model()
        result = model.transcribe(file_path)
        text = result["text"].strip()

        os.remove(file_path)

        details = extract_expense_details(text)

        context.user_data["pending"] = details

        await update.message.reply_text(
            f"Recognized:\n"
            f"Text: {text}\n\n"
            f"Expense: {details['expense']}\n"
            f"Amount: {details['amount']}\n"
            f"Bank: {details['bank']}\n\n"
            f"Confirm? (Yes/No)"
        )

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# ======================
# TEXT HANDLER
# ======================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower().strip()

    # Confirmation stage
    if "pending" in context.user_data:
        if user_text in ["yes", "y"]:
            data = context.user_data["pending"]

            await update.message.reply_text(
                f"Saved:\n"
                f"{data['expense']} - ₹{data['amount']} via {data['bank']}"
            )

            context.user_data.clear()
        else:
            await update.message.reply_text("Cancelled")
            context.user_data.clear()
        return

    # Normal text expense entry
    if context.user_data.get("mode") == "text":
        details = extract_expense_details(update.message.text)
        context.user_data["pending"] = details

        await update.message.reply_text(
            f"Expense: {details['expense']}\n"
            f"Amount: {details['amount']}\n"
            f"Bank: {details['bank']}\n\n"
            f"Confirm? (Yes/No)"
        )
    else:
        await update.message.reply_text("Use /start first.")


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()