from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing required environment variable: TELEGRAM_BOT_TOKEN")

# קובץ שבו נשמור את התשובות
DATA_FILE = "responses.json"

# פונקציית התחלה - שומרת את המשתמש ושולחת את השאלה
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"היי {user.first_name}, נכנסת לממד? אנא השב 'כן' או 'לא'.\n\n"
    )

# פונקציה לקליטת תשובות ושמירה לקובץ
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    valid_responses = ['כן', 'לא']

    if text not in valid_responses:
        await update.message.reply_text(
            "🤖 לא הצלחתי להבין אותך...\n"
            "אנא כתוב רק 'כן' או 'לא' כדי שנוכל לשמור את התשובה 🙏"
        )
        return

    # טען קובץ JSON או התחל חדש
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    # הוסף תשובה
    data.append({
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "response": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await update.message.reply_text("✅ תודה! התשובה שלך נשמרה.")

# פונקציית main להרצת הבוט
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_response))

    print("🤖 for stop the bot press Ctrl+C")
    app.run_polling()

if __name__ == '__main__':
    main()
