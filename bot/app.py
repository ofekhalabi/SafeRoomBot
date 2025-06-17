from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing required environment variable: TELEGRAM_BOT_TOKEN")

DATA_FILE = "responses.json"
MISSING_RESPONSES_FILE = "missing_responses.json"
expected_names = ["יוסי כהן", "דנה לוי", "Ofek Halabi", "נועם ישראלי"]

# התחלה
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"היי {user.first_name}, נכנסת לממד? אנא השב 'כן' או 'לא'."
    )

# טיפול בתשובות
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    if text not in ['כן', 'לא']:
        await update.message.reply_text("אנא השב רק 'כן' או 'לא'.")
        return

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    # מחיקה של תשובה קודמת של אותו משתמש (לפי user_id)
    data = [entry for entry in data if entry["user_id"] != user.id]

    # הוספת תשובה חדשה עם זמן UTC מדויק
    data.append({
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "response": text,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    })

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await update.message.reply_text("תודה! התשובה שלך נשמרה 🙏")

# מוניטור רקע
async def monitor_responses():
    while True:
        try:
            if not os.path.exists(DATA_FILE):
                # אם הקובץ לא קיים, נמחק גם את הקובץ missing_responses.json אם קיים ונחכה
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                    print("🧹 נמחק הקובץ missing_responses.json כי responses.json לא קיים")
                await asyncio.sleep(60)
                continue

            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not data:
                # אם קובץ התשובות ריק, נמחק את שני הקבצים ונחכה
                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)
                    print("🧹 נמחק הקובץ responses.json כי הוא ריק")
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                    print("🧹 נמחק הקובץ missing_responses.json כי responses.json ריק")
                await asyncio.sleep(60)
                continue

            now = datetime.now(timezone.utc)
            five_minutes_ago = now - timedelta(minutes=5)
            twenty_minutes_ago = now - timedelta(minutes=20)

            first_timestamp = min(
                datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                for entry in data
            )

            # מחיקה אחרי 20 דקות
            if first_timestamp < twenty_minutes_ago:
                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)
                    print("🧹 נמחק הקובץ responses.json – עברו יותר מ-20 דקות.")
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                    print("🧹 נמחק הקובץ missing_responses.json – עברו יותר מ-20 דקות.")
                await asyncio.sleep(60)
                continue

            # קיבוץ לפי שם - ניקח את הרשומות האחרונות לפי user
            latest_responses = {}
            for entry in data:
                name = entry["name"]
                timestamp = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if name not in latest_responses or timestamp > latest_responses[name]["timestamp"]:
                    latest_responses[name] = {
                        "response": entry["response"],
                        "timestamp": timestamp
                    }

            # בדיקת חסרים
            problematic_users = []
            for name in expected_names:
                if name not in latest_responses:
                    problematic_users.append({"name": name, "status": "לא ענה בכלל"})
                else:
                    answer = latest_responses[name]["response"]
                    time = latest_responses[name]["timestamp"]
                    if answer != "כן":
                        problematic_users.append({"name": name, "status": f"ענה: {answer}"})
                    elif time < five_minutes_ago:
                        problematic_users.append({"name": name, "status": f"ענה כן באיחור ({time.strftime('%H:%M:%S')})"})

            # שמירת פלט לקובץ
            if problematic_users:
                with open(MISSING_RESPONSES_FILE, "w", encoding='utf-8') as f:
                    json.dump(problematic_users, f, ensure_ascii=False, indent=2)
                print(f"🚨 משתמשים שלא ענו 'כן': {problematic_users}")
            else:
                # ריק את הקובץ אם אין בעיות
                open(MISSING_RESPONSES_FILE, "w").close()

        except Exception as e:
            print(f"שגיאה במוניטור: {e}")

        await asyncio.sleep(60)

# הרצת הבוט
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_response))

    async def post_init(app):
        asyncio.create_task(monitor_responses())

    app.post_init = post_init

    print("🤖 for stop the bot press Ctrl+C")
    app.run_polling()

if __name__ == '__main__':
    main()
