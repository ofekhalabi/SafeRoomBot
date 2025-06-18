from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import yagmail

# --------------------------------------------------
# 🔧 טעינת משתני סביבה
# --------------------------------------------------
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

# --------------------------------------------------
# 📁 קבצי נתונים
# --------------------------------------------------
DATA_FILE = "responses.json"
MISSING_RESPONSES_FILE = "missing_responses.json"
expected_names = [
    "roeisheffer", "gaialu", "Ofek Halabi", "lavinag", "Itay Ben kimon",
    "stav_eini", "Ofek Barhum","ronens2001"
]

# --------------------------------------------------
# 🌐 סטייט גלובלי
# --------------------------------------------------
user_followup_state: dict[int, str] = {}
chat_ids: set[int] = set()
first_answer_time: datetime | None = None
followup_mode: bool = False
followup_answers: dict[int, dict] = {}

# --------------------------------------------------
# 👋 /start
# --------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """אתחול משתמש חדש"""
    user = update.effective_user
    user_followup_state[user.id] = 'initial'
    await update.message.reply_text(
        f"היי {user.first_name}, נכנסת לממד? אנא השב 'כן' או 'לא'."
    )

# --------------------------------------------------
# 📨 שליחת מייל דרכי Yagmail (סיכום מעקב)
# --------------------------------------------------
async def send_followup_summary():
    """שולח במייל את תוצאות המעקב של 1/2 ומאפס סטייט"""
    global followup_answers

    if not followup_answers:
        body = "לא התקבלו תגובות בהודעת המעקב."
    else:
        lines = [
            "תשובות למעקב לאחר 30 דק':",
            *[
                f"- {info['name']}: {'הכול בסדר' if info['answer']=='1' else 'יש בעיה'}"
                for info in followup_answers.values()
            ]
        ]
        body = "\n".join(lines)

    yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
    yag.send(
        to=RECEIVER_EMAIL,
        subject="דו""ח תשובות למעקב לאחר אזעקה",
        contents=body
    )
    print("✅ נשלח מייל עם תוצאות המעקב")

# --------------------------------------------------
# ⏳ מתזמן הודעת מעקב
# --------------------------------------------------
async def schedule_followup(bot):
    """ממתין 30 דק' ואז שולח הודעת מעקב, ממתין עוד 10 דק' לאיסוף תשובות -> מייל"""
    global followup_mode, first_answer_time, followup_answers

    await asyncio.sleep(30 * 60)  # 30 דקות
    followup_mode = True

    message = (
        "⚠️ חלפו 30 דקות מאז האזעקה.\n\n"
        "אנא אשר את מצבך בתוך 10 הדקות הקרובות:\n"
        "1️⃣ הכול בסדר\n"
        "2️⃣ יש בעיה\n\n"
        "תודה על שיתוף הפעולה 🙏"
    )

    # שליחת ההודעה לכל מי שדיבר עם הבוט מתחילת הריצה
    for uid in chat_ids:
        try:
            await bot.send_message(chat_id=uid, text=message)
        except Exception as e:
            print(f"❌ שגיאה בשליחת הודעת מעקב ל־{uid}: {e}")

    # המתנה של 10 דקות לאיסוף תשובות
    await asyncio.sleep(10 * 60)
    await send_followup_summary()

    # איפוס סטייט
    followup_mode = False
    followup_answers = {}
    first_answer_time = None
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)

# --------------------------------------------------
# 🤖 טיפול בכל הודעה רגילה
# --------------------------------------------------
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global first_answer_time, followup_mode

    user = update.effective_user
    text = update.message.text.strip().lower()

    # רישום chat_id
    chat_ids.add(user.id)

    # --------------------------------------------------
    # 🟡 במצב follow-up (מצפים ל-1/2)
    # --------------------------------------------------
    if followup_mode:
        if text in ['1', '2']:
            if user.id not in followup_answers:
                followup_answers[user.id] = {
                    "name": user.full_name,
                    "answer": text,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                }
                await update.message.reply_text("תודה על העדכון 🙏")
            else:
                await update.message.reply_text("העדכון שלך כבר נרשם 🙏")
        else:
            await update.message.reply_text("אנא הקש 1 או 2 בלבד.")
        return

    # --------------------------------------------------
    # 🟢 לוגיקה קיימת – איסוף תשובות 'כן'/'לא'
    # --------------------------------------------------

    # שלב איסוף סיבה לאחר תשובת "לא"
    if user_followup_state.get(user.id) == 'awaiting_reason':
        if text in ['1', '2']:
            reason = "אין לי אזעקה" if text == '1' else "אין לי מרחב מוגן"
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []

            data = [e for e in data if e["user_id"] != user.id]
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
            # בדיקה האם זו התשובה הראשונה
            if first_answer_time is None:
                first_answer_time = datetime.now(timezone.utc)
                asyncio.create_task(schedule_followup(context.bot))
            return
        else:
            await update.message.reply_text("אנא הקש 1 או 2.")
            return

    # קליטה רק של כן/לא
    if text not in ['כן', 'לא']:
        await update.message.reply_text("אנא השב רק 'כן' או 'לא'.")
        return

    # ----- "לא" → בקשת סיבה -----
    if text == 'לא':
        user_followup_state[user.id] = 'awaiting_reason'
        await update.message.reply_text(
            "הזנת שאתה לא בממד..\nמה הסיבה?\n1. אין לי אזעקה\n2. אין לי מרחב מוגן\n\n"
            "הקש את המספר הרלוונטי עבורך?"
        )
        return

    # ----- "כן" -----
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data = [e for e in data if e["user_id"] != user.id]
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

    # בדיקה האם זו התשובה הראשונה – הפעלת הטיימר
    if first_answer_time is None:
        first_answer_time = datetime.now(timezone.utc)
        asyncio.create_task(schedule_followup(context.bot))

# --------------------------------------------------
# 📨 שליחת מייל על משתמשים חסרים (לוגיקה קיימת)
# --------------------------------------------------

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

# --------------------------------------------------
# 🔄 מוניטור קיים – לא שונה
# --------------------------------------------------
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
                datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                for e in data
            )

            latest_responses = {}
            for e in data:
                name = e["name"]
                ts = datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if name not in latest_responses or ts > latest_responses[name]["timestamp"]:
                    latest_responses[name] = {"response": e["response"], "timestamp": ts}

            problematic_users = []
            for name in expected_names:
                if name not in latest_responses:
                    problematic_users.append({"name": name, "status": "לא ענה בכלל"})
                else:
                    user_entries = [e for e in data if e["name"] == name]
                    last_entry = max(
                        user_entries,
                        key=lambda x: datetime.strptime(x["timestamp"], "%Y-%m-%d %H:%M:%S")
                    )
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

# --------------------------------------------------
# 🚀 main – הפעלת הבוט
# --------------------------------------------------

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
