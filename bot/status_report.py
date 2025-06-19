import asyncio
from datetime import datetime, timezone
import yagmail
from config import name_mapping  # כאן נמצא המילון: {שם_מקורי: שם_לצגה}

# משתנים גלובליים
status_check_active = False
status_check_responses = {}
status_check_start_time = None

# נא להחליף ל-user_id אמיתיים של המשתמשים
participants_user_ids = {
    "Gaia Luvchik": 5903107616,
    "Ofek Halabi": 7893093742,
    "Sopo": 1314376201,
    "Itay Ben kimon": 56789012,
    "סתיו עיני": 6557978538,
    "Roei Sheffer": 637947209,
    "Ronen Smotrizky": 7482984801,
    "Ofek Barhum": 6514536577
}

expected_names = list(participants_user_ids.keys())

# הפעלת דוח מצב
async def trigger_status_check(context, sender_email, sender_password, receiver_email):
    global status_check_active, status_check_responses, status_check_start_time
    status_check_active = True
    status_check_responses = {}
    status_check_start_time = datetime.now(timezone.utc)

    message = (
        "📋 דוח מצב!\n"
        "אנא אשר את מצבך בתוך 10 הדקות הקרובות:\n"
        "1️⃣ הכול בסדר\n"
        "2️⃣ יש בעיה\n\n"
        "תודה על שיתוף הפעולה 🙏"
    )

    for name, user_id in participants_user_ids.items():
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            print(f"✅ Message sent to {name}")
        except Exception as e:
            print(f"❌ Error sending message to {name}: {e}")

    asyncio.create_task(collect_status_check_results(sender_email, sender_password, receiver_email))

# איסוף תוצאות ושליחת מייל
async def collect_status_check_results(sender_email, sender_password, receiver_email):
    global status_check_active
    await asyncio.sleep(600)  # 10 דקות

    report = []
    for name in expected_names:
        display_name = name_mapping.get(name, name)
        status = status_check_responses.get(name)
        if status:
            report.append({"name": display_name, "status": status})
        else:
            report.append({"name": display_name, "status": "לא ענה"})

    content = "\n".join([f"{r['name']}: {r['status']}" for r in report])

    yag = yagmail.SMTP(sender_email, sender_password)
    yag.send(
        to=receiver_email,
        subject="📊 דוח מצב - סיכום",
        contents=content
    )

    print("✅ Status report sent by email")
    status_check_active = False

# פונקציות עזר
def is_status_check_active():
    return status_check_active

def record_status_response(name, text):
    status_check_responses[name] = "הכול בסדר" if text == '1' else "יש בעיה"
