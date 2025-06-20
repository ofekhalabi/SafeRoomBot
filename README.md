# מערכת מעקב תגובות משתמשים

המערכת מבוססת על תהליך אוטומטי למעקב אחר תשובות משתמשים ושליחה של עדכונים ודוחות. להלן השלבים שכוללים את פעולת המערכת:

## שלב 1: שמירת תשובות
- כאשר משתמש שולח תשובה "כן" או "לא", התשובה נשמרת בקובץ `responses.json`.

## שלב 2: שליחה אוטומטית לאחר 30 דקות
- לאחר 30 דקות, נשלחת לכל המשתמשים הידועים הודעה עם השאלה: "הכול בסדר / יש בעיה?"

## שלב 3: המתנה לתשובות המשך
- לאחר שליחת ההודעה, המערכת מחכה 10 דקות לקבלת תשובות המשך. התשובות נשמרות בקובץ `followup_responses.json`.

## שלב 4: שליחת דוח מלא
- לאחר סיום של 40 דקות (30 דקות + 10 דקות), נשלח מייל עם דוח מלא. הדוח יכלול את כל המשתמשים, יפרט מי ענה "לא", מי לא ענה בכלל, ומי ענה לשאלה "הכול בסדר / יש בעיה".

## שלב 5: מחיקת קבצים
- לאחר שליחת הדוח, הקבצים `responses.json` ו-`followup_responses.json` יימחקו אוטומטית.
