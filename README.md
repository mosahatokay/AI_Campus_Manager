# CampusAI — סוכן מזכירות לניהול חדרים ומבחנים

**קורס:** סוכני AI · **אבן דרך א׳** · **מגישים:** מוסא ונוריאן (נא לוודא שמות מלאים לפני הגשה)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mosahatokay/AI_Campus_Manager/blob/main/CampusAI_agent_demo.ipynb)

**[פתיחת מחברת ההגשה ב־Google Colab](https://colab.research.google.com/github/mosahatokay/AI_Campus_Manager/blob/main/CampusAI_agent_demo.ipynb)**

## מה הפרויקט עושה?

סוכן למזכירה הראשית במכללה: מאתר חדרים לפי קיבולת וציוד, בודק שעות פנויות, מציג מבחנים מתוכננים ומציע יצירה, ביטול או עדכון של הזמנה. פעולות כתיבה דורשות אישור מפורש מטעם יישום מהימן. הכלים אוכפים ימים א׳–ה׳, שעות 08:00–22:00, בדיקת תפוסה וציוד. חיפוש ללא שעות מציג חלונות זמינים.

בתצורת ההגשה, כל החדרים וההזמנות הם **נתונים סינתטיים** ב־`MockBackend`: חמישה בניינים × שלוש קומות × שמונה חדרים = 120 חדרים. אין תלות במודל API בתשלום, בחיבור SQL Server או ב־GPU.

## הרצה ב־Google Colab — חובה בהגשה

1. פתחו את [CampusAI_agent_demo.ipynb](https://colab.research.google.com/github/mosahatokay/AI_Campus_Manager/blob/main/CampusAI_agent_demo.ipynb).
2. בחרו **Runtime → Run all** במחברת חדשה (CPU רגיל מספיק). תאי החובה מורידים את המאגר באמצעות `git clone` ומתקינים את `requirements.txt` עם גרסאות נעולות.
3. בדקו שהפלט מציג את `pytest` (בהרצה מקומית אחרונה: **131 passed**), את דמו לולאת הסוכן, את השוואת ההקשר ואת שני קובצי העקבות. תעדו צילומי מסך של הרצות שבוצעו באמת.
4. התא האופציונלי עם `RUN_FREE_MODEL = False` **כבוי כברירת מחדל**. אין צורך להפעילו בשביל אבן דרך א׳; `ScriptedModel` הוא מודל **מדומה**, לא LLM.

**ההגשה כוללת קישור למאגר ואת מזהה ה־commit הנבחר.** ה־commit להגשה יהיה זה שייבדק לאחר העלאת העדכון הזה והרצת Colab נקייה — לא מזהה ישן.

## הרצה מקומית

מ־root המאגר (Python 3.10+ מומלץ):

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.demo_agent
python -m src.demo_exams
python -m src.context_comparison
python -m src.trace_examples
```

`src.context_comparison` כותב `docs/context_comparison_results.json`. `src.trace_examples` כותב `docs/traces/success.json` ו־`docs/traces/transient_failure.json`.

## כלים, חוזים והרשאות

| כלי | תפקיד | אישור |
|---|---|---|
| `find_rooms` | חיפוש חדרים לפי נתונים וזמינות | לא |
| `get_availability` | חלונות זמן פנויים | לא |
| `list_exams` | רשימת מבחנים לפי תאריך ומסננים | לא |
| `create_reservation` | יצירת הזמנה | כן |
| `cancel_reservation` | ביטול הזמנה | כן |
| `update_reservation` | שינוי הזמנה | כן |

חוזי JSON Schema נמצאים בקובצי `*_contract.json` שבשורש המאגר וכן `tool_contract.json` ו־`availability_contract.json`. `src/tools.py` מאמת את הקלט, מפריד בין שגיאות, מגביל ניסיונות חוזרים בקריאה ואינו מבצע ניסיונות כתיבה חוזרים אחרי תוצאה לא ודאית. `src/agent.py` מגדיר מצב שיחה נפרד לפי מזהה, תיעוד והצעה לפני אישור. במצב Mock החלטות הכלים מוכנות מראש על ידי `ScriptedModel` — לא בדיקה של הבנת שפה טבעית.

## מימוש SQL Server — מקומי בלבד (לא נדרש ב־Colab)

`src/sql_backend.py` מאפשר עבודה מול טבלאות `CampusAI` קיימות באמצעות Windows Authentication. במחשב עם SQL Server ו־ODBC Driver 17/18 יש להתקין `pyodbc` בנפרד ולהגדיר `CAMPUS_SQL_SERVER`. אין סיסמאות בקוד. בדיקות ה־Mock אינן נוגעות במסד הנתונים. בדיקות קריאה וכתיבה בסיסיות בוצעו גם מול SQL Server מקומי, אבל אין תלות בו בשחזור ההגשה.

## תיעוד וראיות

- [תיעוד אבן דרך א׳](docs/milestone1.md) — ארכיטקטורה, מצב, השוואת הקשר, מגבלות, תרומת המגישים.
- [נספח שימוש ב־AI](docs/ai_usage.md) — במה נעזרנו ב־ChatGPT ומה אומת בפועל.
- [השוואת הקשר מלא/מצומצם](docs/context_comparison.md) ו־[תוצאות JSON](docs/context_comparison_results.json).
- [עקבות הצלחה](docs/traces/success.json) ו־[עקבות כשל זמני](docs/traces/transient_failure.json).
- [תיעוד עקבות](docs/traces/README.md).

**הערה אקדמית:** בשלב הזה הוכח בבדיקות תהליך Python מבוקר עם החלטות מדומות. ניסיון נפרד עם Qwen חינמי בחר כלי ראשון אך נכשל בשלב התשובה; הוא לא מוצג כהדגמת שפה חופשית מוצלחת. השמות המלאים וחלק התרומה של נוריאן מחייבים השלמה אמתית לפני ההגשה.
