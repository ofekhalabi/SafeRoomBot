from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import yagmail

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing required environment variable: TELEGRAM_BOT_TOKEN")
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
if not SENDER_EMAIL:
    raise RuntimeError("Missing required environment variable: SENDER_EMAIL")
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
if not SENDER_PASSWORD:
    raise RuntimeError("Missing required environment variable: SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL')
if not RECEIVER_EMAIL:
    raise RuntimeError("Missing required environment variable: RECEIVER_EMAIL")

DATA_FILE = "responses.json"
MISSING_RESPONSES_FILE = "missing_responses.json"
expected_names = ["roeisheffer", "gaialu", "Ofek Halabi", "lavinag", "Itay Ben kimon","stav_eini", "Ofek Barhum"]

user_followup_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_followup_state.pop(user.id, None)
    await update.message.reply_text(f"היי {user.first_name}, נכנסת לממד? אנא השב 'כן' או 'לא'.")

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    if user_followup_state.get(user.id) == 'awaiting_reason':
        if text in ['1', '2']:
            reason = "אין לי אזעקה" if text == '1' else "אין לי מרחב מוגן"
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []

            data = [entry for entry in data if entry["user_id"] != user.id]
            data.append({
                "user_id": user.id,
                "username": user.username,
                "name": user.full_name,
                "response": "לא",
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            })

            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            user_followup_state.pop(user.id)
            await update.message.reply_text(f"תודה שהבהרת: '{reason}'. התשובה שלך נשמרה 🙏")
            return

        elif text == 'כן':
            user_followup_state.pop(user.id, None)
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []

            data = [entry for entry in data if entry["user_id"] != user.id]
            data.append({
                "user_id": user.id,
                "username": user.username,
                "name": user.full_name,
                "response": "כן",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            })

            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            await update.message.reply_text("תודה! התשובה שלך נשמרה 🙏")
            return

        else:
            await update.message.reply_text("אנא הקש 1 או 2, או 'כן' כדי לחזור לתשובה הראשית.")
            return

    if text not in ['כן', 'לא']:
        await update.message.reply_text("אנא השב רק 'כן' או 'לא'.")
        return

    if text == 'לא':
        user_followup_state[user.id] = 'awaiting_reason'
        await update.message.reply_text(
            "הזנת שאתה לא בממד..\nמה הסיבה?\n1. אין לי אזעקה\n2. ⁠אין לי מרחב מוגן\n\n"
            "הקש את המספר הרלוונטי עבורך?"
        )
        return

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data = [entry for entry in data if entry["user_id"] != user.id]
    data.append({
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "response": "כן",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    })

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await update.message.reply_text("תודה! התשובה שלך נשמרה 🙏")

# 📨 שליחת מייל עם תוכן הקובץ
def send_missing_email():
    if not os.path.exists(MISSING_RESPONSES_FILE):
        print("❌ אין קובץ לשלוח.")
        return

    with open(MISSING_RESPONSES_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.strip():
        print("📭 הקובץ ריק – לא נשלח מייל.")
        return

    yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
    yag.send(
        to=RECEIVER_EMAIL,
        subject="משתמשים שלא ענו כן",
        contents=f"הנה תוכן הקובץ missing_responses.json:\n\n{content}"
    )
    print("✅ נשלח מייל עם missing_responses.json")

# 🎯 מוניטור
async def monitor_responses():
    email_sent = False

    while True:
        try:
            if not os.path.exists(DATA_FILE):
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                email_sent = False
                await asyncio.sleep(60)
                continue

            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not data:
                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                email_sent = False
                await asyncio.sleep(60)
                continue

            now = datetime.now(timezone.utc)
            five_minutes_ago = now - timedelta(minutes=5)
            seven_minutes_ago = now - timedelta(minutes=7)

            first_timestamp = min(
                datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                for entry in data
            )

            latest_responses = {}
            for entry in data:
                name = entry["name"]
                timestamp = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if name not in latest_responses or timestamp > latest_responses[name]["timestamp"]:
                    latest_responses[name] = {
                        "response": entry["response"],
                        "timestamp": timestamp
                    }

            problematic_users = []
            for name in expected_names:
                if name not in latest_responses:
                    problematic_users.append({"name": name, "status": "לא ענה בכלל"})
                else:
                    user_entries = [entry for entry in data if entry["name"] == name]
                    last_entry = max(user_entries, key=lambda e: datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S"))
                    answer = last_entry["response"]
                    time = datetime.strptime(last_entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if answer != "כן":
                        reason = last_entry.get("reason")
                        status_text = f"ענה: {answer}"
                        if reason:
                            status_text += f", סיבה: {reason}"
                        problematic_users.append({"name": name, "status": status_text})
                    elif time < five_minutes_ago:
                        problematic_users.append({"name": name, "status": f"ענה כן באיחור ({time.strftime('%H:%M:%S')})"})

            if problematic_users:
                with open(MISSING_RESPONSES_FILE, "w", encoding='utf-8') as f:
                    json.dump(problematic_users, f, ensure_ascii=False, indent=2)
            else:
                open(MISSING_RESPONSES_FILE, "w").close()

            if first_timestamp < seven_minutes_ago:
                if not email_sent:
                    send_missing_email()
                    email_sent = True

                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)
                if os.path.exists(MISSING_RESPONSES_FILE):
                    os.remove(MISSING_RESPONSES_FILE)
                await asyncio.sleep(60)
                continue

        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(60)

# 🚀 הפעלת הבוט
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

