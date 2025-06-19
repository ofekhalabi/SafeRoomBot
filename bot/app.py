# קוד מלא עם תיקונים לזיהוי נכון של שמות
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import yagmail
from config import name_mapping  # מילון {שם_מקורי: שם_לצגה}

from status_report import (
    is_status_check_active,
    record_status_response,
    trigger_status_check
)

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL')

DATA_FILE = "responses.json"
MISSING_RESPONSES_FILE = "missing_responses.json"

# שמות מקוריים לצורך השוואה, מומרים לשמות להצגה
expected_raw_names = ["Roei Sheffer", "Gaia Luvchik", "Ofek Halabi", "Sopo", "Itay Ben kimon", "סתיו עיני", "Ofek Barhum", "Ronen Smotrizky"]
expected_names = [name_mapping.get(name, name) for name in expected_raw_names]

user_followup_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_followup_state.pop(update.effective_user.id, None)
    await update.message.reply_text(f"היי {update.effective_user.first_name}, נכנסת לממד? אנא השב 'כן' או 'לא'.")

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    if user.full_name == "Ofek Halabi" and text == "דוח מצב":
        await trigger_status_check(context, SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL)
        return

    if is_status_check_active() and text in ['1', '2']:
        record_status_response(user.full_name, text)
        await update.message.reply_text("✅ תודה על העדכון!")
        return

    if user_followup_state.get(user.id) == 'awaiting_reason':
        if text in ['1', '2']:
            reason = "אין לי אזעקה" if text == '1' else "אין לי מרחב מוגן"
            save_response(user, "לא", reason)
            user_followup_state.pop(user.id)
            await update.message.reply_text(f"תודה שהבהרת: '{reason}'. התשובה שלך נשמרה 🙏")
        elif text == 'כן':
            save_response(user, "כן")
            user_followup_state.pop(user.id)
            await update.message.reply_text("תודה! התשובה שלך נשמרה 🙏")
        else:
            await update.message.reply_text("אנא הקש 1 או 2, או 'כן'.")
        return

    if text not in ['כן', 'לא']:
        await update.message.reply_text("אנא השב רק 'כן' או 'לא'.")
        return

    if text == 'לא':
        user_followup_state[user.id] = 'awaiting_reason'
        await update.message.reply_text(
            "הזנת שאתה לא בממד..\nמה הסיבה?\n1. אין לי אזעקה\n2. ⁠אין לי מרחב מוגן\n\nהקש את המספר הרלוונטי עבורך?"
        )
        return

    save_response(user, "כן")
    await update.message.reply_text("תודה! התשובה שלך נשמרה 🙏")

def save_response(user, response, reason=None):
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data = [entry for entry in data if entry["user_id"] != user.id]
    mapped_name = name_mapping.get(user.full_name, user.full_name)
    entry = {
        "user_id": user.id,
        "username": user.username,
        "name": mapped_name,
        "response": response,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    }
    if reason:
        entry["reason"] = reason
    data.append(entry)

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_missing_email():
    if not os.path.exists(MISSING_RESPONSES_FILE):
        return
    with open(MISSING_RESPONSES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not data:
        return

    lines = [f"{entry['name']}: {entry['status']}" for entry in data]
    content = "\n".join(lines)

    try:
        yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
        yag.send(
            to=RECEIVER_EMAIL,
            subject="משתמשים שלא ענו כן",
            contents=f"הנה דוח מצב:\n\n{content}"
        )
    except Exception as e:
        print(f"❌ Failed to send missing responses email: {e}")

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
                os.remove(DATA_FILE)
                os.remove(MISSING_RESPONSES_FILE)
                email_sent = False
                await asyncio.sleep(60)
                continue

            now = datetime.now(timezone.utc)
            check_time_threshold = now - timedelta(minutes=7)
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
                    problematic_users.append({"name": name, "status": "לא ענה"})
                else:
                    entry = latest_responses[name]
                    if entry["response"] != "כן":
                        status_text = f"ענה: {entry['response']}"
                        reason = next((e.get("reason") for e in data if e["name"] == name and e["response"] != "כן"), None)
                        if reason:
                            status_text += f", סיבה: {reason}"
                        problematic_users.append({"name": name, "status": status_text})

            if problematic_users:
                with open(MISSING_RESPONSES_FILE, "w", encoding='utf-8') as f:
                    json.dump(problematic_users, f, ensure_ascii=False, indent=2)
            else:
                open(MISSING_RESPONSES_FILE, "w").close()

            if first_timestamp < check_time_threshold and not email_sent:
                send_missing_email()
                print("📧 Email sent with missing responses.")
                email_sent = True
                os.remove(DATA_FILE)
                os.remove(MISSING_RESPONSES_FILE)

        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(60)

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
