import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import json
import os
from dotenv import load_dotenv  
from datetime import datetime
import random 
import re
import uuid
from urllib.request import urlopen
from pypdf import PdfReader
from zoneinfo import ZoneInfo

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
        
load_dotenv()

# --- FIX 1: BOT_TOKEN None tekshiruvi ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable o'rnatilmagan! Railway > Variables ga qo'shing.")

ADMINS = [6340253146]
bot = telebot.TeleBot(BOT_TOKEN)
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD")

# Cache bot info to avoid repeated API calls
_bot_me = None
def get_bot_me():
    global _bot_me
    if _bot_me is None:
        _bot_me = bot.get_me()
    return _bot_me

user_languages = {}  # {user_id: language}
chat_mode = {}        # {user_id: True} – chat rejimida ekanligini bildiradi

# --- POSTGRESQL DATABASE (Neon) ---
import psycopg2
from psycopg2.extras import Json
from psycopg2 import pool as pg_pool

# --- FIX 2: Hardcoded URL olib tashlandi - faqat env dan o'qiydi ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL environment variable o'rnatilmagan! Railway > Variables ga qo'shing.")

# --- FIX 4: Connection pool - har safar yangi konneksiya emas ---
_db_pool = None

def get_db_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = pg_pool.SimpleConnectionPool(1, 5, DATABASE_URL)
    return _db_pool

def get_conn():
    try:
        return get_db_pool().getconn()
    except Exception:
        # Pool ishlamasa to'g'ridan-to'g'ri ulan
        return psycopg2.connect(DATABASE_URL)

def release_conn(conn):
    try:
        get_db_pool().putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass

def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS botdata (
                    key TEXT PRIMARY KEY,
                    value JSONB
                )
            """)
            conn.commit()
    except Exception as e:
        print(f"init_db xatosi: {e}")
    finally:
        release_conn(conn)

init_db()

def load_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM botdata WHERE key = 'main'")
            row = cur.fetchone()
            if row:
                return row[0]
            return {"students": [], "arizalar": []}
    except Exception as e:
        print(f"load_db xatosi: {e}")
        return {"students": [], "arizalar": []}
    finally:
        release_conn(conn)

def save_db(data):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO botdata (key, value) VALUES ('main', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (Json(data),))
            conn.commit()
    except Exception as e:
        print(f"save_db xatosi: {e}")
    finally:
        release_conn(conn)


def all_admins():
    db = load_db()
    dynamic = set(db.get("admins", []))
    return list(set(ADMINS) | dynamic)


def add_admin(user_id):
    db = load_db()
    admins = set(db.get("admins", []))
    admins.add(int(user_id))
    db["admins"] = list(admins)
    save_db(db)


def is_admin(user_id):
    return int(user_id) in set(all_admins())

def is_primary_admin(user_id):
    return int(user_id) in set(ADMINS)

# --- AUTO LANGUAGE DETECTION ---
def detect_and_set_language(message):
    user_id = message.from_user.id

    # Determine language from Telegram language_code (best-effort)
    detected = None
    lang_code = getattr(message.from_user, "language_code", None)
    if lang_code:
        code = lang_code.split("-")[0].lower()
        # support additional languages (Arabic, Chinese, Japanese)
        mapping = {
            "uz": "O'zbek",
            "en": "English",
            "ru": "Русский",
            "tr": "Turkish",
            "ko": "한국어",
            "kr": "한국어",
            "ar": "العربية",
            "zh": "中文",
            "ja": "日本語"
        }
        detected = mapping.get(code)

    # Fallback / supplement: detect from message text greetings
    text = (message.text or "").lower()
    if any(g in text for g in ["salom", "assalomu", "aslomu", "salam"]):
        detected = "O'zbek"
    elif any(g in text for g in ["hello", "hi"]):
        detected = "English"
    elif any(g in text for g in ["привет", "здравствуйте"]):
        detected = "Русский"
    elif any(g in text for g in ["merhaba"]):
        detected = "Turkish"
    elif any(g in text for g in ["안녕", "안녕하세요"]):
        detected = "한국어"
    elif any(g in text for g in ["مرحبا", "السلام"]):
        detected = "العربية"
    elif any(g in text for g in ["你好", "您好"]):
        detected = "中文"
    elif any(g in text for g in ["こんにちは", "こんばんは"]):
        detected = "日本語"

    # If nothing detected, default O'zbek
    if not detected:
        detected = user_languages.get(user_id, "O'zbek")

    # If detected language differs from stored one, update and persist
    prev = user_languages.get(user_id)
    if prev != detected:
        user_languages[user_id] = detected
        db = load_db()
        if "user_languages" not in db:
            db["user_languages"] = {}
        db["user_languages"][str(user_id)] = detected
        save_db(db)

    return detected


# --- LOCALIZED STRINGS FOR COMMON PROMPTS ---
localized_texts = {
    "welcome": {
        "O'zbek": "🎓 Saminov School o‘quv markazi\nKerakli bo‘limni tanlang:",
        "English": "🎓 Saminov School\nPlease choose a section:",
        "Русский": "🎓 Saminov School\nПожалуйста, выберите раздел:",
        "Turkish": "🎓 Saminov School\nLütfen bir bölüm seçin:",
        "한국어": "🎓 Saminov School\n섹션을 선택하세요:"
    },
    "courses_title": {
        "O'zbek": "📚 Bizning kurslar — bo'limni tanlang:",
        "English": "📚 Our courses — choose a section:",
        "Русский": "📚 Наши курсы — выберите раздел:",
        "Turkish": "📚 Kurslarımız — bir bölüm seçin:",
        "한국어": "📚 강좌 — 섹션을 선택하세요:",
        "العربية": "📚 دوراتنا — اختر قسمًا:",
        "中文": "📚 我们的课程 — 请选择一个部分:",
        "日本語": "📚 コース一覧 — セクションを選択してください:"
    },
    "trial_text": {
        "O'zbek": "💻 Trial kurs:\nPython dasturlashning kirish darslari bepul.",
        "English": "💻 Trial course:\nIntroductory Python lessons are free.",
        "Русский": "💻 Пробный курс:\nВводные уроки по Python бесплатны.",
        "Turkish": "💻 Deneme kursu:\nPython giriş dersleri ücretsizdir.",
        "한국어": "💻 체험 강좌:\n파이썬 입문 수업은 무료입니다.",
        "العربية": "💻 دورة تجريبية:\nالدروس التمهيدية في بايثون مجانية.",
        "中文": "💻 试用课程：\nPython 入门课程免费。",
        "日本語": "💻 体験コース：\nPython 入門レッスンは無料です。"
    },
    "teachers_prompt": {
        "O'zbek": "👨‍🏫 O‘qituvchini tanlang:",
        "English": "👨‍🏫 Choose a teacher:",
        "Русский": "👨‍🏫 Выберите преподавателя:",
        "Turkish": "👨‍🏫 Bir öğretmen seçin:",
        "한국어": "👨‍🏫 강사를 선택하세요:",
        "العربية": "👨‍🏫 اختر معلمًا:",
        "中文": "👨‍🏫 选择一位教师：",
        "日本語": "👨‍🏫 教師を選択してください："
    },
    "subjects_prompt": {
        "O'zbek": "📂 Fanlar — bo'limni tanlang:",
        "English": "📂 Subjects — choose a section:",
        "Русский": "📂 Предметы — выберите раздел:",
        "Turkish": "📂 Konular — bir bölüm seçin:",
        "한국어": "📂 과목 — 섹션을 선택하세요:",
        "العربية": "📂 المواد — اختر قسمًا:",
        "中文": "📂 科目 — 请选择一个部分：",
        "日本語": "📂 科目 — セクションを選択してください："
    },
    "applications_title": {
        "O'zbek": "📝 Ariza bo‘limi",
        "English": "📝 Applications",
        "Русский": "📝 Заявки",
        "Turkish": "📝 Başvurular",
        "한국어": "📝 신청",
        "العربية": "📝 الطلبات",
        "中文": "📝 申请",
        "日本語": "📝 申し込み"
    },
    "ask_name": {
        "O'zbek": "Ismingizni yozing:",
        "English": "Write your name:",
        "Русский": "Напишите ваше имя:",
        "Turkish": "Adınızı yazın:",
        "한국어": "이름을 작성하세요:",
        "العربية": "اكتب اسمك:",
        "中文": "写下你的名字：",
        "日本語": "お名前を書いてください：" 
    },
    "test_text": {
        "O'zbek": "🧪 Test bo'limi hozircha tayyorlanmoqda.",
        "English": "🧪 Test section is under preparation.",
        "Русский": "🧪 Раздел тестов находится в разработке.",
        "Turkish": "🧪 Test bölümü hazırlanıyor.",
        "한국어": "🧪 테스트 섹션이 준비 중입니다.",
        "العربية": "🧪 قسم الاختبار قيد التحضير.",
        "中文": "🧪 测试部分正在准备中。",
        "日本語": "🧪 テストセクションは準備中です。"
    },
    "quiz_which": {
        "O'zbek": "📝 Qaysi fanning quizini ishlaysiz?",
        "English": "📝 Which subject's quiz do you want to take?",
        "Русский": "📝 Какая тема викторины?",
        "Turkish": "📝 Hangi konunun quizini yapmak istiyorsunuz?",
        "한국어": "📝 어떤 과목의 퀴즈를 진행하시겠습니까?",
        "العربية": "📝 أي اختبار مادة تريد أن تأخذ؟",
        "中文": "📝 您想参加哪个科目的测验？",
        "日本語": "📝 どの科目のクイズを受けたいですか？"
    },
    "chat_prompt": {
        "O'zbek": "💬 Suhbat rejimi. Istalgan savolingizni yozing! (Chiqish uchun /exit yoki tugmani bosing)",
        "English": "💬 Chat mode. Ask me anything! (Use /exit or button to leave)",
        "Русский": "💬 Режим чата. Задайте любой вопрос! (Для выхода используйте /exit или кнопку)"
    },
    "quiz_started": {
        "O'zbek": "✅ {name} boshlandi. Savollarga javob bering!",
        "English": "✅ {name} started. Answer the questions!",
        "Русский": "✅ {name} начался. Отвечайте на вопросы!",
        "Turkish": "✅ {name} başladı. Soruları cevaplayın!",
        "한국어": "✅ {name} 시작되었습니다. 질문에 답하세요!",
        "العربية": "✅ {name} بدأ. أجب على الأسئلة!",
        "中文": "✅ {name} 开始了。请回答问题！",
        "日本語": "✅ {name} が開始されました。質問に答えてください！"
    }
}

# --- O‘QITUVCHILAR ---
teachers = {
    # KIMYO FANI
    "kimyo_saminov": {
        "name": "Saminov Husnidin",
        "subject": "Kimyo",
        "experience": "5 yil",
        "students": "400+",
        "price": "450.000 so'm/oy",
        "bio": "Kimyo fanining murakkab mavzularini sodda tilda tushuntira oladigan tajribali o'qituvchi. Laboratoriya ishlariga alohida e'tibor beradi.",
               "education": "O'zMU, Kimyo fakulteti (2019)",
        "achievements": "2023-yil 'Eng yaxshi kimyo o'qituvchisi' sovrindori",
        "info": """
👨‍🏫 <b>O'QITUVCHI: SAMINOV HUSNIDIN</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧪 <b>Fan:</b> Kimyo
⏳ <b>Tajriba:</b> 5 yil
👥 <b>O'quvchilar soni:</b> 400+
💰 <b>To'lov:</b> 450.000 so'm/oy
🎓 <b>Ma'lumoti:</b> O'zMU, Kimyo fakulteti (2019)

📝 <b>BIOGRAFIYA:</b>
Kimyo fanining murakkab mavzularini sodda tilda tushuntira oladigan tajribali o'qituvchi. Laboratoriya ishlariga alohida e'tibor beradi. Darslarida ko'rgazmali qurollar va video materiallardan foydalanadi.

🏆 <b>YUTUQLARI:</b>
• 2023-yil 'Eng yaxshi kimyo o'qituvchisi' sovrindori
• 3 ta ilmiy maqola muallifi
• 50+ o'quvchisi tibbiyot institutlariga qabul qilingan

📞 <b>Bog'lanish:</b>


⭐️ <b>O'QUVCHILAR FIKRI:</b>
"Kimyo endi qo'rqinchli emas! Saminov ustoz tufayli fan sevimli fanga aylandi" - Ziyoda
"""
    },
    "kimyo_isajonov": {
        "name": "Isajonov Bekzod",
        "subject": "Kimyo",
        "experience": "3 yil",
        "students": "250+",
        "price": "400.000 so'm/oy",
        "bio": "Yosh va kreativ yondashuvga ega kimyo o'qituvchisi. Darslarida zamonaviy pedagogik texnologiyalarni qo'llaydi.",
        "phone": "+998902345678",
               "education": "Toshkent Kimyo Texnologiya Instituti",
        "info": """
👨‍🏫 <b>O'QITUVCHI: ISAJONOV BEKZOD</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧪 <b>Fan:</b> Kimyo
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 250+
💰 <b>To'lov:</b> 400.000 so'm/oy
🎓 <b>Ma'lumoti:</b> Toshkent Kimyo Texnologiya Instituti

📝 <b>BIOGRAFIYA:</b>
Yosh va kreativ yondashuvga ega kimyo o'qituvchisi. Darslarida zamonaviy pedagogik texnologiyalarni qo'llaydi. Kimyoni hayot bilan bog'lab tushuntirish ustasi.

📞 <b>Bog'lanish:</b>


⭐️ <b>O'QUVCHILAR FIKRI:</b>
"Bekzod aka darslari juda qiziq, vaqt qanday o'tganini bilmay qolaman" - Jasur
"""
    },
    "kimyo_abduvohid": {
        "name": "Abduvohid",
        "subject": "Kimyo",
        "experience": "2 yil",
        "students": "150+",
        "price": "350.000 so'm/oy",
        "bio": "Kimyoni sevib o'rganadigan va o'rgatadigan o'qituvchi. Individual yondashuv asosida ishlaydi.",
      
        "info": """
👨‍🏫 <b>O'QITUVCHI: ABDUVOHID</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧪 <b>Fan:</b> Kimyo
⏳ <b>Tajriba:</b> 2 yil
👥 <b>O'quvchilar soni:</b> 150+
💰 <b>To'lov:</b> 350.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Kimyoni sevib o'rganadigan va o'rgatadigan o'qituvchi. Individual yondashuv asosida ishlaydi. Har bir o'quvchining o'zlashtirish darajasiga qarab dars o'tadi.

📞 <b>Bog'lanish:</b>

"""
    },
    
    # RUS TILI
    "rus_jo_rayev": {
        "name": "Jo'rayev Bekzod",
        "subject": "Rus tili",
        "experience": "4 yil",
        "students": "300+",
        "price": "400.000 so'm/oy",
        "bio": "Rus tilini 0 dan boshlab, mukammal darajagacha o'rgatadi. Suhbatlashish amaliyotiga alohida e'tibor beradi.",
    
        "info": """
👨‍🏫 <b>O'QITUVCHI: JO'RAYEV BEKZOD</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇷🇺 <b>Fan:</b> Rus tili
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 300+
💰 <b>To'lov:</b> 400.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Rus tilini 0 dan boshlab, mukammal darajagacha o'rgatadi. Suhbatlashish amaliyotiga alohida e'tibor beradi. Darslarda audio va video materiallardan foydalanadi.

🏆 <b>YUTUQLARI:</b>
• 100+ o'quvchisi rus tilida erkin suhbatlasha oladi
• 50+ o'quvchisi Rossiyada ta'lim olmoqda

📞 <b>Bog'lanish:</b>
• Telegram: @jorayev_rus
"""
    },
    "rus_azimov": {
        "name": "Azimov Azizbek",
        "subject": "Rus tili",
        "experience": "3 yil",
        "students": "200+",
        "price": "350.000 so'm/oy",
        "bio": "Rus tilini oson va tushunarli usulda o'rgatadi. Grammatikani hayotiy misollar bilan tushuntiradi.",
      
        "info": """
👨‍🏫 <b>O'QITUVCHI: AZIMOV AZIZBEK</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇷🇺 <b>Fan:</b> Rus tili
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 200+
💰 <b>To'lov:</b> 350.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Rus tilini oson va tushunarli usulda o'rgatadi. Grammatikani hayotiy misollar bilan tushuntiradi. Darslar interaktiv va qiziqarli o'tadi.

📞 <b>Bog'lanish:</b>
• Telegram: @azimov_rus
"""
    },
    
    # INGLIZ TILI
    "ingliz_roziqov": {
        "name": "Roziqov Dilshodbek",
        "subject": "Ingliz tili",
        "experience": "5 yil",
        "students": "500+",
        "price": "500.000 so'm/oy",
        "bio": "IELTS 7.5 sertifikatiga ega, ingliz tilini zamonaviy metodika asosida o'rgatadi. Suhbatlashish klubi tashkilotchisi.",
     
        "certificates": "IELTS 7.5, TEFL",
        "info": """
👨‍🏫 <b>O'QITUVCHI: ROZIQOV DILSHODBEK</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇬🇧 <b>Fan:</b> Ingliz tili
⏳ <b>Tajriba:</b> 5 yil
👥 <b>O'quvchilar soni:</b> 500+
💰 <b>To'lov:</b> 500.000 so'm/oy
📜 <b>Sertifikatlari:</b> IELTS 7.5, TEFL

📝 <b>BIOGRAFIYA:</b>
IELTS 7.5 sertifikatiga ega, ingliz tilini zamonaviy metodika asosida o'rgatadi. Suhbatlashish klubi tashkilotchisi. Darslarida faqat ingliz tilida so'zlashadi.

🏆 <b>YUTUQLARI:</b>
• 100+ o'quvchisi IELTS 6.5+ olgan
• 50+ o'quvchisi chet elda ta'lim olmoqda

📞 <b>Bog'lanish:</b>
• Telegram: @roziqov_english
"""
    },
    "ingliz_rejavaliyev": {
        "name": "Rejavaliyev Nodirbek",
        "subject": "Ingliz tili",
        "experience": "4 yil",
        "students": "350+",
        "price": "450.000 so'm/oy",
        "bio": "Ingliz tilini o'rgatishda kommunikativ metodikani qo'llaydi. Darslari do'stona va samimiy muhitda o'tadi.",
      
        "info": """
👨‍🏫 <b>O'QITUVCHI: REJAVALIYEV NODIRBEK</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇬🇧 <b>Fan:</b> Ingliz tili
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 350+
💰 <b>To'lov:</b> 450.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Ingliz tilini o'rgatishda kommunikativ metodikani qo'llaydi. Darslari do'stona va samimiy muhitda o'tadi. Har bir o'quvchi bilan individual shug'ullanadi.

📞 <b>Bog'lanish:</b>

"""
    },
    "ingliz_rahmatov": {
        "name": "Rahmatov Bekzod",
        "subject": "Ingliz tili",
        "experience": "3 yil",
        "students": "250+",
        "price": "400.000 so'm/oy",
        "bio": "Yosh va energiyaga to'la o'qituvchi. Ingliz tilini o'yinlar va qiziqarli topshiriqlar orqali o'rgatadi.",
        "phone": "+998908901234",
      
        "info": """
👨‍🏫 <b>O'QITUVCHI: RAHMATOV BEKZOD</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇬🇧 <b>Fan:</b> Ingliz tili
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 250+
💰 <b>To'lov:</b> 400.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Yosh va energiyaga to'la o'qituvchi. Ingliz tilini o'yinlar va qiziqarli topshiriqlar orqali o'rgatadi. Darslari hech qachon zerikarli o'tmaydi.

📞 <b>Bog'lanish:</b>

"""
    },
    "ingliz_abdusatarov": {
        "name": "Abdusatarov Dilmuhammad",
        "subject": "Ingliz tili",
        "experience": "4 yil",
        "students": "300+",
        "price": "450.000 so'm/oy",
        "bio": "Akademik ingliz tili va IELTS yo'nalishida ixtisoslashgan o'qituvchi. Ko'plab o'quvchilari yuqori ballarni qo'lga kiritgan.",
       
        "info": """
👨‍🏫 <b>O'QITUVCHI: ABDUSATAROV DILMUHAMMAD</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇬🇧 <b>Fan:</b> Ingliz tili
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 300+
💰 <b>To'lov:</b> 450.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Akademik ingliz tili va IELTS yo'nalishida ixtisoslashgan o'qituvchi. Ko'plab o'quvchilari yuqori ballarni qo'lga kiritgan. Har bir o'quvchi uchun individual strategiya ishlab chiqadi.

📞 <b>Bog'lanish:</b>

"""
    },
    "ingliz_jamolova": {
        "name": "Jamolova Hilola",
        "subject": "Ingliz tili",
        "experience": "3 yil",
        "students": "200+",
        "price": "400.000 so'm/oy",
        "bio": "Bolalar va o'smirlar bilan ishlash bo'yicha mutaxassis. Ingliz tilini sevib o'rganishga yordam beradi.",

        "info": """
👩‍🏫 <b>O'QITUVCHI: JAMOLOVA HILOLA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇬🇧 <b>Fan:</b> Ingliz tili
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 200+
💰 <b>To'lov:</b> 400.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Bolalar va o'smirlar bilan ishlash bo'yicha mutaxassis. Ingliz tilini sevib o'rganishga yordam beradi. Darslarida ko'plab interaktiv metodlardan foydalanadi.

📞 <b>Bog'lanish:</b>

"""
    },
    
    # BIOLOGIYA
    "bio_nazirov_husan": {
        "name": "Nazirov Husanxon",
        "subject": "Biologiya",
        "experience": "6 yil",
        "students": "600+",
        "price": "500.000 so'm/oy",
        "bio": "Biologiya fanini chuqur biladigan va o'quvchilarni tibbiyotga tayyorlaydigan tajribali o'qituvchi.",
       
        "info": """
👨‍🏫 <b>O'QITUVCHI: NAZIROV HUSANXON</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧬 <b>Fan:</b> Biologiya
⏳ <b>Tajriba:</b> 6 yil
👥 <b>O'quvchilar soni:</b> 600+
💰 <b>To'lov:</b> 500.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Biologiya fanini chuqur biladigan va o'quvchilarni tibbiyotga tayyorlaydigan tajribali o'qituvchi. DTM va milliy sertifikat imtihonlariga tayyorlash bo'yicha mutaxassis.

🏆 <b>YUTUQLARI:</b>
• 200+ o'quvchisi tibbiyot institutlariga qabul qilingan
• 50+ o'quvchisi milliy sertifikat sohibi

📞 <b>Bog'lanish:</b>

"""
    },
    "bio_nazirov_hasan": {
        "name": "Nazirov Hasanxon",
        "subject": "Biologiya",
        "experience": "5 yil",
        "students": "450+",
        "price": "450.000 so'm/oy",
        "bio": "Biologiyani mantiqiy tahlil qilish asosida o'rgatadi. Murakkab mavzularni sodda tushuntiradi.",
        
        "info": """
👨‍🏫 <b>O'QITUVCHI: NAZIROV HASANXON</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧬 <b>Fan:</b> Biologiya
⏳ <b>Tajriba:</b> 5 yil
👥 <b>O'quvchilar soni:</b> 450+
💰 <b>To'lov:</b> 450.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Biologiyani mantiqiy tahlil qilish asosida o'rgatadi. Murakkab mavzularни sodda tushuntiradi. Darslarida ko'plab diagramma va jadvallardan foydalanadi.

📞 <b>Bog'lanish:</b>

"""
    },
    "bio_mamurov": {
        "name": "Mamurov Ortiqali",
        "subject": "Biologiya",
        "experience": "4 yil",
        "students": "300+",
        "price": "400.000 so'm/oy",
        "bio": "Biologiya fanini hayot bilan bog'lab o'rgatadi. Amaliy mashg'ulotlarga alohida e'tibor beradi.",
       
        "info": """
👨‍🏫 <b>O'QITUVCHI: MAMUROV ORTIQALI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧬 <b>Fan:</b> Biologiya
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 300+
💰 <b>To'lov:</b> 400.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Biologiya fanini hayot bilan bog'lab o'rgatadi. Amaliy mashg'ulotlarga alohida e'tibor beradi. O'quvchilari fan olimpiadalarida faxrli o'rinlarni egallagan.

📞 <b>Bog'lanish:</b>

"""
    },
    "bio_jumanazar": {
        "name": "Jumanazar Domla",
        "subject": "Biologiya",
        "experience": "3 yil",
        "students": "200+",
        "price": "350.000 so'm/oy",
        "bio": "Yosh va bilimli biologiya o'qituvchisi. Darslari qiziqarli va mazmunli o'tadi.",
      
        "info": """
👨‍🏫 <b>O'QITUVCHI: JUMANAZAR DOMLA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧬 <b>Fan:</b> Biologiya
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 200+
💰 <b>To'lov:</b> 350.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Yosh va bilimli biologiya o'qituvchisi. Darslari qiziqarli va mazmunli o'tadi. Zamonaviy pedagogik texnologiyalarni qo'llaydi.


"""
    },
    
    # NEMIS TILI
    "nemis_qobulov": {
        "name": "Qobulov Abdurahim",
        "subject": "Nemis tili",
        "experience": "4 yil",
        "students": "150+",
        "price": "400.000 so'm/oy",
        "bio": "Nemis tilini 0 dan boshlab, Goethe-Zertifikat darajasigacha tayyorlaydi. Germaniyada ta'lim olish istagidagilar uchun.",
        
        "certificates": "Goethe-Zertifikat C1",
        "info": """
👨‍🏫 <b>O'QITUVCHI: QOBULOV ABDURAHIM</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🇩🇪 <b>Fan:</b> Nemis tili
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 150+
💰 <b>To'lov:</b> 400.000 so'm/oy
📜 <b>Sertifikati:</b> Goethe-Zertifikat C1

📝 <b>BIOGRAFIYA:</b>
Nemis tilini 0 dan boshlab, Goethe-Zertifikat darajasigacha tayyorlaydi. Germaniyada ta'lim olish istagidagilar uchun ideal o'qituvchi.


"""
    },
    
    # KOMPYUTER VA IT
    "it_valiyev": {
        "name": "Valiyev Omadbek",
        "subject": "Kompyuter va IT",
        "experience": "4 yil",
        "students": "300+",
        "price": "550.000 so'm/oy",
        "bio": "Python, Telegram Bot, Web dasturlash bo'yicha mutaxassis. 100+ loyiha muallifi. Darslari amaliyotga asoslangan.",
        "phone": "+998907877157",
        "telegram": "@Teacher_texno",
        "achievements": "100+ loyiha muallifi",
        "info": """
👨‍🏫 <b>O'QITUVCHI: VALIYEV OMADBEK</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💻 <b>Fan:</b> Kompyuter va IT (Python, Telegram Bot, Web)
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 300+
💰 <b>To'lov:</b> 550.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Python, Telegram Bot, Web dasturlash bo'yicha mutaxassis. 100+ loyiha muallifi. Darslari amaliyotga asoslangan. Har bir darsda real loyiha yozish.

🏆 <b>YUTUQLARI:</b>
• 100+ loyiha muallifi
• 50+ o'quvchisi IT sohasida ish bilan ta'minlangan
• 3 ta Telegram boti 10k+ foydalanuvchiga ega

📞 <b>Bog'lanish:</b>
• Telegram: @Teacher_texno
"""
    },
    
    # ONA TILI
    "ona_jamalov": {
        "name": "Jamalov Qosimxon",
        "subject": "Ona tili",
        "experience": "7 yil",
        "students": "700+",
        "price": "450.000 so'm/oy",
        "bio": "Ona tili va adabiyoti fanining ustoz o'qituvchisi. DTM va milliy sertifikat imtihonlariga tayyorlash bo'yicha katta tajriba.",
  
        "info": """
👨‍🏫 <b>O'QITUVCHI: JAMALOV QOSIMXON</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Fan:</b> Ona tili
⏳ <b>Tajriba:</b> 7 yil
👥 <b>O'quvchilar soni:</b> 700+
💰 <b>To'lov:</b> 450.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Ona tili va adabiyoti fanining ustoz o'qituvchisi. DTM va milliy sertifikat imtihonlariga tayyorlash bo'yicha katta tajriba. O'quvchilari eng yuqori ballarni qo'lga kiritgan.

🏆 <b>YUTUQLARI:</b>
• 300+ o'quvchisi DTMda 150+ ball to'plagan
• 100+ o'quvchisi milliy sertifikat sohibi


"""
    },
    
    # ARAB TILI
    "arab_farmonova": {
        "name": "Farmonova Gulbahor",
        "subject": "Arab tili",
        "experience": "5 yil",
        "students": "200+",
        "price": "450.000 so'm/oy",
        "bio": "Arab tilini o'rgatish bo'yicha mutaxassis. Qur'on tilini o'rganish va arab tilida suhbatlashish amaliyoti.",
       
        "info": """
👩‍🏫 <b>O'QITUVCHI: FARMONOVA GULBAHOR</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🕌 <b>Fan:</b> Arab tili
⏳ <b>Tajriba:</b> 5 yil
👥 <b>O'quvchilar soni:</b> 200+
💰 <b>To'lov:</b> 450.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Arab tilini o'rgatish bo'yicha mutaxassis. Qur'on tilini o'rganish va arab tilida suhbatlashish amaliyoti. Darslarida zamonaviy metodikalarni qo'llaydi.


"""
    },
    
    # TARIX
    "tarix_mahmudova": {
        "name": "Mahmudova Gulhayo",
        "subject": "Tarix",
        "experience": "4 yil",
        "students": "250+",
        "price": "400.000 so'm/oy",
        "bio": "Tarix fanini qiziqarli hikoyalar va faktlar asosida o'rgatadi. Xronologik ketma-ketlikka alohida e'tibor beradi.",
        "phone": "+998910111213",
        "telegram": "@mahmudova_tarix",
        "info": """
👩‍🏫 <b>O'QITUVCHI: MAHMUDOVA GULHAYO</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📜 <b>Fan:</b> Tarix
⏳ <b>Tajriba:</b> 4 yil
👥 <b>O'quvchilar soni:</b> 250+
💰 <b>To'lov:</b> 400.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Tarix fanini qiziqarli hikoyalar va faktlar asosida o'rgatadi. Xronologik ketma-ketlikka alohida e'tibor beradi. Darslari hech qachon zerikarli o'tmaydi.

"""
    },
    "tarix_botirova": {
        "name": "Botirova Gulyora",
        "subject": "Tarix",
        "experience": "3 yil",
        "students": "200+",
        "price": "350.000 so'm/oy",
        "bio": "Jahon va O'zbekiston tarixi bo'yicha mutaxassis. Darslarida xarita va diagrammalardan foydalanadi.",
      
        "info": """
👩‍🏫 <b>O'QITUVCHI: BOTIROVA GULYORA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📜 <b>Fan:</b> Tarix
⏳ <b>Tajriba:</b> 3 yil
👥 <b>O'quvchilar soni:</b> 200+
💰 <b>To'lov:</b> 350.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Jahon va O'zbekiston tarixi bo'yicha mutaxassis. Darslarida xarita va diagrammalardan foydalanadi. Tarixiy voqealarni sabab-natija bog'liqligida tushuntiradi.


"""
    },
    "tarix_soliyeva": {
        "name": "Soliyeva Marjona",
        "subject": "Tarix",
        "experience": "2 yil",
        "students": "150+",
        "price": "300.000 so'm/oy",
        "bio": "Yosh va g'ayratli tarix o'qituvchisi. Darslari interaktiv va zamonaviy usulda o'tadi.",
             "info": """
👩‍🏫 <b>O'QITUVCHI: SOLIYEVA MARJONA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📜 <b>Fan:</b> Tarix
⏳ <b>Tajriba:</b> 2 yil
👥 <b>O'quvchilar soni:</b> 150+
💰 <b>To'lov:</b> 300.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Yosh va g'ayratli tarix o'qituvchisi. Darslari interaktiv va zamonaviy usulda o'tadi. Tarixni sevib o'rganishga yordam beradi.


"""
    },
    
    # MATEMATIKA
    "math_saidafzalxon": {
        "name": "Muhamadxonov Saidafzalxon",
        "subject": "Matematika",
        "experience": "8 yil",
        "students": "1000+",
        "price": "600.000 so'm/oy",
        "bio": "Matematika fanining ustoz o'qituvchisi. DTM, milliy sertifikat va xalqaro imtihonlarga tayyorlash bo'yicha eng katta tajriba.",
               "achievements": "1000+ o'quvchi, 200+ olimpiada g'oliblari",
        "info": """
👨‍🏫 <b>O'QITUVCHI: SAIDAFZALXON</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

➗ <b>Fan:</b> Matematika
⏳ <b>Tajriba:</b> 8 yil
👥 <b>O'quvchilar soni:</b> 1000+
💰 <b>To'lov:</b> 600.000 so'm/oy

📝 <b>BIOGRAFIYA:</b>
Matematika fanining ustoz o'qituvchisi. DTM, milliy sertifikat va xalqaro imtihonlarga tayyorlash bo'yicha eng katta tajriba. Murakkab masalalarni oson usulda yechish sirlarini o'rgatadi.

🏆 <b>YUTUQLARI:</b>
• 1000+ o'quvchi
• 200+ olimpiada g'oliblari
• 500+ o'quvchisi DTMda 170+ ball to'plagan
• 300+ o'quvchisi milliy sertifikat sohibi


"""
    }
}

# === O'QITUVCHILARNI FANLAR BO'YICHA GURUHLASH ===
def get_teachers_by_subject(subject):
    """Fan bo'yicha o'qituvchilarni qaytaradi"""
    result = []
    subject_lower = subject.lower()
    
    for key, teacher in teachers.items():
        if subject_lower in teacher['subject'].lower():
            result.append(teacher)
    
    return result

# === O'QITUVCHI QIDIRISH FUNKSIYASI ===
def search_teachers(query):
    """O'qituvchilarni qidirish (ism, fan, bio bo'yicha)"""
    query = query.lower().strip()
    results = []
    
    for key, teacher in teachers.items():
        score = 0
        
        # Ism bo'yicha qidirish
        if query in teacher['name'].lower():
            score += 10
        
        # Fan bo'yicha qidirish
        if query in teacher['subject'].lower():
            score += 8
        
        # Bio bo'yicha qidirish
        if 'bio' in teacher and query in teacher['bio'].lower():
            score += 5
        
        # Tajriba bo'yicha qidirish (agar son bo'lsa)
        if query.isdigit() and query in teacher['experience']:
            score += 6
        
        if score > 0:
            results.append((score, teacher))
    
    # Yuqori score bo'yicha tartiblash
    results.sort(reverse=True, key=lambda x: x[0])
    return [teacher for score, teacher in results]

# === FANLAR RO'YXATI ===
subjects_list = list(set([teacher['subject'] for teacher in teachers.values()]))

# --- FANLAR ---
subjects = {
    "python": "💻 Python dasturlash (0 dan professional darajagacha)",
    "web": "🌐 Web dasturlash (HTML, CSS, JS, React)",
    "computer": "🖥 Kompyuter savodxonligi (0 dan o‘rgatish)",
    "Ingliz_tili": "🇬🇧 Ingliz tili (0 dan o‘rgatish)",
    "Rus_tili": "🇷🇺 Rus tili (0 dan o‘rgatish)",
    "Matematika": "➗ Matematika (maktab va oliy matematika)",
    "Koreys_tili": "🇰🇷 Koreys tili (0 dan o‘rgatish va professional)",
    "Biologiya": "🧬 Biologiya (maktab va oliy biologiya)",
    "Kimyo": "⚗️ Kimyo (maktab va oliy kimyo)",
    "Tarix": "📜 Tarix (maktab va oliy tarix)",
}

subject_keywords = {
    "python": ["python", "py"],
    "web": ["web", "frontend", "react", "html", "css", "javascript", "js"],
    "computer": ["kompyuter", "kompyuter savodxonligi"],
    "Ingliz_tili": ["ingliz", "english"],
    "Rus_tili": ["rus", "russian"],
    "Matematika": ["matematika", "math"],
    "Koreys_tili": ["koreys", "korean"],
    "Biologiya": ["biologiya", "biology"],
    "Kimyo": ["kimyo", "chemistry"],
    "Tarix": ["tarix", "history"],
    # Geografiya/Fizika/Android olib tashlandi
}

def get_course_price(key):
    prog = {"python", "web"}
    return 400000 if key in prog else 300000

def find_subject_key(text):
    t = (text or "").lower()
    for k, kws in subject_keywords.items():
        for w in kws:
            if w in t:
                return k
    return None

# --- QUIZ DATA ---
quiz_data = {
    "python": {
        "name": "💻 Python Quiz",
        "questions": [
            {
                "q": "Python nimaning asosida o'rgatiladi?",
                "options": ["Dasturlash", "Matematika", "Tarix", "San'at"],
                "correct": 0
            },
            {
                "q": "Python o'zgaruvchini e'lon qilish uchun nima kerak?",
                "options": ["var", "def", "Hech nima", "int"],
                "correct": 2
            },
            {
                "q": "Python-da string yaratish uchun nimani ishlatasiz?",
                "options": ["[ ]", "( )", "{ }", "Qo'shtirnoqlar"],
                "correct": 3
            }
        ]
    },
    "web": {
        "name": "🌐 Web Quiz",
        "questions": [
            {
                "q": "HTML nimaning uchun ishlatiladi?",
                "options": ["Sahifa strukturasi", "Stillar", "Logika", "Ma'lumot omborida"],
                "correct": 0
            },
            {
                "q": "CSS nimani boshqaradi?",
                "options": ["Strukturani", "Uslublarni", "Logikani", "Ma'lumotlarni"],
                "correct": 1
            },
            {
                "q": "JavaScript qayerda ishlatiladi?",
                "options": ["Frontend", "Backend", "Database", "Server"],
                "correct": 0
            }
        ]
    },
    "Ingliz_tili": {
        "name": "🇬🇧 Ingliz tili Quiz",
        "questions": [
            {
                "q": "Ingliz tilida 'Salom' nima?",
                "options": ["Hello", "Goodbye", "Thank you", "Please"],
                "correct": 0
            },
            {
                "q": "'Good morning' nima?",
                "options": ["Xayr", "Xayrli tong", "Xayrli tush", "Xayrli kech"],
                "correct": 1
            }
        ]
    },
    "Matematika": {
        "name": "➗ Matematika Quiz",
        "questions": [
            {
                "q": "2 + 2 = ?",
                "options": ["3", "4", "5", "6"],
                "correct": 1
            },
            {
                "q": "5 * 6 = ?",
                "options": ["30", "11", "35", "25"],
                "correct": 0
            }
        ]
    }
}

# --- BOT ASSISTANT RESPONSES ---
assistant_responses = {
    "python": "💻 Python dasturlash kursi 3 oy davom etadi, haftada 3 dars. Narxi 400.000 so'm.",
    "web": "🌐 Web dasturlash kursi HTML, CSS, JavaScript va React o'rgatadi. 3 oy davomiyligi, 400.000 so'm.",
    "kurs": "📚 Bizda turli xil kurslar mavjud: kerakli kursni tanlab o'qishingiz mumkin.",
    "narx": "💰 Kurslar narxi 300.000 dan 600.000 so'm gacha.",
    "vaqt": "⏰ Darslar haftada 3-4 kun bo'ladi.",
    "o'qituvchi": "👨‍🏫 Bizda tajribali o'qituvchilar bor.",
    "ariza": "📝 Kursga yozilish uchun arizalar bo'limiga boring.",
    "ingliz": "🇬🇧 Ingliz tili kursi 3 oy davom etadi, haftada 3 dars. Narxi 300.000 so'm.",
    "rus": "🇷🇺 Rus tili kursi 3 oy davom etadi, haftada 3 dars. Narxi 300.000 so'm.",
}

# --- Conversational knowledge base ---
assistant_knowledge = {
    "O'zbek": {
        "python": "💻 Python kursi 3 oy davom etadi, hafta 3 marta dars bo'ladi.",
        "web": "🌐 Web kursi HTML, CSS, JS va React'ni qamrab oladi.",
        "kurs": "📚 Bizda bir nechta kurs mavjud — qaysi birini xohlaysiz?",
        "narx": "💰 Kurslar narxi kursga qarab 300k-700k orasida.",
        "vaqt": "⏰ Darslar odatda haftada 3-4 marta bo'ladi.",
        "ingliz": "🇬🇧 Ingliz tili kursi 3 oy, haftada 3 marta.",
        "rus": "🇷🇺 Rus tili kursi 3 oy, haftada 3 marta."
    },
    "English": {
        "python": "💻 The Python course runs for 3 months, three lessons per week.",
        "web": "🌐 Web course covers HTML, CSS, JavaScript and React.",
        "price": "💰 Prices range from 300k to 700k depending on the course.",
        "hours": "⏰ Classes usually happen 3-4 times per week."
    },
    "Русский": {
        "python": "💻 Курс по Python длится 3 месяца, 3 занятия в неделю.",
        "web": "🌐 Веб-курс охватывает HTML, CSS, JS и React.",
        "price": "💰 Цены варьируются от 300k до 700k в зависимости от курса.",
        "hours": "⏰ Занятия обычно 3-4 раза в неделю."
    },
    "Turkish": {
        "python": "💻 Python kursu 3 ay sürer, haftada 3 ders.",
        "web": "🌐 Web kursu HTML, CSS, JS ve React'i kapsar.",
        "price": "💰 Fiyatlar kursa göre 300k-700k arasındadır.",
        "hours": "⏰ Dersler genellikle haftada 3-4 kez yapılır."
    },
    "한국어": {
        "python": "💻 파이썬 과정은 3개월 동안 주 3회 수업입니다.",
        "web": "🌐 웹 과정은 HTML, CSS, JS 및 React를 다룹니다.",
        "price": "💰 수업료는 코스에 따라 300k에서 700k 사이입니다.",
        "hours": "⏰ 수업은 보통 주 3-4회 진행됩니다."
    }
}

chat_templates = {
    "O'zbek": [
        "Ajoyib — batafsilroq aytib bera olasizmi?",
        "Tushunarli, yana qanday savollaringiz bor?",
        "Men sizga yordam berishdan xursandman — davom eting.",
        "Sizning so'rovingizni tushundim. Qo'shimcha ma'lumot kerakmi?"
    ],
    "English": [
        "Great — could you tell me more?",
        "I see, what else would you like to know?",
        "I'm happy to help — please continue.",
        "Got it. Do you need more details?"
    ],
    "Русский": [
        "Отлично — можете рассказать подробнее?",
        "Понял, что ещё вы хотели бы узнать?",
        "Рад помочь — продолжайте, пожалуйста.",
        "Понял. Нужны ли дополнительные детали?"
    ],
    "Turkish": [
        "Harika — daha fazla ayrıntı verebilir misiniz?",
        "Anladım, başka ne bilmek istiyorsunuz?",
        "Yardımcı olmaktan memnuniyet duyarım — devam edin.",
        "Anladım. Daha fazla detaya ihtiyacınız var mı?"
    ],
    "한국어": [
        "좋아요 — 자세히 알려주실 수 있나요?",
        "이해했습니다. 무엇을 더 알고 싶으신가요?",
        "도와드리게 되어 기쁩니다 — 계속해주세요.",
        "알겠습니다. 추가 정보가 필요하신가요?"
    ],
    "العربية": [
        "ممتاز — هل يمكنك أن تخبرني بالمزيد؟",
        "فهمت، ماذا تريد أن تعرف أيضاً؟",
        "سعيد بالمساعدة — تفضل بالسؤال.",
        "حسنًا. هل تحتاج إلى مزيد من التفاصيل؟"
    ],
    "中文": [
        "很棒 — 你能告诉我更多吗？",
        "我明白了，你还想知道什么？",
        "很高兴帮忙 — 请继续。",
        "明白了。你需要更多细节吗？"
    ],
    "日本語": [
        "素晴らしいです — もっと教えていただけますか？",
        "わかりました、他に何を知りたいですか？",
        "お手伝いできて嬉しいです — 続けてください。",
        "了解しました。詳細が必要ですか？"
    ]
}

# --- MOTIVATIONAL QUOTES ---
motivation_quotes = {
    "O'zbek": [
        "Ishon, harakat qil va rivojlan!",
        "Orzular faqat harakat bilan haqiqatga aylanadi.",
        "Kuching o'zing o'ylagandan ham kattaroq.",
        "Boshlash uchun mukammal bo'lish shart emas.",
        "Har kuni o'zingni kechagidan yaxshi qil.",
        "Qiyinchiliklar seni kuchli qiladi.",
        "Harakat – eng katta motivatsiya.",
        "Kutma, vaqtni o'zing yarat.",
        "Muvaffaqiyat sabr va mehnatni yaxshi ko'radi.",
        "Yiqilsang ham, oldinga yiqil.",
        "Imkonsiz degan so'z faqat qo'rqoq uchun mavjud.",
        "O'zingga ishon!",
        "Hammasi mumkin!",
        "Sen o'zingning eng katta imkoniyating san.",
        "To'xtama, sen juda yaqin turibsan.",
        "Orzularing seni kutmoqda.",
        "Harakat qilmasang, hech narsa o'zgarmaydi.",
        "Intizom – muvaffaqiyat kaliti.",
        "Har kuni 1% yaxshilan – bir yilda 37 marta yaxshilangan bo'lasan.",
        "Qo'rqma, harakat qil.",
        "Eng yaxshi vaqt – hozir.",
        "Maqsad aniq bo'lsa, yo'l topiladi.",
        "Sabr qil, ko'rasan.",
        "O'zingni yeng – dunyoni yengasan.",
        "Bugungi intilish – ertangi faxr.",
        "Harakat – orzu va natija o'rtasidagi ko'prik.",
        "Sen o'ylagandan kuchliroqsan.",
        "Maqsad sari har kuni bir qadam tashla.",
        "Imkoniyatlar harakat qilganlarga ochiladi.",
        "Sabr qil, hammasi keladi.",
        "Harakat hech qachon bekor ketmaydi.",
        "Sen bunga loyiqsan."
    ],
    "English": [
        "Believe in yourself and take action!",
        "Every small step matters for the future.",
        "Success is the sum of daily efforts.",
        "Don't wait for the perfect moment, take the moment and make it perfect.",
        "Your only limit is your mind.",
        "Dream big and dare to fail.",
        "It always seems impossible until it's done.",
        "The future depends on what you do today."
    ],
    "Русский": [
        "Верь в себя и действуй!",
        "Каждый маленький шаг важен для будущего.",
        "Успех — это сумма ежедневных усилий.",
        "Не жди идеального момента, сделай этот момент идеальным.",
        "Единственное ограничение — это твой разум.",
        "Мечтай о великом и не бойся ошибаться."
    ],
    "Turkish": [
        "Kendine inan ve harekete geç!",
        "Gelecek için her küçük adım önemlidir.",
        "Başarı, günlük çabaların toplamıdır.",
        "Mükemmel anı beklemeyin, anı alın ve mükemmel yapın.",
        "Tek sınırınız zihninizdir."
    ],
    "한국어": [
        "자신을 믿고 행동하세요!",
        "미래를 위해 작은 한 걸음도 중요합니다.",
        "성공은 매일의 노력의 합입니다.",
        "완벽한 순간을 기다리지 말고, 순간을 완벽하게 만드세요.",
        "당신의 유일한 한계는 당신의 마음입니다."
    ]
}

def generate_chatbot_reply(user_id, text):
    """
    Foydalanuvchi xabariga javob qaytaradi.
    Birinchi knowledge base dan qidiradi, topilmasa template qaytaradi.
    """
    lang = get_user_lang(user_id)
    text_l = (text or "").lower()

    skey = find_subject_key(text_l)
    if skey:
        price = get_course_price(skey)
        name = subjects.get(skey, skey)
        return f"{name}\nNarxi: {price} so'm\nKurs mavjud.\nKursga yozilmoqchimisiz?"

    # Check knowledge base for keywords
    kb = assistant_knowledge.get(lang, assistant_knowledge.get("O'zbek", {}))
    for key, ans in kb.items():
        if key in text_l:
            return ans

    # Check multilingual assistant_responses (fallback)
    for key, ans in assistant_responses.items():
        if key in text_l:
            return ans

    # Otherwise return a friendly templated reply
    tpl = chat_templates.get(lang, chat_templates.get("O'zbek", ["👍"]))
    return random.choice(tpl)

def get_user_lang(user_id):
    # First check in-memory mapping
    if user_id in user_languages:
        return user_languages[user_id]
    # Fallback to DB
    db = load_db()
    u = db.get("user_languages", {})
    lang = u.get(str(user_id))
    if lang:
        user_languages[user_id] = lang
        return lang
    return "O'zbek"

def send_motivation(user_id):
    """Send a random motivational quote in the user's language."""
    lang = get_user_lang(user_id)
    quotes = motivation_quotes.get(lang, motivation_quotes.get("English", motivation_quotes["O'zbek"]))
    return random.choice(quotes)

# --- MAIN INLINE MENU ---
def main_menu():
    return main_menu_lang("O'zbek")

def main_menu_lang(lang="O'zbek"):
    labels = {
        "O'zbek": {
            "courses": "📚 Kurslar",
            "trial": "💻 Trial Kurs",
            "teachers": "👨‍🏫 O‘qituvchilar",
            "subjects": "📂 Fanlar",
            "quiz": "📝 Quiz",
            "test": "🧪 Test",
            "chat": "💬 Chat",
            "motivation": "🎯 Motivatsiya",
            "check": "🧾 Chek/Tolov",
            "search_teacher": "🔍 O'qituvchi izlash",
            "arizalar": "📝 Arizalar",
            "contact": "📞 Aloqa",
            "site": "🌐 Veb-sayt",
            "telegram": "📱 Telegram",
            "instagram": "📸 Instagram",
            "facebook": "📘 Facebook",
            "admin": "🛠 Admin",
            "teacher_panel": "👨‍🏫 O‘qituvchi"
        },
        "English": {
            "courses": "📚 Courses",
            "trial": "💻 Trial Course",
            "teachers": "👨‍🏫 Teachers",
            "subjects": "📂 Subjects",
            "quiz": "📝 Quiz",
            "test": "🧪 Test",
            "chat": "💬 Chat",
            "motivation": "🎯 Motivation",
            "check": "🧾 Receipt/Payment",
            "search_teacher": "🔍 Find Teacher",
            "arizalar": "📝 Applications",
            "contact": "📞 Contact",
            "site": "🌐 Website",
            "telegram": "📱 Telegram",
            "instagram": "📸 Instagram",
            "facebook": "📘 Facebook",
            "admin": "🛠 Admin",
            "teacher_panel": "👨‍🏫 Teacher"
        },
        "Русский": {
            "courses": "📚 Курсы",
            "trial": "💻 Пробный курс",
            "teachers": "👨‍🏫 Преподаватели",
            "subjects": "📂 Предметы",
            "quiz": "📝 Викторина",
            "test": "🧪 Тест",
            "chat": "💬 Чат",
            "motivation": "🎯 Мотивация",
            "check": "🧾 Чек/Платёж",
            "search_teacher": "🔍 Поиск преподавателя",
            "arizalar": "📝 Заявки",
            "contact": "📞 Контакты",
            "site": "🌐 Сайт",
            "telegram": "📱 Telegram",
            "instagram": "📸 Instagram",
            "facebook": "📘 Facebook",
            "admin": "🛠 Админ",
            "teacher_panel": "👨‍🏫 Преподаватель"
        }
    }

    l = labels.get(lang, labels["O'zbek"])
    markup = InlineKeyboardMarkup(row_width=2)
    
    # Add buttons
    if "motivation" in l:
        markup.add(InlineKeyboardButton(l["motivation"], callback_data="motivation"))
    
    markup.add(
        InlineKeyboardButton(l["courses"], callback_data="kurslar"),
        InlineKeyboardButton(l["trial"], callback_data="trial")
    )
    markup.add(
        InlineKeyboardButton(l["teachers"], callback_data="teachers"),
        InlineKeyboardButton(l["subjects"], callback_data="subjects")
    )
    markup.add(
        InlineKeyboardButton(l["quiz"], callback_data="quiz"),
        InlineKeyboardButton(l["test"], callback_data="test")
    )
    markup.add(
        InlineKeyboardButton(l["chat"], callback_data="chat"),
        InlineKeyboardButton(l["search_teacher"], callback_data="search_teacher")
    )
    markup.add(
        InlineKeyboardButton(l["arizalar"], callback_data="arizalar"),
        InlineKeyboardButton(l["check"], callback_data="check")
    )
    markup.add(InlineKeyboardButton(l["teacher_panel"], callback_data="teacher_panel"))
    markup.add(InlineKeyboardButton(l["admin"], callback_data="admin"))
    markup.add(InlineKeyboardButton(l["contact"], url="https://t.me/saminovschool"))
    markup.add(InlineKeyboardButton(l["site"], url="https://saminovschool.uz"))
    markup.add(InlineKeyboardButton(l["telegram"], url="https://t.me/saminovschool"))
    markup.add(InlineKeyboardButton(l["instagram"], url="https://instagram.com/saminovschool"))
    markup.add(InlineKeyboardButton(l["facebook"], url="https://facebook.com/saminovschool"))
    
    return markup

def back_button():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
    return markup

# Storage for form data in progress
user_form_state = {}  # {user_id: {"type": "kurs"|"ish", "name": str, "phone": str, "subject": str}}
check_form_states = {}  # {user_id: {"name": str, "teacher": str, "subject": str, "amount": str}}
user_quiz_state = {}
quiz_question_time = {}  # Track when each question was shown
QUIZ_TIME_LIMIT = 30  # seconds
admin_edit_state = {}
admin_notify_state = {}
admin_test_state = {}
admin_delete_state = {}
teacher_sessions = set()

def get_quiz_uploads():
    db = load_db()
    return db.get("quiz_uploads", {})

def set_quiz_upload(subject_key, quiz_obj):
    db = load_db()
    q = db.get("quiz_uploads", {})
    q[subject_key] = quiz_obj
    db["quiz_uploads"] = q
    save_db(db)

def get_quiz(quiz_key):
    if quiz_key in quiz_data:
        return quiz_data[quiz_key]
    if quiz_key.startswith("db:"):
        subj = quiz_key.split(":", 1)[1]
        uploads = get_quiz_uploads()
        return uploads.get(subj)
    return None

def has_quiz(quiz_key):
    if quiz_key in quiz_data:
        return True
    if quiz_key.startswith("db:"):
        subj = quiz_key.split(":", 1)[1]
        return subj in get_quiz_uploads()
    return False

def parse_test_text(text):
    blocks = re.split(r"\n\s*\n", text.strip())
    questions = []
    for blk in blocks:
        lines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not lines:
            continue
        q = lines[0]
        opts = []
        correct = None
        for l in lines[1:]:
            m = re.match(r"^(\d+)[\)\.\:\-\s]+(.*)$", l)
            if m:
                opts.append(m.group(2).strip())
                continue
            m2 = re.search(r"(correct|javob)\s*[:\-]\s*(\d+)", l, flags=re.I)
            if m2:
                try:
                    correct = int(m2.group(2)) - 1
                except Exception:
                    pass
        if len(opts) >= 2:
            if correct is None or correct < 0 or correct >= len(opts):
                correct = 0
            questions.append({"q": q, "options": opts, "correct": correct})
    return questions

def download_telegram_file(file_id):
    f = bot.get_file(file_id)
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f.file_path}"
    data = urlopen(url).read()
    return data

def get_check_state(user_id):
    return check_form_states.get(user_id, {})

def set_check_state(user_id, data):
    check_form_states[user_id] = data

def clear_check_state(user_id):
    check_form_states.pop(user_id, None)

def get_teacher_links():
    db = load_db()
    return db.get("teacher_links", {})

def set_teacher_link(user_id, link):
    db = load_db()
    links = db.get("teacher_links", {})
    links[str(user_id)] = link
    db["teacher_links"] = links
    save_db(db)

def is_teacher(user_id):
    links = get_teacher_links()
    return str(user_id) in links

def get_teacher_subject_for_user(user_id):
    links = get_teacher_links()
    l = links.get(str(user_id))
    if not l:
        return None
    if l.get("type") == "base":
        key = l.get("key")
        t = apply_teacher_override(key, teachers.get(key, {}))
        return l.get("subject") or t.get("subject_key") or key
    if l.get("type") == "custom":
        dbt = get_custom_teachers()
        for t in dbt:
            if t.get("id") == l.get("id"):
                return l.get("subject") or t.get("subject")
    return None

def get_teacher_passwords():
    db = load_db()
    return db.get("teacher_passwords", {})

def set_teacher_password_for_ref(ref, pwd):
    db = load_db()
    tps = db.get("teacher_passwords", {})
    tps[ref] = pwd
    db["teacher_passwords"] = tps
    save_db(db)

def delete_teacher_password_for_ref(ref):
    db = load_db()
    tps = db.get("teacher_passwords", {})
    if ref in tps:
        del tps[ref]
        db["teacher_passwords"] = tps
        save_db(db)

def find_teacher_ref_by_password(pwd):
    tps = get_teacher_passwords()
    for ref, p in tps.items():
        if p == pwd:
            return ref
    return None

def teacher_ref_to_name(ref):
    try:
        kind, val = ref.split(":", 1)
    except ValueError:
        return ref
    if kind == "base":
        t = apply_teacher_override(val, teachers.get(val, {}))
        return format_full_name(t) or val
    if kind == "custom":
        try:
            tid = int(val)
        except Exception:
            return ref
        for t in get_custom_teachers():
            if t.get("id") == tid:
                return t.get("name", f"custom:{tid}")
    return ref

# --- LANGUAGE SELECTION ---
def language_menu():
    """Til tanlash tugmalari"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang:O'zbek"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:English"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:Русский"),
        InlineKeyboardButton("🇹🇷 Turkish", callback_data="lang:Turkish"),
        InlineKeyboardButton("🇰🇷 한국어", callback_data="lang:한국어"),
        InlineKeyboardButton("🇸🇦 العربية", callback_data="lang:العربية"),
        InlineKeyboardButton("🇨🇳 中文", callback_data="lang:中文"),
        InlineKeyboardButton("🇯🇵 日本語", callback_data="lang:日本語")
    )
    return markup

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]  # chat rejimidan chiqish
    # FIX 7: /start da avtomatik obunaga qo'shish + admin xabari
    add_subscriber(user_id, user=message.from_user)
    # Try auto-detect language and greet accordingly
    detect_and_set_language(message)
    user_lang = user_languages.get(message.from_user.id, "O'zbek")
    welcome_texts = {
        "O'zbek": "🎓 Saminov School o‘quv markazi\nKerakli bo‘limni tanlang:",
        "English": "🎓 Saminov School\nPlease choose a section:",
        "Русский": "🎓 Saminov School\nПожалуйста, выберите раздел:",
        "Turkish": "🎓 Saminov School\nLütfen bir bölüm seçin:",
        "한국어": "🎓 Saminov School\n섹션을 선택하세요:",
        "العربية": "🎓 مدرسة سامينوف\nيرجى اختيار قسم:",
        "中文": "🎓 萨米诺夫学校\n请选择一个部分:",
        "日本語": "🎓 サミノフスクール\nセクションを選択してください:" 
    }
    bot.send_message(
        message.chat.id,
        welcome_texts.get(user_lang, welcome_texts["O'zbek"]),
        reply_markup=main_menu_lang(user_lang)
    )

# --- GREETING HANDLER (LANGUAGE SELECTION) ---
@bot.message_handler(func=lambda message: any(greeting in (message.text or "").lower() for greeting in ["salom", "hello", "привет", "merhaba", "안녕", "مرحبا", "你好", "こんにちは"]))
def handle_greeting(message):
    """Salom/Hello/Привет desa til tanlash ko'rsatiladi"""
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]  # chat rejimidan chiqish
    # First try auto-detection; if not set, show language menu
    detect_and_set_language(message)
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "O'zbek")
    lang_messages = {
        "O'zbek": "🇺🇿 Xush kelibsiz! Menyudan davom eting.",
        "English": "🇬🇧 Welcome! Continue from the menu.",
        "Русский": "🇷🇺 Добро пожаловать! Продолжайте из меню.",
        "Turkish": "🇹🇷 Hoş geldiniz! Menüden devam edin.",
        "한국어": "🇰🇷 환영합니다! 메뉴에서 계속 하세요.",
        "العربية": "🇸🇦 أهلاً وسهلاً! تابع من القائمة.",
        "中文": "🇨🇳 欢迎！请从菜单继续.",
        "日本語": "🇯🇵 ようこそ！メニューから続行してください。"
    }
    bot.send_message(message.chat.id, lang_messages.get(lang, lang_messages["O'zbek"]), reply_markup=main_menu_lang(lang))

# --- EXIT COMMAND ---
@bot.message_handler(commands=['exit'])
def exit_command(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    lang = get_user_lang(user_id)
    bot.send_message(message.chat.id, "👋 Suhbat rejimidan chiqildi.", reply_markup=main_menu_lang(lang))

# --- TEXT MESSAGE HANDLER ---
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_message(message):
    user_id = message.from_user.id

    # Guruh xabarlarini filtrlash
    if message.chat.type in ["group", "supergroup"]:
        me = get_bot_me()
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == me.id
        is_mention = f"@{me.username}" in (message.text or "")
        if not (is_reply or is_mention):
            return

    # Forma jarayonida bo‘lsa, ularni bezovta qilmaymiz
    if user_id in check_form_states or user_id in user_form_state:
        return

    text = (message.text or "").strip()
    if not text:
        return

    # Ismni aniqlash
    lower = text.lower()
    name_prefixes = ["ismim ", "mening ismim ", "my name is ", "call me ", "men ismim "]
    for p in name_prefixes:
        if lower.startswith(p):
            name = text[len(p):].strip()
            if name:
                set_user_name(user_id, name)
                bot.send_message(message.chat.id, f"Salom {name}! Ismingiz saqlandi.")
                return

    # Suhbat rejimi
    if user_id in chat_mode:
        reply = generate_chatbot_reply(user_id, lower)
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Exit Chat", callback_data="exit_chat"))
        bot.send_message(message.chat.id, reply, reply_markup=markup)
        return

    skey = find_subject_key(lower)
    if skey:
        price = get_course_price(skey)
        name = subjects.get(skey, skey)
        reply = f"{name}\nNarxi: {price} so'm\nKurs mavjud.\nKursga yozilmoqchimisiz?"
        mk = InlineKeyboardMarkup()
        mk.add(
            InlineKeyboardButton("✅ Ha", callback_data=f"qa_apply_subject:{skey}"),
            InlineKeyboardButton("❌ Yo'q", callback_data="qa_apply_no")
        )
        bot.send_message(message.chat.id, reply, reply_markup=mk)
        return
    # Oddiy rejim (asosiy menyu bilan)
    reply = generate_chatbot_reply(user_id, lower)
    bot.send_message(message.chat.id, reply, reply_markup=main_menu_lang(get_user_lang(user_id)))

# --- NAME & SUBSCRIPTION HELPERS ---
def set_user_name(user_id, name):
    db = load_db()
    if "names" not in db:
        db["names"] = {}
    db["names"][str(user_id)] = name
    save_db(db)

def notify_admins_new_member(user):
    """Yangi a'zo qo'shilganda adminlarga xabar yuboradi"""
    user_id = user.id
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = (first_name + " " + last_name).strip() or "Nomsiz"
    username = user.username

    # Profilga havola: username bo'lsa @username, bo'lmasa tg://user?id=...
    if username:
        link = f"https://t.me/{username}"
    else:
        link = f"tg://user?id={user_id}"

    msg = (
        f"🔔 Botga yangi a'zo qo'shildi\n\n"
        f"👤 <a href=\"{link}\">{full_name}</a>\n"
        f"🆔 ID: <code>{user_id}</code>"
    )
    if username:
        msg += f"\n📱 @{username}"

    for admin_id in all_admins():
        try:
            bot.send_message(admin_id, msg, parse_mode="HTML")
        except Exception:
            pass

def add_subscriber(user_id, user=None):
    db = load_db()
    subs = set(db.get("subscribers", []))
    is_new = int(user_id) not in subs
    subs.add(int(user_id))
    db["subscribers"] = list(subs)
    save_db(db)
    # Faqat YANGI a'zolar haqida adminlarga xabar
    if is_new and user is not None:
        notify_admins_new_member(user)

def remove_subscriber(user_id):
    db = load_db()
    subs = set(db.get("subscribers", []))
    subs.discard(int(user_id))
    db["subscribers"] = list(subs)
    save_db(db)

@bot.message_handler(commands=["setname"])
def cmd_setname(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    parts = message.text.split(' ', 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.send_message(message.chat.id, "Foydalanish: /setname Ismingiz")
        return
    name = parts[1].strip()
    set_user_name(message.from_user.id, name)
    bot.send_message(message.chat.id, f"Salom {name}! Ismingiz saqlandi. Endi /subscribe bilan obuna bo'ling.")

@bot.message_handler(commands=["subscribe"])
def cmd_subscribe(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    add_subscriber(message.from_user.id)
    bot.send_message(message.chat.id, "Siz obuna bo'ldingiz. Rahmat!")

@bot.message_handler(commands=["unsubscribe"])
def cmd_unsubscribe(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    remove_subscriber(message.from_user.id)
    bot.send_message(message.chat.id, "Siz obunadan chiqdingiz.")

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    # Admin-only broadcast to subscribers
    if message.from_user.id not in ADMINS:
        bot.send_message(message.chat.id, "Sizda ruxsat yo'q.")
        return
    parts = message.text.split(' ', 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.send_message(message.chat.id, "Foydalanish: /broadcast Xabar matni")
        return
    text = parts[1].strip()
    db = load_db()
    subs = db.get("subscribers", [])
    sent = 0
    for sid in subs:
        try:
            bot.send_message(int(sid), text)
            sent += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"Xabar {sent} obunachiga yuborildi.")

@bot.message_handler(commands=["motivation"])
def motivation_command(message):
    user_id = message.from_user.id
    if user_id in chat_mode:
        del chat_mode[user_id]
    """Send a random motivational quote in the user's language."""
    quote = send_motivation(message.from_user.id)
    bot.send_message(
        message.chat.id,
        quote,
        reply_markup=main_menu_lang(get_user_lang(message.from_user.id))
    )

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda call: not call.data.startswith("answer:"))
def callback(call):
    db = load_db()

    # EXIT CHAT CALLBACK
    if call.data == "exit_chat":
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        if user_id in chat_mode:
            del chat_mode[user_id]
        lang = get_user_lang(user_id)
        bot.send_message(chat_id, "👋 Suhbat rejimidan chiqildi.", reply_markup=main_menu_lang(lang))
        bot.answer_callback_query(call.id)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        return

    # APPROVE CHECK
    if call.data.startswith("approve_check:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        try:
            check_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Xatolik: ID noto'g'ri")
            return
        found = False
        for check in db.get("checks", []):
            if check["id"] == check_id:
                found = True
                if check["status"] != "kutilmoqda":
                    bot.answer_callback_query(call.id, "Bu chek allaqachon ko'rib chiqilgan!")
                    return
                check["status"] = "tasdiqlandi"
                save_db(db)
                user_id = check["user_id"]
                lang = get_user_lang(user_id)
                subject_name = subjects.get(check.get("subject"), check.get("subject", "N/A"))
                confirmations = {
                    "O'zbek": f"✅ To'lovingiz tasdiqlandi!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')} so'm",
                    "English": f"✅ Payment confirmed!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')}",
                    "Русский": f"✅ Платёж подтверждён!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')}"
                }
                try:
                    bot.send_message(user_id, confirmations.get(lang, confirmations["O'zbek"]))
                except Exception as e:
                    print(f"Error sending confirmation to user: {e}")
                subject_name_admin = subjects.get(check.get("subject"), check.get("subject", "N/A"))
                try:
                    bot.edit_message_caption(
                        caption=f"✅ TASDIQLANDI\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name_admin}\n💰 {check.get('amount')} so'm\n🕒 {check['time']}\nID: {check_id}",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id
                    )
                except Exception as e:
                    print(f"Error editing caption: {e}")
                bot.answer_callback_query(call.id, "✅ Tasdiqlandi!")
                return
        if not found:
            bot.answer_callback_query(call.id, "Chek topilmadi!")
        return

    # REJECT CHECK
    if call.data.startswith("reject_check:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        try:
            check_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Xatolik: ID noto'g'ri")
            return
        found = False
        for check in db.get("checks", []):
            if check["id"] == check_id:
                found = True
                if check["status"] != "kutilmoqda":
                    bot.answer_callback_query(call.id, "Bu chek allaqachon ko'rib chiqilgan!")
                    return
                check["status"] = "rad_etildi"
                save_db(db)
                user_id = check["user_id"]
                lang = get_user_lang(user_id)
                subject_name = subjects.get(check.get("subject"), check.get("subject", "N/A"))
                rejections = {
                    "O'zbek": f"❌ To'lovingiz rad etildi!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')} so'm\n\nIltimos, to'g'ri chekni yuboring.",
                    "English": f"❌ Payment rejected!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')}\n\nPlease send a valid receipt.",
                    "Русский": f"❌ Платёж отклонён!\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name}\n💰 {check.get('amount')}\n\nПожалуйста, отправьте правильный чек."
                }
                try:
                    bot.send_message(user_id, rejections.get(lang, rejections["O'zbek"]))
                except Exception as e:
                    print(f"Error sending rejection to user: {e}")
                subject_name_admin = subjects.get(check.get("subject"), check.get("subject", "N/A"))
                try:
                    bot.edit_message_caption(
                        caption=f"❌ RAD ETILDI\n\n👤 {check.get('name')}\n👨‍🏫 {check.get('teacher')}\n📂 {subject_name_admin}\n💰 {check.get('amount')} so'm\n🕒 {check['time']}\nID: {check_id}",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id
                    )
                except Exception as e:
                    print(f"Error editing caption: {e}")
                bot.answer_callback_query(call.id, "❌ Rad etildi!")
                return
        if not found:
            bot.answer_callback_query(call.id, "Chek topilmadi!")
        return

    # CHECK_SUBJECT selection
    if call.data.startswith("check_subject:"):
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        subject_key = call.data.split(":", 1)[1]
        state = get_check_state(user_id)
        if not state or "name" not in state:
            # State yo'q - qaytadan boshlaymiz
            bot.answer_callback_query(call.id, "❌ Session tugadi. Qaytadan boshlang.")
            ask_name_texts = {
                "O'zbek": "👤 Ismingizni yozing:",
                "English": "👤 Enter your name:",
                "Русский": "👤 Напишите ваше имя:"
            }
            msg = bot.send_message(call.message.chat.id, ask_name_texts.get(lang, ask_name_texts["O'zbek"]))
            bot.register_next_step_handler(msg, check_name)
            return
        state["subject"] = subject_key
        set_check_state(user_id, state)
        ask_amount = {
            "O'zbek": f"✅ Fan: {subjects.get(subject_key, subject_key)}\n\n💰 Tolov miqdorini yozing (so'm):",
            "English": f"✅ Subject: {subjects.get(subject_key, subject_key)}\n\n💰 Enter payment amount:",
            "Русский": f"✅ Предмет: {subjects.get(subject_key, subject_key)}\n\n💰 Напишите сумму платежа:"
        }
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, ask_amount.get(lang, ask_amount["O'zbek"]))
        bot.register_next_step_handler(msg, check_amount)
        return

    if call.data == "kurslar":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        for k, v in subjects.items():
            markup.add(InlineKeyboardButton(v, callback_data=f"subject:{k}"))
        markup.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        bot.edit_message_text(
            "📚 Bizning kurslar — bo'limni tanlang:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    # TRIAL KURS
    elif call.data == "trial":
        bot.answer_callback_query(call.id)
        text = "💻 Trial kurs:\nPython dasturlashning kirish darslari bepul."
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=back_button()
        )
    
    # motivation quote
    elif call.data == "motivation":
        bot.answer_callback_query(call.id)
        quote = send_motivation(call.from_user.id if hasattr(call, 'from_user') else call.message.chat.id)
        bot.edit_message_text(
            quote,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_button()
        )
    
    # tanlangan predmet uchun ma'lumot
    elif call.data.startswith("subject:"):
        key = call.data.split(":", 1)[1]
        info = subjects.get(key, "Ma'lumot topilmadi.")
        price = get_course_price(key)
        info = f"{info}\nNarxi: {price} so'm"
        bot.edit_message_text(
            info,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_button()
        )
    
    # O‘QITUVCHILAR
    elif call.data == "teachers":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        for key in teachers:
            t = apply_teacher_override(key, teachers[key])
            nm = format_full_name(t)
            price = t.get("price")
            label = f"{nm} — {price}" if price else nm
            markup.add(InlineKeyboardButton(label, callback_data=key))
        bot.edit_message_text(
            "👨‍🏫 O‘qituvchini tanlang:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif call.data in teachers:
        t = apply_teacher_override(call.data, teachers[call.data])
        info = t.get("info") or f"👤 {(t.get('name','') + (' ' + t.get('surname','') if t.get('surname') else '')).strip()}\n📂 {t.get('subject','')}"
        bot.edit_message_text(
            info,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_button()
        )

    # FANLAR — subjects tugmalari (xuddi kurslar bilan bir xil)
    elif call.data == "subjects":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        for k, v in subjects.items():
            markup.add(InlineKeyboardButton(v, callback_data=f"subject:{k}"))
        markup.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        bot.edit_message_text(
            "📂 Fanlar — bo'limni tanlang:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    # ARIZALAR
    elif call.data == "arizalar":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("📄 Kursga yozilish", callback_data="ariza_course"),
            InlineKeyboardButton("💼 Ishga kirish", callback_data="ariza_job"),
        )
        markup.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        bot.edit_message_text(
            "📝 Ariza bo‘limi",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif call.data == "admin":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        m = InlineKeyboardMarkup(row_width=2)
        m.add(
            InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton("🎲 Tasodifiy g'olib", callback_data="admin_random")
        )
        m.add(
            InlineKeyboardButton("➕ Admin qo'shish", callback_data="admin_add_admin"),
            InlineKeyboardButton("👥 Adminlar", callback_data="admin_list_admins")
        )
        m.add(
            InlineKeyboardButton("➕ O'qituvchi qo'shish", callback_data="admin_add_teacher"),
            InlineKeyboardButton("👨‍🏫 O'qituvchilar", callback_data="admin_list_teachers")
        )
        m.add(InlineKeyboardButton("📢 E'lon yuborish", callback_data="admin_broadcast"))
        m.add(InlineKeyboardButton("📄 Test yuklash (PDF/TXT)", callback_data="admin_test_upload"))
        m.add(InlineKeyboardButton("👨‍🏫 O'qituvchi bo'limi", callback_data="admin_teachers_section"))
        m.add(InlineKeyboardButton("🧩 Ma'lumotlarni tahrirlash", callback_data="admin_manage_data"))
        m.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        bot.edit_message_text("🛠 Admin paneli", call.message.chat.id, call.message.message_id, reply_markup=m)

    elif call.data == "admin_stats":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        subs = len(db.get("subscribers", []))
        students = len(db.get("students", []))
        arizalar = db.get("arizalar", [])
        checks = db.get("checks", [])
        ariza_count = len(arizalar)
        checks_pending = sum(1 for c in checks if c.get("status") == "kutilmoqda")
        checks_ok = sum(1 for c in checks if c.get("status") == "tasdiqlandi")
        checks_rej = sum(1 for c in checks if c.get("status") == "rad_etildi")
        langs = db.get("user_languages", {})
        admins_list = db.get("admins", [])
        msg = (
            f"📊 Statistika\n"
            f"🎓 Talabalar: {students}\n"
            f"👥 Obunachilar: {subs}\n"
            f"📝 Arizalar: {ariza_count}\n"
            f"🧾 Cheklar: {len(checks)}\n"
            f"  • Kutilmoqda: {checks_pending}\n"
            f"  • Tasdiqlangan: {checks_ok}\n"
            f"  • Rad etilgan: {checks_rej}\n"
            f"👨‍💼 Adminlar: {len(admins_list) + len(ADMINS)}\n"
            f"🌐 Foydalanuvchilar: {len(langs)}"
        )
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "admin_add_admin":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        msg = bot.send_message(call.message.chat.id, "🆔 Yangi admin user ID ni yozing:")
        bot.register_next_step_handler(msg, admin_add_admin_step)

    elif call.data == "admin_list_admins":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        ids = all_admins()
        bot.edit_message_text("👥 Adminlar:\n" + "\n".join([str(i) for i in ids]), call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "admin_random":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        subs = db.get("subscribers", [])
        if not subs:
            bot.answer_callback_query(call.id, "Obunachilar topilmadi!")
            return
        winner = random.choice(subs)
        bot.edit_message_text(f"🎉 Tasodifiy g'olib: {winner}", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "admin_add_teacher":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        msg = bot.send_message(call.message.chat.id, "👤 O'qituvchi ismini yozing:")
        bot.register_next_step_handler(msg, teacher_add_name_step)

    elif call.data == "admin_list_teachers":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        base = []
        for k, t in teachers.items():
            cur = apply_teacher_override(k, t)
            nm = format_full_name(cur)
            price = cur.get("price")
            base.append(f"{nm}" + (f" — {price}" if price else ""))
        dbt = get_custom_teachers()
        names = base + [(t.get("name","") + (f" — {t.get('price')}" if t.get("price") else "")) for t in dbt]
        bot.edit_message_text("👨‍🏫 O'qituvchilar:\n" + "\n".join(names), call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "admin_broadcast":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        msg = bot.send_message(
            call.message.chat.id,
            "📢 E'lon matnini yozing:",
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Bekor qilish", callback_data="admin"))
        )
        bot.register_next_step_handler(msg, admin_broadcast_step)

    elif call.data == "admin_manage_data":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        m = InlineKeyboardMarkup(row_width=2)
        m.add(InlineKeyboardButton("🗑 Adminni o'chirish", callback_data="admin_remove_admin"))
        m.add(
            InlineKeyboardButton("✏️ O'qituvchini tahrirlash", callback_data="admin_teacher_edit")
        )
        m.add(
            InlineKeyboardButton("🗑 O'qituvchini o'chirish", callback_data="admin_teacher_delete")
        )
        m.add(
            InlineKeyboardButton("✏️ Arizani tahrirlash", callback_data="admin_ariza_edit"),
            InlineKeyboardButton("🗑 Arizani o'chirish", callback_data="admin_ariza_delete")
        )
        m.add(InlineKeyboardButton("📩 Arizaga xabar yuborish", callback_data="admin_ariza_notify"))
        m.add(InlineKeyboardButton("📢 Fan bo'yicha xabar", callback_data="admin_ariza_notify_subject"))
        m.add(
            InlineKeyboardButton("✏️ Chekni tahrirlash", callback_data="admin_check_edit"),
            InlineKeyboardButton("🗑 Chekni o'chirish", callback_data="admin_check_delete")
        )
        m.add(InlineKeyboardButton("🗑 Obunachini o'chirish", callback_data="admin_subscriber_delete"))
        m.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin"))
        bot.edit_message_text("🧩 Ma'lumotlarni tahrirlash", call.message.chat.id, call.message.message_id, reply_markup=m)

    elif call.data == "admin_teachers_section":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        m = InlineKeyboardMarkup(row_width=2)
        m.add(
            InlineKeyboardButton("➕ O'qituvchi qo'shish", callback_data="admin_add_teacher"),
            InlineKeyboardButton("👨‍🏫 O'qituvchilar", callback_data="admin_list_teachers")
        )
        m.add(
            InlineKeyboardButton("✏️ O'qituvchini tahrirlash", callback_data="admin_teacher_edit"),
            InlineKeyboardButton("🗑 O'qituvchini o'chirish", callback_data="admin_teacher_delete")
        )
        m.add(
            InlineKeyboardButton("🔐 Parol o'rnatish", callback_data="admin_tp_setpwd"),
            InlineKeyboardButton("🗂 Parollarni boshqarish", callback_data="admin_tp_list")
        )
        m.add(InlineKeyboardButton("📄 Test yuklash (PDF/TXT)", callback_data="admin_test_upload"))
        m.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin"))
        bot.edit_message_text("👨‍🏫 O'qituvchi bo'limi", call.message.chat.id, call.message.message_id, reply_markup=m)

    elif call.data.startswith("qa_apply_subject:"):
        key = call.data.split(":", 1)[1]
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        user_form_state[user_id] = {"type": "kurs", "subject": key, "strict_phone": True}
        msg = bot.send_message(call.message.chat.id, "👤 Ismingizni yozing:")
        bot.register_next_step_handler(msg, course_name)

    elif call.data == "admin_test_upload":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        kbd = InlineKeyboardMarkup(row_width=1)
        for k, v in subjects.items():
            kbd.add(InlineKeyboardButton(v, callback_data=f"admin_test_subject:{k}"))
        kbd.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_teachers_section"))
        bot.edit_message_text("Fanni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=kbd)

    elif call.data.startswith("admin_test_subject:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        subj = call.data.split(":",1)[1]
        admin_test_state[call.from_user.id] = {"subject": subj}
        msg = bot.send_message(
            call.message.chat.id,
            "PDF yoki TXT faylini yuboring (savollar: bir bo‘limda savol, keyin 1) 2) ..., va Correct: n).",
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_teachers_section"))
        )
        bot.register_next_step_handler(msg, admin_test_receive_file)

    elif call.data == "admin_tp_setpwd":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        kbd = InlineKeyboardMarkup(row_width=1)
        for k, t in teachers.items():
            nm = format_full_name(apply_teacher_override(k, t))
            kbd.add(InlineKeyboardButton(nm, callback_data=f"admin_tp_setpwd_base:{k}"))
        for t in get_custom_teachers():
            kbd.add(InlineKeyboardButton(t.get("name",""), callback_data=f"admin_tp_setpwd_custom:{t.get('id')}"))
        kbd.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_teachers_section"))
        bot.edit_message_text("Parol o'rnatish — o'qituvchi tanlang:", call.message.chat.id, call.message.message_id, reply_markup=kbd)

    elif call.data.startswith("admin_tp_setpwd_base:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        key = call.data.split(":",1)[1]
        admin_edit_state[call.from_user.id] = {"tp_ref": f"base:{key}"}
        msg = bot.send_message(call.message.chat.id, "Yangi parolni yozing:")
        bot.register_next_step_handler(msg, admin_tp_setpwd_input_step)

    elif call.data.startswith("admin_tp_setpwd_custom:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        tid = call.data.split(":",1)[1]
        admin_edit_state[call.from_user.id] = {"tp_ref": f"custom:{tid}"}
        msg = bot.send_message(call.message.chat.id, "Yangi parolni yozing:")
        bot.register_next_step_handler(msg, admin_tp_setpwd_input_step)

    elif call.data == "admin_tp_list":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        tps = get_teacher_passwords()
        if not tps:
            bot.edit_message_text("Parollar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        kbd = InlineKeyboardMarkup(row_width=1)
        for ref in tps.keys():
            kbd.add(InlineKeyboardButton(f"O'chirish: {teacher_ref_to_name(ref)}", callback_data=f"admin_tp_delpwd:{ref}"))
        kbd.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_teachers_section"))
        bot.edit_message_text("Parollar ro'yxati (parol ko'rsatilmaydi):", call.message.chat.id, call.message.message_id, reply_markup=kbd)

    elif call.data.startswith("admin_tp_delpwd:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        ref = call.data.split(":",1)[1]
        admin_edit_state[call.from_user.id] = {"tp_del_ref": ref}
        mk = InlineKeyboardMarkup()
        mk.add(
            InlineKeyboardButton("✅ Ha", callback_data=f"admin_tp_delpwd_yes:{ref}"),
            InlineKeyboardButton("❌ Yo'q", callback_data="admin_teachers_section")
        )
        bot.edit_message_text(f"{teacher_ref_to_name(ref)} paroli o'chirilsinmi?", call.message.chat.id, call.message.message_id, reply_markup=mk)

    elif call.data.startswith("admin_tp_delpwd_yes:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        ref = call.data.split(":",1)[1]
        delete_teacher_password_for_ref(ref)
        bot.edit_message_text("✅ Parol o'chirildi.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "qa_apply_no":
        bot.answer_callback_query(call.id, "Yaxshi, menyudan davom eting.")
        try:
            bot.edit_message_text("Bekor qilindi.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
        except Exception:
            pass
    elif call.data == "admin_remove_admin":
        if not is_primary_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Faqat asosiy admin o'chira oladi!")
            return
        msg = bot.send_message(call.message.chat.id, "🆔 O'chiriladigan admin ID ni yozing:")
        bot.register_next_step_handler(msg, admin_remove_admin_step)

    elif call.data == "admin_teacher_edit":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        kbd = InlineKeyboardMarkup(row_width=1)
        count = 0
        for k, t in teachers.items():
            cur = apply_teacher_override(k, t)
            nm = format_full_name(cur)
            price = cur.get("price")
            label = f"{nm} — {price}" if price else nm
            kbd.add(InlineKeyboardButton(label, callback_data=f"edit_base_teacher:{k}"))
            count += 1
        dbt = get_custom_teachers()
        for t in dbt:
            nm = t.get("name","")
            price = t.get("price")
            label = f"{nm} — {price}" if price else nm
            kbd.add(InlineKeyboardButton(label, callback_data=f"edit_custom_teacher:{t.get('id')}"))
            count += 1
        if count == 0:
            bot.edit_message_text("❌ O'qituvchilar ro'yxati bo'sh.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
        else:
            bot.edit_message_text("O'qituvchini tanlang:", call.message.chat.id, call.message.message_id, reply_markup=kbd)

    elif call.data.startswith("edit_base_teacher:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        key = call.data.split(":",1)[1]
        user_id = call.from_user.id
        base = teachers.get(key, {})
        cur = apply_teacher_override(key, base)
        nm = format_full_name(cur)
        info_text = (
            f"Hozirgi ma'lumotlar:\n"
            f"Ism/Familiya: {nm}\n"
            f"Fan: {cur.get('subject','')}\n"
            f"Ma'lumot:\n{cur.get('info','')}\n\n"
            f"Qaysi maydonni tahrirlaysiz? (Ism/Familiya/Fan/Ma'lumot)"
        )
        admin_edit_state[user_id] = {"key": key}
        msg = bot.send_message(call.message.chat.id, info_text)
        bot.register_next_step_handler(msg, teacher_edit_base_field_step)

    elif call.data.startswith("edit_custom_teacher:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        try:
            tid = int(call.data.split(":",1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "ID xato")
            return
        db = load_db()
        lst = db.get("teachers_custom", [])
        cur = None
        for t in lst:
            if t.get("id") == tid:
                cur = t
                break
        if not cur:
            bot.answer_callback_query(call.id, "Topilmadi")
            return
        info_text = (
            f"Hozirgi ma'lumotlar:\n"
            f"Ism: {cur.get('name','')}\n"
            f"Fan: {cur.get('subject','')}\n"
            f"Ma'lumot:\n{cur.get('info','')}\n\n"
            f"Qaysi maydonni tahrirlaysiz? (Ism/Fan/Ma'lumot)"
        )
        msg = bot.send_message(call.message.chat.id, info_text)
        bot.register_next_step_handler(msg, lambda m: teacher_edit_field_step(m, {"id": tid}))

    elif call.data == "admin_teacher_delete":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        dbt = get_custom_teachers()
        if not dbt:
            bot.edit_message_text("❌ Hozircha custom o'qituvchilar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{t['id']}: {t['name']} ({t.get('subject','')})" for t in dbt])
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun ID ni yozing:\n" + listing)
        bot.register_next_step_handler(msg, teacher_delete_step)
    
    elif call.data.startswith("confirm_delete_teacher:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        try:
            tid = int(call.data.split(":",1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "ID xato")
            return
        db = load_db()
        lst = db.get("teachers_custom", [])
        new_lst = [t for t in lst if t.get("id") != tid]
        if len(new_lst) == len(lst):
            bot.answer_callback_query(call.id, "Topilmadi")
            return
        db["teachers_custom"] = new_lst
        save_db(db)
        bot.edit_message_text("✅ O'qituvchi o'chirildi.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
    
    elif call.data == "cancel_delete_teacher":
        bot.edit_message_text("Bekor qilindi.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "admin_ariza_edit":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        arizalar = db.get("arizalar", [])
        if not arizalar:
            bot.edit_message_text("❌ Arizalar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{i+1}: {a.get('name')} ({a.get('subject')})" for i, a in enumerate(arizalar[:15])])
        msg = bot.send_message(call.message.chat.id, "Tahrirlash uchun indeksni yozing (1..N):\n" + listing)
        bot.register_next_step_handler(msg, ariza_edit_index_step)

    elif call.data == "admin_ariza_delete":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        arizalar = db.get("arizalar", [])
        if not arizalar:
            bot.edit_message_text("❌ Arizalar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{i+1}: {a.get('name')} ({a.get('subject')})" for i, a in enumerate(arizalar[:15])])
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun indeksni yozing (1..N):\n" + listing)
        bot.register_next_step_handler(msg, ariza_delete_index_step)

    elif call.data == "admin_ariza_notify":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        arizalar = db.get("arizalar", [])
        if not arizalar:
            bot.edit_message_text("❌ Arizalar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{i+1}: {a.get('name','')} — {a.get('subject','')}" for i, a in enumerate(arizalar[:20])])
        admin_notify_state[call.from_user.id] = {}
        msg = bot.send_message(call.message.chat.id, "Xabar yuborish uchun indeksni yozing (1..N):\n" + listing)
        bot.register_next_step_handler(msg, admin_ariza_notify_index_step)

    elif call.data == "admin_ariza_notify_subject":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        kbd = InlineKeyboardMarkup(row_width=1)
        for k, v in subjects.items():
            kbd.add(InlineKeyboardButton(v, callback_data=f"admin_ariza_notify_subject_select:{k}"))
        kbd.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_manage_data"))
        bot.edit_message_text("Fan tanlang:", call.message.chat.id, call.message.message_id, reply_markup=kbd)

    elif call.data.startswith("admin_ariza_notify_subject_select:"):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        subject_key = call.data.split(":",1)[1]
        admin_notify_state[call.from_user.id] = {"subject": subject_key}
        subject_name = subjects.get(subject_key, subject_key)
        msg = bot.send_message(call.message.chat.id, f"{subject_name}\nXabar matnini yozing (bo'sh — standart):")
        bot.register_next_step_handler(msg, admin_ariza_notify_subject_message_step)
    elif call.data == "admin_check_edit":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        checks = db.get("checks", [])
        if not checks:
            bot.edit_message_text("❌ Cheklar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{c.get('id')}: {c.get('name')} - {c.get('amount')}" for c in checks[:15]])
        msg = bot.send_message(call.message.chat.id, "Tahrirlash uchun chek ID ni yozing:\n" + listing)
        bot.register_next_step_handler(msg, check_edit_id_step)

    elif call.data == "admin_check_delete":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        checks = db.get("checks", [])
        if not checks:
            bot.edit_message_text("❌ Cheklar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{c.get('id')}: {c.get('name')} - {c.get('amount')}" for c in checks[:15]])
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun chek ID ni yozing:\n" + listing)
        bot.register_next_step_handler(msg, check_delete_id_step)

    elif call.data == "admin_subscriber_delete":
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Sizga ruxsat yo'q!")
            return
        subs = db.get("subscribers", [])
        if not subs:
            bot.edit_message_text("❌ Obunachilar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([str(s) for s in subs[:20]])
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun obunachi ID ni yozing:\n" + listing)
        bot.register_next_step_handler(msg, subscriber_delete_id_step)

    # Kursga yozilish arizasi
    elif call.data == "ariza_course":
        lang = get_user_lang(call.from_user.id)
        msg = bot.send_message(call.message.chat.id, localized_texts["ask_name"].get(lang, localized_texts["ask_name"]["O'zbek"]))
        bot.register_next_step_handler(msg, course_name)

    # Ishga kirish arizasi
    elif call.data == "ariza_job":
        lang = get_user_lang(call.from_user.id)
        msg = bot.send_message(call.message.chat.id, localized_texts["ask_name"].get(lang, localized_texts["ask_name"]["O'zbek"]))
        bot.register_next_step_handler(msg, job_name)

    # BACK
    elif call.data == "back":
        bot.answer_callback_query(call.id)
        lang = get_user_lang(call.from_user.id)
        try:
            bot.edit_message_text(
                localized_texts["welcome"].get(lang, localized_texts["welcome"]["O'zbek"]),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu_lang(lang)
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                localized_texts["welcome"].get(lang, localized_texts["welcome"]["O'zbek"]),
                reply_markup=main_menu_lang(lang)
            )
    
    # QUIZ
    elif call.data == "quiz":
        bot.answer_callback_query(call.id)
        markup = InlineKeyboardMarkup(row_width=1)
        for k in quiz_data.keys():
            markup.add(InlineKeyboardButton(quiz_data[k]["name"], callback_data=f"quiz:{k}"))
        uploads = get_quiz_uploads()
        for subj, qobj in uploads.items():
            name = qobj.get("name") or f"{subjects.get(subj, subj)} Test"
            markup.add(InlineKeyboardButton(name, callback_data=f"quiz:db:{subj}"))
        markup.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        lang = get_user_lang(call.from_user.id)
        bot.edit_message_text(
            localized_texts["quiz_which"].get(lang, localized_texts["quiz_which"]["O'zbek"]),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    # Quiz boshlash
    elif call.data.startswith("quiz:"):
        key = call.data.split(":", 1)[1]
        lang = get_user_lang(call.from_user.id)
        qobj = get_quiz(key)
        if not qobj:
            bot.answer_callback_query(call.id, "❌ Test topilmadi")
            return
        msg_text = localized_texts["quiz_started"].get(lang, localized_texts["quiz_started"]["O'zbek"]).format(name=qobj.get("name","Test"))
        bot.send_message(call.message.chat.id, msg_text)
        show_quiz_question(call.message.chat.id, key, 0, 0)
    
    # TEST
    elif call.data == "test":
        lang = get_user_lang(call.from_user.id)
        bot.send_message(
            call.message.chat.id,
            localized_texts["test_text"].get(lang, localized_texts["test_text"]["O'zbek"]),
            reply_markup=back_button()
        )
    
    # CHAT (new chat mode)
    elif call.data == "chat":
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        chat_mode[user_id] = True
        lang = get_user_lang(user_id)
        welcome = localized_texts["chat_prompt"].get(lang, localized_texts["chat_prompt"]["O'zbek"])
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Exit Chat", callback_data="exit_chat"))
        bot.send_message(chat_id, welcome, reply_markup=markup)
        bot.answer_callback_query(call.id)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
    
    elif call.data == "teacher_panel":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            msg = bot.send_message(call.message.chat.id, "Parolni kiriting:")
            bot.register_next_step_handler(msg, teacher_login_step)
            return
        show_teacher_panel(call.message.chat.id, user_id)

    elif call.data.startswith("teacher_bind_base:"):
        user_id = call.from_user.id
        key = call.data.split(":",1)[1]
        set_teacher_link(user_id, {"type": "base", "key": key, "subject": key})
        bot.edit_message_text("✅ Bog‘landi. Endi o‘qituvchi panelidan foydalanishingiz mumkin.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data.startswith("teacher_bind_custom:"):
        user_id = call.from_user.id
        try:
            tid = int(call.data.split(":",1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "ID xato")
            return
        dbt = get_custom_teachers()
        cur = None
        for t in dbt:
            if t.get("id") == tid:
                cur = t
                break
        if not cur:
            bot.answer_callback_query(call.id, "Topilmadi")
            return
        set_teacher_link(user_id, {"type": "custom", "id": tid, "subject": cur.get("subject")})
        bot.edit_message_text("✅ Bog‘landi. Endi o‘qituvchi panelidan foydalanishingiz mumkin.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "teacher_profile":
        user_id = call.from_user.id
        l = get_teacher_links().get(str(user_id))
        if not l:
            bot.answer_callback_query(call.id, "Bog‘lanmagan")
            return
        if l.get("type") == "base":
            key = l.get("key")
            cur = apply_teacher_override(key, teachers.get(key, {}))
            nm = format_full_name(cur)
            txt = f"👤 {nm}\n📂 {cur.get('subject','')}\n💰 {cur.get('price','')}\n\n{cur.get('info','')}"
        else:
            dbt = get_custom_teachers()
            cur = None
            for t in dbt:
                if t.get("id") == l.get("id"):
                    cur = t
                    break
            nm = cur.get("name","") if cur else ""
            txt = f"👤 {nm}\n📂 {cur.get('subject','') if cur else ''}\n💰 {cur.get('price','') if cur else ''}\n\n{cur.get('info','') if cur else ''}"
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "teacher_self_edit":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Bog‘lanmagan")
            return
        msg = bot.send_message(call.message.chat.id, "Qaysi maydonni tahrirlaysiz? (Ism/Familiya/Fan/Ma'lumot/To'lov)")
        bot.register_next_step_handler(msg, teacher_self_edit_field_step)

    elif call.data == "teacher_self_test":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Bog‘lanmagan")
            return
        subj = get_teacher_subject_for_user(user_id)
        if not subj:
            kbd = InlineKeyboardMarkup(row_width=1)
            for k, v in subjects.items():
                kbd.add(InlineKeyboardButton(v, callback_data=f"tp_set_subject:{k}"))
            bot.edit_message_text("Fan tanlang:", call.message.chat.id, call.message.message_id, reply_markup=kbd)
            return
        admin_test_state[user_id] = {"subject": subj}
        msg = bot.send_message(call.message.chat.id, "PDF yoki TXT faylini yuboring (savollar: bir bo‘limda savol, keyin 1) 2) ..., va Correct: n).")
        bot.register_next_step_handler(msg, admin_test_receive_file)

    elif call.data.startswith("tp_set_subject:"):
        user_id = call.from_user.id
        subj = call.data.split(":",1)[1]
        set_teacher_link(user_id, {"type": "manual", "subject": subj})
        bot.edit_message_text("✅ Fan saqlandi.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "tp_students":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        subj = get_teacher_subject_for_user(user_id)
        db = load_db()
        lst = db.get("arizalar", [])
        studs = [a for a in lst if a.get("subject") == subj and a.get("user_id")]
        count = len(studs)
        preview = "\n".join([f"{a.get('name','?')} — {a.get('phone','?')}" for a in studs[:15]]) or "Yo'q"
        bot.edit_message_text(f"👨‍🎓 Talabalar: {count}\n\n{preview}", call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "tp_stats":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        subj = get_teacher_subject_for_user(user_id)
        db = load_db()
        studs = [a for a in db.get("arizalar", []) if a.get("subject") == subj and a.get("user_id")]
        results = [r for r in db.get("quiz_results", []) if r.get("subject") == subj]
        avg = 0
        if results:
            avg = sum(r.get("score",0)/max(1,r.get("total",1)) for r in results)/len(results)*100
        msg = f"📊 Statistika\nFan: {subj}\nTalabalar: {len(studs)}\nTestlar: {len(results)}\nO'rtacha ball: {avg:.1f}%"
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=back_button())

    elif call.data == "tp_homework":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        msg = bot.send_message(call.message.chat.id, "Uy vazifani yozing yoki fayl yuboring:")
        bot.register_next_step_handler(msg, teacher_homework_receive)

    elif call.data == "tp_announce":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        msg = bot.send_message(call.message.chat.id, "E'lon matnini yozing:")
        bot.register_next_step_handler(msg, teacher_announce_step)

    elif call.data == "tp_materials":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        m = InlineKeyboardMarkup(row_width=2)
        m.add(
            InlineKeyboardButton("➕ Qo'shish", callback_data="tp_material_add"),
            InlineKeyboardButton("🗂 Ro'yxat/O'chirish", callback_data="tp_material_list")
        )
        bot.edit_message_text("Materiallar", call.message.chat.id, call.message.message_id, reply_markup=m)

    elif call.data == "tp_material_add":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        msg = bot.send_message(call.message.chat.id, "Matn, link yoki fayl yuboring:")
        bot.register_next_step_handler(msg, teacher_material_add_step)

    elif call.data == "tp_material_list":
        user_id = call.from_user.id
        if user_id not in teacher_sessions:
            bot.answer_callback_query(call.id, "Ruxsat yo'q")
            return
        db = load_db()
        mats = db.get("teacher_materials", {}).get(str(user_id), [])
        if not mats:
            bot.edit_message_text("Materiallar yo'q.", call.message.chat.id, call.message.message_id, reply_markup=back_button())
            return
        listing = "\n".join([f"{i+1}: {m.get('title','Material')}" for i, m in enumerate(mats[:20])])
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun indeksni yozing:\n" + listing)
        bot.register_next_step_handler(msg, teacher_material_delete_index_step)

    # TEACHER SEARCH
    elif call.data == "search_teacher":
        msg = bot.send_message(
            call.message.chat.id,
            "🔍 O'qituvchi izlovchi\n\nO'qituvchi ismini yozing:",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(msg, handle_teacher_search)
    
    # CHECK/PAYMENT RECEIPT
    elif call.data == "check":
        lang = get_user_lang(call.from_user.id)
        ask_name = {
            "O'zbek": "👤 Ismingizni yozing:",
            "English": "👤 Enter your name:",
            "Русский": "👤 Напишите ваше имя:"
        }
        msg = bot.send_message(call.message.chat.id, ask_name.get(lang, ask_name["O'zbek"]))
        bot.register_next_step_handler(msg, check_name)

    # ARIZA CONFIRMATIONS
    elif call.data == "ariza_confirm_name_yes":
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        if user_id in user_form_state:
            # Kontakt ulashish tugmasi
            phone_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            share_btn_text = {
                "O'zbek": "📱 Telefon raqamni ulashish",
                "English": "📱 Share phone number",
                "Русский": "📱 Поделиться номером"
            }
            phone_markup.add(KeyboardButton(
                share_btn_text.get(lang, share_btn_text["O'zbek"]),
                request_contact=True
            ))
            ask_phone_text = {
                "O'zbek": "📞 Telefon raqamingizni yozing yoki tugmani bosing:",
                "English": "📞 Enter your phone number or press the button:",
                "Русский": "📞 Введите номер телефона или нажмите кнопку:"
            }
            msg = bot.send_message(
                call.message.chat.id,
                ask_phone_text.get(lang, ask_phone_text["O'zbek"]),
                reply_markup=phone_markup
            )
            form_type = user_form_state[user_id]["type"]
            if form_type == "kurs":
                bot.register_next_step_handler(msg, lambda m: course_phone(m, user_form_state[user_id]["name"]))
            else:
                bot.register_next_step_handler(msg, lambda m: job_phone(m, user_form_state[user_id]["name"]))
    
    elif call.data == "ariza_confirm_name_no":
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        msg = bot.send_message(call.message.chat.id, "❌ Xato! Iltimos ismingizni qayta yozing:")
        form_type = user_form_state.get(user_id, {}).get("type", "kurs")
        if form_type == "kurs":
            bot.register_next_step_handler(msg, course_name)
        else:
            bot.register_next_step_handler(msg, job_name)
    
    elif call.data == "ariza_confirm_phone_yes":
        user_id = call.from_user.id
        if user_id in user_form_state:
            show_subject_selection(call.message.chat.id, user_id)
    
    elif call.data == "ariza_confirm_phone_no":
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        msg = bot.send_message(call.message.chat.id, "❌ Xato! Iltimos telefon raqamini qayta yozing:")
        form_type = user_form_state.get(user_id, {}).get("type", "kurs")
        name = user_form_state.get(user_id, {}).get("name", "")
        if form_type == "kurs":
            bot.register_next_step_handler(msg, lambda m: course_phone(m, name))
        else:
            bot.register_next_step_handler(msg, lambda m: job_phone(m, name))
    
    elif call.data.startswith("ariza_subject:"):
        subject_key = call.data.split(":", 1)[1]
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        
        if user_id in user_form_state:
            user_form_state[user_id]["subject"] = subject_key
            confirm_final = InlineKeyboardMarkup()
            confirm_final.add(
                InlineKeyboardButton("✅ Ha", callback_data="ariza_submit_yes"),
                InlineKeyboardButton("❌ Yo'q", callback_data="ariza_submit_no")
            )
            subject_name = subjects.get(subject_key, subject_key)
            bot.send_message(call.message.chat.id, f"{subject_name} - Ariza yuborilsinmi?", reply_markup=confirm_final)
    
    elif call.data == "ariza_submit_yes":
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        
        if user_id in user_form_state:
            form = user_form_state[user_id]
            db = load_db()
            if "arizalar" not in db:
                db["arizalar"] = []
            
            ariza = {
                "type": form.get("type", "kurs"),
                "name": form.get("name"),
                "phone": form.get("phone"),
                "subject": form.get("subject"),
                "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M"),
            "status": "yangi",
            "user_id": int(user_id)
            }
            db["arizalar"].append(ariza)
            save_db(db)
            
            bot.send_message(call.message.chat.id, "✅ Ariza muvaffaqiyatli yuborildi!", reply_markup=main_menu_lang(lang))
            
            subject_name = subjects.get(form.get("subject"), form.get("subject"))
            admin_text = f"📩 Yangi ariza:\n👤 {form.get('name')}\n📞 {form.get('phone')}\n📚 {subject_name}\n🕒 {ariza['time']}"
            for admin in all_admins():
                try:
                    bot.send_message(admin, admin_text)
                except Exception:
                    pass
            
            del user_form_state[user_id]
    
    elif call.data == "ariza_submit_no":
        user_id = call.from_user.id
        lang = get_user_lang(user_id)
        bot.send_message(call.message.chat.id, "Bekor qilindi.", reply_markup=main_menu_lang(lang))
        if user_id in user_form_state:
            del user_form_state[user_id]

# --- QUIZ HANDLERS ---
def show_quiz_question(chat_id, quiz_key, question_idx, score):
    qobj = get_quiz(quiz_key)
    if not qobj:
        return
    questions = qobj.get("questions", [])
    if question_idx >= len(questions):
        db = load_db()
        res = db.get("quiz_results", [])
        total = len(questions)
        subj = quiz_key.split(":",1)[1] if quiz_key.startswith("db:") else quiz_key
        res.append({
            "user_id": int(chat_id),
            "quiz_key": quiz_key,
            "subject": subj,
            "score": int(score),
            "total": int(total),
            "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")
        })
        db["quiz_results"] = res
        save_db(db)
        bot.send_message(chat_id, f"🎉 Quiz tugadi!\n\nSizning ballangiz: {score}/{total}\n\n{(score/total)*100:.0f}%")
        return
    
    q = questions[question_idx]
    markup = InlineKeyboardMarkup(row_width=1)
    
    for idx, option in enumerate(q["options"]):
        callback_data = f"answer:{quiz_key}:{question_idx}:{idx}:{score}"
        markup.add(InlineKeyboardButton(option, callback_data=callback_data))
    
    user_quiz_state[chat_id] = {"quiz_key": quiz_key, "question_idx": question_idx, "score": score}
    quiz_question_time[chat_id] = datetime.now(TASHKENT_TZ)  # Record when question was shown
    
    msg = f"Savol {question_idx + 1}/{len(questions)}:\n\n⏱️ Vaqt: {QUIZ_TIME_LIMIT} soniya\n\n{q['q']}"
    bot.send_message(chat_id, msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def handle_quiz_answer(call):
    parts = call.data.split(":")
    quiz_key = parts[1]
    question_idx = int(parts[2])
    selected = int(parts[3])
    score = int(parts[4])
    
    qobj = get_quiz(quiz_key)
    if not qobj:
        return
    
    # Vaqt chegarasi tekshirish
    chat_id = call.message.chat.id
    if chat_id not in quiz_question_time:
        show_quiz_question(chat_id, quiz_key, question_idx + 1, score)
        return
    
    time_elapsed = (datetime.now(TASHKENT_TZ) - quiz_question_time[chat_id]).total_seconds()
    
    if time_elapsed > QUIZ_TIME_LIMIT:
        # Vaqt tugadi
        questions = qobj.get("questions", [])
        if question_idx < len(questions):
            q = questions[question_idx]
            bot.send_message(call.message.chat.id, f"⏱️ Vaqt tugadi! To'g'ri javob: {q['options'][q['correct']]}")
        bot.send_message(call.message.chat.id, f"⏱️ Vaqt tugadi! To'g'ri javob: {q['options'][q['correct']]}")
        show_quiz_question(call.message.chat.id, quiz_key, question_idx + 1, score)
        return
    
    questions = qobj.get("questions", [])
    if question_idx >= len(questions):
        return
    q = questions[question_idx]
    is_correct = selected == q["correct"]
    
    if is_correct:
        score += 1
        bot.send_message(call.message.chat.id, f"✅ To'g'ri! ({time_elapsed:.1f}s)")
    else:
        bot.send_message(call.message.chat.id, f"❌ Noto'g'ri. To'g'ri javob: {q['options'][q['correct']]}")
    
    show_quiz_question(call.message.chat.id, quiz_key, question_idx + 1, score)

def admin_test_receive_file(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "❌ Sizga ruxsat yo'q!", reply_markup=back_button())
        return
    st = admin_test_state.get(user_id, {})
    subj = st.get("subject")
    if not subj:
        bot.send_message(message.chat.id, "❌ Fan tanlanmagan.", reply_markup=back_button())
        return
    if not getattr(message, "document", None):
        msg = bot.send_message(message.chat.id, "❌ Iltimos, PDF yoki TXT faylini yuboring:")
        bot.register_next_step_handler(msg, admin_test_receive_file)
        return
    file_name = message.document.file_name or ""
    file_id = message.document.file_id
    ext = file_name.lower().split(".")[-1] if "." in file_name else ""
    try:
        data = download_telegram_file(file_id)
    except Exception:
        bot.send_message(message.chat.id, "❌ Faylni yuklab bo'lmadi.", reply_markup=back_button())
        return
    text = None
    if ext == "txt":
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = data.decode("latin-1", errors="ignore")
    elif ext == "pdf":
        try:
            import PyPDF2  # type: ignore
            from io import BytesIO
            reader = PyPDF2.PdfReader(BytesIO(data))
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            text = "\n".join(pages)
        except Exception:
            bot.send_message(message.chat.id, "❌ PDF o‘qish uchun kutubxona topilmadi yoki xato yuz berdi. Iltimos TXT yuboring.", reply_markup=back_button())
            return
    else:
        msg = bot.send_message(message.chat.id, "❌ Faqat PDF yoki TXT qabul qilinadi. Qayta yuboring:")
        bot.register_next_step_handler(msg, admin_test_receive_file)
        return
    questions = parse_test_text(text or "")
    if not questions:
        bot.send_message(message.chat.id, "❌ Savollar topilmadi. Formatni tekshiring.", reply_markup=back_button())
        return
    name = f"{subjects.get(subj, subj)} Test"
    set_quiz_upload(subj, {"name": name, "questions": questions})
    kbd = InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Testni boshlash", callback_data=f"quiz:db:{subj}"))
    bot.send_message(message.chat.id, f"✅ {len(questions)} ta savol yuklandi.", reply_markup=kbd)

# --- LANGUAGE SELECTION HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("lang:"))
def handle_language_choice(call):
    language = call.data.split(":", 1)[1]
    user_id = call.from_user.id
    user_languages[user_id] = language
    
    lang_flags = {
        "O'zbek": "🇺🇿",
        "English": "🇬🇧",
        "Русский": "🇷🇺",
        "Turkish": "🇹🇷",
        "한국어": "🇰🇷",
        "العربية": "🇸🇦",
        "中文": "🇨🇳",
        "日本語": "🇯🇵"
    }
    
    # Language-specific messages
    lang_messages = {
        "O'zbek": "🇺🇿 O'zbek tili tanlandi!",
        "English": "🇬🇧 English language selected!",
        "Русский": "🇷🇺 Русский язык выбран!",
        "Turkish": "🇹🇷 Türkçe seçildi!",
        "한국어": "🇰🇷 한국어가 선택되었습니다!",
        "العربية": "🇸🇦 تم اختيار اللغة العربية!",
        "中文": "🇨🇳 已选择中文！",
        "日本語": "🇯🇵 日本語が選択されました！"
    }
    
    # Save to DB
    db = load_db()
    if "user_languages" not in db:
        db["user_languages"] = {}
    db["user_languages"][str(user_id)] = language
    save_db(db)
    
    bot.send_message(
        call.message.chat.id,
        lang_messages.get(language, lang_messages["O'zbek"]),
        reply_markup=main_menu_lang(language)
    )

# --- ARIZALAR FORM FLOW ---
def course_name(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    name = message.text.strip()
    
    user_form_state[user_id] = {"type": "kurs", "name": name}
    
    # Ask for confirmation
    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_name_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_name_no")
    )
    bot.send_message(message.chat.id, f"✅ Ismingiz: {name} — to'g'rimi?", reply_markup=confirm_markup)

def job_name(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    name = message.text.strip()
    
    user_form_state[user_id] = {"type": "ish", "name": name}
    
    # Ask for confirmation
    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_name_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_name_no")
    )
    bot.send_message(message.chat.id, f"✅ Ismingiz: {name} — to'g'rimi?", reply_markup=confirm_markup)

def course_phone(message, name):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)

    # Kontakt ulashilgan bo'lsa
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        phone = message.text.strip()
    else:
        msg = bot.send_message(message.chat.id, "❌ Telefon raqamni yozing yoki tugmani bosing:")
        bot.register_next_step_handler(msg, lambda m: course_phone(m, name))
        return

    # Klaviaturani yopamiz
    bot.send_message(message.chat.id, "✅", reply_markup=ReplyKeyboardRemove())

    if user_id in user_form_state:
        user_form_state[user_id]["phone"] = phone
        if user_form_state[user_id].get("strict_phone"):
            if phone != "907877157":
                msg = bot.send_message(message.chat.id, "❌ Telefon raqam noto'g'ri. Iltimos 907877157 ni kiriting:")
                bot.register_next_step_handler(msg, lambda m: course_phone(m, name))
                return

    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_phone_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_phone_no")
    )
    bot.send_message(message.chat.id, f"📞 Telefon: {phone} — to'g'rimi?", reply_markup=confirm_markup)

def job_phone(message, name):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)

    # Kontakt ulashilgan bo'lsa
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        phone = message.text.strip()
    else:
        msg = bot.send_message(message.chat.id, "❌ Telefon raqamni yozing yoki tugmani bosing:")
        bot.register_next_step_handler(msg, lambda m: job_phone(m, name))
        return

    # Klaviaturani yopamiz
    bot.send_message(message.chat.id, "✅", reply_markup=ReplyKeyboardRemove())

    if user_id in user_form_state:
        user_form_state[user_id]["phone"] = phone

    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_phone_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_phone_no")
    )
    bot.send_message(message.chat.id, f"📞 Telefon: {phone} — to'g'rimi?", reply_markup=confirm_markup)

def show_subject_selection(chat_id, user_id):
    lang = get_user_lang(user_id)
    markup = InlineKeyboardMarkup(row_width=1)
    for k, v in subjects.items():
        markup.add(InlineKeyboardButton(v, callback_data=f"ariza_subject:{k}"))
    bot.send_message(chat_id, "📚 Qaysi fanni tanlaysiz?", reply_markup=markup)

# --- TEACHER SEARCH HANDLER ---
def handle_teacher_search(message):
    search_name = message.text.lower()
    
    # Teachers'ni izlash
    found_teachers = []
    for key, teacher in teachers.items():
        t = apply_teacher_override(key, teacher)
        name_surname = (t.get("name","") + (" " + t.get("surname","") if t.get("surname") else "")).strip()
        subj = t.get("subject","")
        info = t.get("bio","") or t.get("info","")
        if search_name in name_surname.lower() or search_name in subj.lower() or (info and search_name in info.lower()):
            found_teachers.append((key, t))
    for t in get_custom_teachers():
        if search_name in t["name"].lower():
            found_teachers.append((f"custom_{t.get('id','0')}", t))
    
    if found_teachers:
        response = "🎓 Topilgan o'qituvchilar:\n\n"
        for key, teacher in found_teachers:
            nm = (teacher.get("name","") + (" " + teacher.get("surname","") if teacher.get("surname") else "")).strip()
            info = teacher.get("info") or f"👤 {nm}\n📂 {teacher.get('subject','')}"
            response += info + "\n" + "=" * 40 + "\n"
        bot.send_message(message.chat.id, response, reply_markup=back_button())
    else:
        bot.send_message(
            message.chat.id,
            f"❌ '{search_name}' nomli o'qituvchi topilmadi.\n\nBiz quyidagi o'qituvchilarni taklif qilamiz:\n" + 
            "\n".join([f"👤 {(apply_teacher_override(k, t).get('name','') + (' ' + apply_teacher_override(k, t).get('surname','') if apply_teacher_override(k, t).get('surname') else '')).strip()}" for k, t in teachers.items()] + [f"👤 {t['name']}" for t in get_custom_teachers()]),
            reply_markup=back_button()
        )

def get_custom_teachers():
    db = load_db()
    return db.get("teachers_custom", [])

def get_teacher_overrides():
    db = load_db()
    return db.get("teachers_overrides", {})

def apply_teacher_override(key, base):
    ov = get_teacher_overrides()
    o = ov.get(key, {})
    m = dict(base)
    for k in ["name", "surname", "subject", "info", "price"]:
        if k in o:
            m[k] = o[k]
    return m

def set_teacher_override_field(key, field, value):
    db = load_db()
    ov = db.get("teachers_overrides", {})
    cur = ov.get(key, {})
    cur[field] = value
    ov[key] = cur
    db["teachers_overrides"] = ov
    save_db(db)

def format_full_name(t):
    nm = (t.get("name","") + (" " + t.get("surname","") if t.get("surname") else "")).strip()
    return nm

def teacher_add_name_step(message):
    name = (message.text or "").strip()
    if not name:
        msg = bot.send_message(message.chat.id, "Ism yozing:")
        bot.register_next_step_handler(msg, teacher_add_name_step)
        return
    s = {"name": name}
    msg = bot.send_message(message.chat.id, "Fan nomini yozing:")
    bot.register_next_step_handler(msg, lambda m: teacher_add_subject_step(m, s))

def teacher_add_subject_step(message, state):
    subject = (message.text or "").strip()
    if not subject:
        msg = bot.send_message(message.chat.id, "Fan nomini yozing:")
        bot.register_next_step_handler(msg, lambda m: teacher_add_subject_step(m, state))
        return
    state["subject"] = subject
    msg = bot.send_message(message.chat.id, "O'qituvchi haqida qisqacha ma'lumot yozing:")
    bot.register_next_step_handler(msg, lambda m: teacher_add_info_step(m, state))

def teacher_add_info_step(message, state):
    info = (message.text or "").strip()
    db = load_db()
    lst = db.get("teachers_custom", [])
    tid = (lst[-1]["id"] + 1) if lst else 1
    entry = {"id": tid, "name": state.get("name"), "subject": state.get("subject"), "info": info}
    lst.append(entry)
    db["teachers_custom"] = lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ O'qituvchi qo'shildi.", reply_markup=back_button())

def admin_add_admin_step(message):
    text = (message.text or "").strip()
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "❌ Sizga ruxsat yo'q!", reply_markup=back_button())
        return
    try:
        new_admin_id = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Iltimos raqam kiriting:")
        bot.register_next_step_handler(msg, admin_add_admin_step)
        return
    add_admin(new_admin_id)
    bot.send_message(message.chat.id, f"✅ Admin qo'shildi: {new_admin_id}", reply_markup=back_button())
    for a in all_admins():
        if a != user_id:
            try:
                bot.send_message(a, f"🆕 Yangi admin qo'shildi: {new_admin_id}")
            except Exception:
                pass

def admin_broadcast_step(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "❌ Sizga ruxsat yo'q!", reply_markup=back_button())
        return
    text = (message.text or "").strip()
    if not text:
        msg = bot.send_message(message.chat.id, "❌ Matn bo'sh. Qayta yozing:")
        bot.register_next_step_handler(msg, admin_broadcast_step)
        return
    db = load_db()
    subs = db.get("subscribers", [])
    sent = 0
    for sid in subs:
        try:
            bot.send_message(int(sid), text)
            sent += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"📢 E'lon {sent} obunachiga yuborildi.", reply_markup=back_button())

def admin_remove_admin_step(message):
    user_id = message.from_user.id
    if not is_primary_admin(user_id):
        bot.send_message(message.chat.id, "❌ Faqat asosiy admin o'chira oladi.", reply_markup=back_button())
        return
    text = (message.text or "").strip()
    try:
        rm_id = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, admin_remove_admin_step)
        return
    if rm_id in set(ADMINS):
        bot.send_message(message.chat.id, "❌ Asosiy adminni o'chirib bo'lmaydi.", reply_markup=back_button())
        return
    db = load_db()
    admins = set(db.get("admins", []))
    if rm_id not in admins:
        bot.send_message(message.chat.id, "❌ Bu ID bazadagi adminlar orasida yo'q.", reply_markup=back_button())
        return
    admins.discard(rm_id)
    db["admins"] = list(admins)
    save_db(db)
    bot.send_message(message.chat.id, f"✅ Admin o'chirildi: {rm_id}", reply_markup=back_button())

def admin_ariza_notify_index_step(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    try:
        idx = int(text) - 1
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Indeks noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, admin_ariza_notify_index_step)
        return
    db = load_db()
    lst = db.get("arizalar", [])
    if idx < 0 or idx >= len(lst):
        msg = bot.send_message(message.chat.id, "❌ Indeks chegaradan tashqarida. Qayta kiriting:")
        bot.register_next_step_handler(msg, admin_ariza_notify_index_step)
        return
    ariza = lst[idx]
    admin_notify_state[user_id] = {"idx": idx}
    subject_name = subjects.get(ariza.get("subject"), ariza.get("subject",""))
    default_msg = f"Sizning {subject_name} kursingiz ochildi. Aloqa uchun ushbu xabarni javob bering."
    msg = bot.send_message(message.chat.id, "Xabar matnini yozing (yoki bo'sh qoldiring — standart xabar yuboriladi):")
    bot.register_next_step_handler(msg, admin_ariza_notify_message_step)

def admin_ariza_notify_message_step(message):
    admin_id = message.from_user.id
    st = admin_notify_state.get(admin_id, {})
    db = load_db()
    lst = db.get("arizalar", [])
    idx = st.get("idx")
    if idx is None or idx < 0 or idx >= len(lst):
        bot.send_message(message.chat.id, "❌ Xato. Qayta urinib ko'ring.", reply_markup=back_button())
        return
    ariza = lst[idx]
    subject_name = subjects.get(ariza.get("subject"), ariza.get("subject",""))
    text_in = (message.text or "").strip()
    notify_text = text_in or f"Sizning {subject_name} kursingiz ochildi. Aloqa uchun ushbu xabarni javob bering."
    uid = ariza.get("user_id")
    if not uid:
        bot.send_message(message.chat.id, "❌ Bu arizada user_id saqlanmagan, xabar yuborib bo'lmaydi.", reply_markup=back_button())
        return
    try:
        bot.send_message(int(uid), notify_text)
        bot.send_message(message.chat.id, "✅ Xabar yuborildi.", reply_markup=back_button())
    except Exception:
        bot.send_message(message.chat.id, "❌ Xabar yuborishda xato.", reply_markup=back_button())

def admin_ariza_notify_subject_message_step(message):
    admin_id = message.from_user.id
    st = admin_notify_state.get(admin_id, {})
    subject_key = st.get("subject")
    if not subject_key:
        bot.send_message(message.chat.id, "❌ Xato. Qayta urinib ko'ring.", reply_markup=back_button())
        return
    db = load_db()
    lst = db.get("arizalar", [])
    subject_name = subjects.get(subject_key, subject_key)
    text_in = (message.text or "").strip()
    notify_text = text_in or f"Sizning {subject_name} kursingiz ochildi. Aloqa uchun ushbu xabarni javob bering."
    sent = 0
    for a in lst:
        if a.get("subject") == subject_key and a.get("user_id"):
            try:
                bot.send_message(int(a["user_id"]), notify_text)
                sent += 1
            except Exception:
                pass
    bot.send_message(message.chat.id, f"✅ Xabar {sent} arizachiga yuborildi.", reply_markup=back_button())

def teacher_homework_receive(message):
    user_id = message.from_user.id
    if user_id not in teacher_sessions:
        bot.send_message(message.chat.id, "Ruxsat yo'q.", reply_markup=back_button())
        return
    db = load_db()
    hw = db.get("teacher_homeworks", {})
    arr = hw.get(str(user_id), [])
    if getattr(message, "document", None):
        arr.append({"type": "file", "file_id": message.document.file_id, "file_name": message.document.file_name, "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")})
    else:
        text = (message.text or "").strip()
        arr.append({"type": "text", "text": text, "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")})
    hw[str(user_id)] = arr
    db["teacher_homeworks"] = hw
    save_db(db)
    bot.send_message(message.chat.id, "✅ Uy vazifa saqlandi.", reply_markup=back_button())

def teacher_announce_step(message):
    user_id = message.from_user.id
    if user_id not in teacher_sessions:
        bot.send_message(message.chat.id, "Ruxsat yo'q.", reply_markup=back_button())
        return
    text = (message.text or "").strip()
    subj = get_teacher_subject_for_user(user_id)
    db = load_db()
    lst = db.get("arizalar", [])
    sent = 0
    for a in lst:
        if a.get("subject") == subj and a.get("user_id"):
            try:
                bot.send_message(int(a["user_id"]), text)
                sent += 1
            except Exception:
                pass
    bot.send_message(message.chat.id, f"✅ E'lon {sent} talaba(ga) yuborildi.", reply_markup=back_button())

def teacher_material_add_step(message):
    user_id = message.from_user.id
    if user_id not in teacher_sessions:
        bot.send_message(message.chat.id, "Ruxsat yo'q.", reply_markup=back_button())
        return
    db = load_db()
    mats = db.get("teacher_materials", {})
    arr = mats.get(str(user_id), [])
    if getattr(message, "document", None):
        arr.append({"type": "file", "file_id": message.document.file_id, "file_name": message.document.file_name, "title": message.document.file_name, "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")})
    else:
        text = (message.text or "").strip()
        title = text[:40] + ("..." if len(text) > 40 else "")
        arr.append({"type": "text", "text": text, "title": title, "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")})
    mats[str(user_id)] = arr
    db["teacher_materials"] = mats
    save_db(db)
    bot.send_message(message.chat.id, "✅ Material saqlandi.", reply_markup=back_button())

def teacher_material_delete_index_step(message):
    user_id = message.from_user.id
    if user_id not in teacher_sessions:
        bot.send_message(message.chat.id, "Ruxsat yo'q.", reply_markup=back_button())
        return
    text = (message.text or "").strip()
    try:
        idx = int(text) - 1
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Indeks xato. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_material_delete_index_step)
        return
    db = load_db()
    mats = db.get("teacher_materials", {})
    arr = mats.get(str(user_id), [])
    if idx < 0 or idx >= len(arr):
        msg = bot.send_message(message.chat.id, "❌ Indeks chegaradan tashqarida. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_material_delete_index_step)
        return
    arr.pop(idx)
    mats[str(user_id)] = arr
    db["teacher_materials"] = mats
    save_db(db)
    bot.send_message(message.chat.id, "✅ O'chirildi.", reply_markup=back_button())

def teacher_edit_id_step(message):
    text = (message.text or "").strip()
    try:
        tid = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_edit_id_step)
        return
    db = load_db()
    lst = db.get("teachers_custom", [])
    match = None
    for t in lst:
        if t.get("id") == tid:
            match = t
            break
    if not match:
        msg = bot.send_message(message.chat.id, "❌ Topilmadi. Qayta ID kiriting:")
        bot.register_next_step_handler(msg, teacher_edit_id_step)
        return
    s = {"id": tid}
    cur = match
    info_text = (
        f"Hozirgi ma'lumotlar:\n"
        f"Ism: {cur.get('name','')}\n"
        f"Fan: {cur.get('subject','')}\n"
        f"To'lov: {cur.get('price','')}\n"
        f"Ma'lumot:\n{cur.get('info','')}\n\n"
        f"Qaysi maydonni tahrirlaysiz? (Ism/Fan/Ma'lumot/To'lov)"
    )
    msg = bot.send_message(message.chat.id, info_text)
    bot.register_next_step_handler(msg, lambda m: teacher_edit_field_step(m, s))

def teacher_edit_field_step(message, state):
    field_in = (message.text or "").strip().lower()
    mapping = {
        "ism": "name",
        "familiya": "surname",
        "fan": "subject",
        "ma'lumot": "info",
        "malumot": "info",
        "to'lov": "price",
        "tolov": "price",
        "name": "name",
        "subject": "subject",
        "info": "info",
        "surname": "surname",
        "price": "price"
    }
    field = mapping.get(field_in)
    if not field:
        msg = bot.send_message(message.chat.id, "❌ Noto'g'ri tanlov. (Ism/Familiya/Fan/Ma'lumot/To'lov)")
        bot.register_next_step_handler(msg, lambda m: teacher_edit_field_step(m, state))
        return
    state["field"] = field
    msg = bot.send_message(message.chat.id, "Yangi qiymatni yozing:")
    bot.register_next_step_handler(msg, lambda m: teacher_edit_apply_step(m, state))

def teacher_edit_apply_step(message, state):
    value = (message.text or "").strip()
    db = load_db()
    lst = db.get("teachers_custom", [])
    for t in lst:
        if t.get("id") == state.get("id"):
            t[state.get("field")] = value
            break
    db["teachers_custom"] = lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ O'zgarish saqlandi.", reply_markup=back_button())

def teacher_self_edit_field_step(message):
    user_id = message.from_user.id
    l = get_teacher_links().get(str(user_id))
    field_in = (message.text or "").strip().lower()
    mapping = {
        "ism": "name",
        "familiya": "surname",
        "fan": "subject",
        "ma'lumot": "info",
        "malumot": "info",
        "to'lov": "price",
        "tolov": "price",
        "name": "name",
        "subject": "subject",
        "info": "info",
        "surname": "surname",
        "price": "price"
    }
    field = mapping.get(field_in)
    if not field:
        msg = bot.send_message(message.chat.id, "❌ Noto'g'ri tanlov. (Ism/Familiya/Fan/Ma'lumot/To'lov)")
        bot.register_next_step_handler(msg, teacher_self_edit_field_step)
        return
    if not l:
        bot.send_message(message.chat.id, "❌ Bog‘lanmagan.", reply_markup=back_button())
        return
    bot.send_message(message.chat.id, "Yangi qiymatni yozing:")
    bot.register_next_step_handler(message, lambda m: teacher_self_edit_apply_step(m, l, field))

def teacher_self_edit_apply_step(message, link, field):
    user_id = message.from_user.id
    value = (message.text or "").strip()
    if link.get("type") == "base":
        key = link.get("key")
        set_teacher_override_field(key, field, value)
        bot.send_message(message.chat.id, "✅ O'zgarish saqlandi.", reply_markup=back_button())
    else:
        db = load_db()
        lst = db.get("teachers_custom", [])
        for t in lst:
            if t.get("id") == link.get("id"):
                t[field] = value
                break
        db["teachers_custom"] = lst
        save_db(db)
        bot.send_message(message.chat.id, "✅ O'zgarish saqlandi.", reply_markup=back_button())

def teacher_login_step(message):
    user_id = message.from_user.id
    pwd = (message.text or "").strip()
    ref = find_teacher_ref_by_password(pwd)
    if ref:
        # Auto-bind this user to the teacher ref
        kind, val = ref.split(":", 1)
        if kind == "base":
            set_teacher_link(user_id, {"type": "base", "key": val, "subject": val})
        elif kind == "custom":
            try:
                tid = int(val)
            except Exception:
                tid = None
            set_teacher_link(user_id, {"type": "custom", "id": tid})
        teacher_sessions.add(user_id)
        show_teacher_panel(message.chat.id, user_id)
        return
    # Fallback to global teacher password if configured
    if TEACHER_PASSWORD and pwd == TEACHER_PASSWORD:
        teacher_sessions.add(user_id)
        subj = get_teacher_subject_for_user(user_id)
        if not subj:
            kbd = InlineKeyboardMarkup(row_width=1)
            for k, v in subjects.items():
                kbd.add(InlineKeyboardButton(v, callback_data=f"tp_set_subject:{k}"))
            bot.send_message(message.chat.id, "Fan tanlang:", reply_markup=kbd)
            return
        show_teacher_panel(message.chat.id, user_id)
        return
    msg = bot.send_message(message.chat.id, "❌ Parol xato. Qayta kiriting:")
    bot.register_next_step_handler(msg, teacher_login_step)

def show_teacher_panel(chat_id, user_id):
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("👨‍🎓 Talabalar", callback_data="tp_students"),
        InlineKeyboardButton("📊 Statistika", callback_data="tp_stats")
    )
    m.add(
        InlineKeyboardButton("📝 Uy vazifa", callback_data="tp_homework"),
        InlineKeyboardButton("📢 E'lon", callback_data="tp_announce")
    )
    m.add(
        InlineKeyboardButton("📂 Materiallar", callback_data="tp_materials"),
        InlineKeyboardButton("🧪 Testlar", callback_data="teacher_self_test")
    )
    bot.send_message(chat_id, "👨‍🏫 Teacher Panel", reply_markup=m)

def teacher_delete_step(message):
    text = (message.text or "").strip()
    try:
        tid = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_delete_step)
        return
    db = load_db()
    lst = db.get("teachers_custom", [])
    match = None
    for t in lst:
        if t.get("id") == tid:
            match = t
            break
    if not match:
        bot.send_message(message.chat.id, "❌ Topilmadi.", reply_markup=back_button())
        return
    name = match.get("name","")
    subject = match.get("subject","")
    price = match.get("price","")
    info = match.get("info","")
    txt = f"O'chirishni tasdiqlaysizmi?\n\nIsm: {name}\nFan: {subject}\nTo'lov: {price}\n\n{info}"
    mk = InlineKeyboardMarkup()
    mk.add(
        InlineKeyboardButton("✅ Ha", callback_data=f"confirm_delete_teacher:{tid}"),
        InlineKeyboardButton("❌ Yo'q", callback_data="cancel_delete_teacher")
    )
    bot.send_message(message.chat.id, txt, reply_markup=mk)

def teacher_edit_base_index_step(message):
    text = (message.text or "").strip()
    try:
        idx = int(text) - 1
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Indeks noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_edit_base_index_step)
        return
    user_id = message.from_user.id
    keys = admin_edit_state.get(user_id, {}).get("base_keys", [])
    if idx < 0 or idx >= len(keys):
        msg = bot.send_message(message.chat.id, "❌ Indeks chegaradan tashqarida. Qayta kiriting:")
        bot.register_next_step_handler(msg, teacher_edit_base_index_step)
        return
    k = keys[idx]
    admin_edit_state[user_id] = {"key": k}
    base = teachers.get(k, {})
    cur = apply_teacher_override(k, base)
    nm = (cur.get("name","") + (" " + cur.get("surname","") if cur.get("surname") else "")).strip()
    info_text = (
        f"Hozirgi ma'lumotlar:\n"
        f"Ism/Familiya: {nm}\n"
        f"Fan: {cur.get('subject','')}\n"
        f"To'lov: {cur.get('price','')}\n"
        f"Ma'lumot:\n{cur.get('info','')}\n\n"
        f"Qaysi maydonni tahrirlaysiz? (Ism/Familiya/Fan/Ma'lumot/To'lov)"
    )
    msg = bot.send_message(message.chat.id, info_text)
    bot.register_next_step_handler(msg, teacher_edit_base_field_step)

def teacher_edit_base_field_step(message):
    user_id = message.from_user.id
    st = admin_edit_state.get(user_id, {})
    field_in = (message.text or "").strip().lower()
    mapping = {
        "ism": "name",
        "familiya": "surname",
        "fan": "subject",
        "ma'lumot": "info",
        "malumot": "info",
        "to'lov": "price",
        "tolov": "price",
        "name": "name",
        "subject": "subject",
        "info": "info",
        "surname": "surname",
        "price": "price"
    }
    field = mapping.get(field_in)
    if not field:
        msg = bot.send_message(message.chat.id, "❌ Noto'g'ri tanlov. (Ism/Familiya/Fan/Ma'lumot/To'lov)")
        bot.register_next_step_handler(msg, teacher_edit_base_field_step)
        return
    st["field"] = field
    admin_edit_state[user_id] = st
    msg = bot.send_message(message.chat.id, "Yangi qiymatni yozing:")
    bot.register_next_step_handler(msg, teacher_edit_base_apply_step)

def teacher_edit_base_apply_step(message):
    user_id = message.from_user.id
    st = admin_edit_state.get(user_id, {})
    value = (message.text or "").strip()
    k = st.get("key")
    f = st.get("field")
    if not k or not f:
        bot.send_message(message.chat.id, "❌ Xato. Qayta urinib ko'ring.", reply_markup=back_button())
        return
    set_teacher_override_field(k, f, value)
    bot.send_message(message.chat.id, "✅ O'zgarish saqlandi.", reply_markup=back_button())

def admin_tp_setpwd_input_step(message):
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        bot.send_message(message.chat.id, "Ruxsat yo'q.", reply_markup=back_button())
        return
    pwd = (message.text or "").strip()
    st = admin_edit_state.get(admin_id, {})
    ref = st.get("tp_ref")
    if not ref:
        bot.send_message(message.chat.id, "Xato holat.", reply_markup=back_button())
        return
    set_teacher_password_for_ref(ref, pwd)
    bot.send_message(message.chat.id, f"✅ Parol saqlandi: {teacher_ref_to_name(ref)}", reply_markup=back_button())

def ariza_edit_index_step(message):
    text = (message.text or "").strip()
    try:
        idx = int(text) - 1
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Indeks noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, ariza_edit_index_step)
        return
    db = load_db()
    lst = db.get("arizalar", [])
    if idx < 0 or idx >= len(lst):
        msg = bot.send_message(message.chat.id, "❌ Indeks chegaradan tashqarida. Qayta kiriting:")
        bot.register_next_step_handler(msg, ariza_edit_index_step)
        return
    s = {"idx": idx}
    msg = bot.send_message(message.chat.id, "Yangi holatni yozing: (yangi/ko'rildi/yakunlandi/bekor)")
    bot.register_next_step_handler(msg, lambda m: ariza_edit_status_step(m, s))

def ariza_edit_status_step(message, state):
    status = (message.text or "").strip().lower()
    allowed = ["yangi", "ko'rildi", "yakunlandi", "bekor"]
    if status not in allowed:
        msg = bot.send_message(message.chat.id, "❌ Noto'g'ri holat. (yangi/ko'rildi/yakunlandi/bekor)")
        bot.register_next_step_handler(msg, lambda m: ariza_edit_status_step(m, state))
        return
    db = load_db()
    lst = db.get("arizalar", [])
    lst[state.get("idx")]["status"] = status
    db["arizalar"] = lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ Ariza holati yangilandi.", reply_markup=back_button())

def ariza_delete_index_step(message):
    text = (message.text or "").strip()
    try:
        idx = int(text) - 1
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Indeks noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, ariza_delete_index_step)
        return
    db = load_db()
    lst = db.get("arizalar", [])
    if idx < 0 or idx >= len(lst):
        msg = bot.send_message(message.chat.id, "❌ Indeks chegaradan tashqarida. Qayta kiriting:")
        bot.register_next_step_handler(msg, ariza_delete_index_step)
        return
    del lst[idx]
    db["arizalar"] = lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ Ariza o'chirildi.", reply_markup=back_button())

def check_edit_id_step(message):
    text = (message.text or "").strip()
    try:
        cid = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, check_edit_id_step)
        return
    db = load_db()
    lst = db.get("checks", [])
    found = False
    for c in lst:
        if c.get("id") == cid:
            found = True
            break
    if not found:
        msg = bot.send_message(message.chat.id, "❌ Chek topilmadi. Qayta kiriting:")
        bot.register_next_step_handler(msg, check_edit_id_step)
        return
    s = {"id": cid}
    msg = bot.send_message(message.chat.id, "Yangi holatni yozing: (kutilmoqda/tasdiqlandi/rad_etildi)")
    bot.register_next_step_handler(msg, lambda m: check_edit_status_step(m, s))

def check_edit_status_step(message, state):
    status = (message.text or "").strip().lower()
    allowed = ["kutilmoqda", "tasdiqlandi", "rad_etildi"]
    if status not in allowed:
        msg = bot.send_message(message.chat.id, "❌ Noto'g'ri holat. (kutilmoqda/tasdiqlandi/rad_etildi)")
        bot.register_next_step_handler(msg, lambda m: check_edit_status_step(m, state))
        return
    db = load_db()
    lst = db.get("checks", [])
    for c in lst:
        if c.get("id") == state.get("id"):
            c["status"] = status
            break
    db["checks"] = lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ Chek holati yangilandi.", reply_markup=back_button())

def check_delete_id_step(message):
    text = (message.text or "").strip()
    try:
        cid = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, check_delete_id_step)
        return
    db = load_db()
    lst = db.get("checks", [])
    new_lst = [c for c in lst if c.get("id") != cid]
    if len(new_lst) == len(lst):
        bot.send_message(message.chat.id, "❌ Chek topilmadi.", reply_markup=back_button())
        return
    db["checks"] = new_lst
    save_db(db)
    bot.send_message(message.chat.id, "✅ Chek o'chirildi.", reply_markup=back_button())

def subscriber_delete_id_step(message):
    text = (message.text or "").strip()
    try:
        sid = int(text)
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ ID noto'g'ri. Qayta kiriting:")
        bot.register_next_step_handler(msg, subscriber_delete_id_step)
        return
    remove_subscriber(sid)
    bot.send_message(message.chat.id, "✅ Obunachi o'chirildi.", reply_markup=back_button())

# --- CHECK/PAYMENT FORM HANDLERS ---
def check_name(message):
    """Get name for check"""
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    if not message.text:
        bot.send_message(message.chat.id, "❌ Iltimos, ismingizni matn ko'rinishida yozing!")
        msg = bot.send_message(message.chat.id, "👤 Ismingizni yozing:")
        bot.register_next_step_handler(msg, check_name)
        return

    name = message.text.strip()
    set_check_state(user_id, {"name": name})
    
    # Ask for teacher
    ask_teacher = {
        "O'zbek": f"✅ Ismingiz: {name}\n\n👨‍🏫 O'qituvchi ismini yozing:",
        "English": f"✅ Your name: {name}\n\n👨‍🏫 Enter teacher name:",
        "Русский": f"✅ Ваше имя: {name}\n\n👨‍🏫 Напишите имя преподавателя:"
    }
    msg = bot.send_message(message.chat.id, ask_teacher.get(lang, ask_teacher["O'zbek"]))
    bot.register_next_step_handler(msg, check_teacher)

def check_teacher(message):
    """Get teacher for check"""
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    if not message.text:
        bot.send_message(message.chat.id, "❌ Iltimos, o'qituvchi ismini matn ko'rinishida yozing!")
        msg = bot.send_message(message.chat.id, "👨‍🏫 O'qituvchi ismini yozing:")
        bot.register_next_step_handler(msg, check_teacher)
        return

    teacher = message.text.strip()
    state = get_check_state(user_id)
    if not state or "name" not in state:
        # State yo'qolgan - qaytadan boshlaymiz
        lang = get_user_lang(user_id)
        bot.send_message(message.chat.id, "❌ Session tugadi. Ismingizni qaytadan yozing:")
        msg = bot.send_message(message.chat.id, "👤 Ismingizni yozing:")
        bot.register_next_step_handler(msg, check_name)
        return
    state["teacher"] = teacher
    set_check_state(user_id, state)
    
    # Ask for subject
    markup = InlineKeyboardMarkup(row_width=1)
    for k, v in subjects.items():
        markup.add(InlineKeyboardButton(v, callback_data=f"check_subject:{k}"))
    
    ask_subject = {
        "O'zbek": f"✅ O'qituvchi: {teacher}\n\n📂 Fanni tanlang:",
        "English": f"✅ Teacher: {teacher}\n\n📂 Choose subject:",
        "Русский": f"✅ Преподаватель: {teacher}\n\n📂 Выберите предмет:"
    }
    bot.send_message(message.chat.id, ask_subject.get(lang, ask_subject["O'zbek"]), reply_markup=markup)

def check_amount(message):
    """Get amount for check"""
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    if not message.text:
        bot.send_message(message.chat.id, "❌ Iltimos, to'lov miqdorini matn ko'rinishida yozing!")
        msg = bot.send_message(message.chat.id, "💰 Tolov miqdorini yozing (so'm):")
        bot.register_next_step_handler(msg, check_amount)
        return

    amount = message.text.strip()
    state = get_check_state(user_id)
    if state and "name" in state:
        state["amount"] = amount
        set_check_state(user_id, state)
    else:
        # State yo'qolgan - qaytadan boshlaymiz
        bot.send_message(message.chat.id, "❌ Session tugadi. Ismingizni qaytadan yozing:")
        msg = bot.send_message(message.chat.id, "👤 Ismingizni yozing:")
        bot.register_next_step_handler(msg, check_name)
        return
    
    # Ask for photo
    ask_photo = {
        "O'zbek": f"✅ Tolov: {amount} so'm\n\n🧾 Chek rasmini yuboring:",
        "English": f"✅ Amount: {amount}\n\n🧾 Send receipt image:",
        "Русский": f"✅ Сумма: {amount}\n\n🧾 Отправьте изображение чека:"
    }
    msg = bot.send_message(message.chat.id, ask_photo.get(lang, ask_photo["O'zbek"]))
    bot.register_next_step_handler(msg, handle_photo_upload)

def handle_photo_upload(message):
    """Handle photo upload for payment receipt"""
    if not message.photo:
        bot.send_message(message.chat.id, "❌ Iltimos, rasm yuboring!")
        msg = bot.send_message(message.chat.id, "🧾 Chek rasmini yuboring:")
        bot.register_next_step_handler(msg, handle_photo_upload)
        return
    
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    photo_id = message.photo[-1].file_id
    
    # Get form data from DB
    form_data = get_check_state(user_id)
    
    # Save to database
    db = load_db()
    if "checks" not in db:
        db["checks"] = []
    
    check_id = max((c.get("id", 0) for c in db["checks"]), default=0) + 1
    check_entry = {
        "id": check_id,
        "user_id": user_id,
        "name": form_data.get("name", "N/A"),
        "teacher": form_data.get("teacher", "N/A"),
        "subject": form_data.get("subject", "N/A"),
        "amount": form_data.get("amount", "N/A"),
        "photo_id": photo_id,
        "time": datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M"),
        "status": "kutilmoqda"  # pending
    }
    db["checks"].append(check_entry)
    save_db(db)
    
    # Clean up form state from DB
    clear_check_state(user_id)
    
    # Confirm to user
    confirmations = {
        "O'zbek": f"✅ Chek qabul qilindi! (ID: {check_id})\nAdmin tasdiqini kutib turing...",
        "English": f"✅ Receipt accepted! (ID: {check_id})\nWaiting for admin confirmation...",
        "Русский": f"✅ Чек принят! (ID: {check_id})\nОжидание подтверждения администратором..."
    }
    bot.send_message(message.chat.id, confirmations.get(lang, confirmations["O'zbek"]), reply_markup=main_menu_lang(lang))
    
    # Notify admins
    admin_confirmation = InlineKeyboardMarkup()
    admin_confirmation.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_check:{check_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_check:{check_id}")
    )
    subject_name = subjects.get(check_entry["subject"], check_entry["subject"])
    admin_msg = f"📩 Yangi chek:\n👤 {check_entry['name']}\n👨‍🏫 {check_entry['teacher']}\n📂 {subject_name}\n💰 {check_entry['amount']} so'm\n🕒 {check_entry['time']}\n✅ ID: {check_id}"
    for admin in all_admins():
        try:
            bot.send_photo(admin, photo_id, caption=admin_msg, reply_markup=admin_confirmation)
        except Exception:
            pass

@bot.message_handler(content_types=['photo', 'document', 'audio', 'voice', 'location', 'contact', 'sticker', 'video'])
def handle_media(message):
    """Handle media messages"""
    user_id = message.from_user.id

    # Kontakt ulashilsa — next_step_handler ga uzatamiz (phone step uchun)
    if message.content_type == 'contact':
        if user_id in user_form_state:
            # next_step_handler o'zi oladi, shu yerda qayta chaqirishga hojat yo'q
            return
        lang = get_user_lang(user_id)
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
        bot.send_message(
            message.chat.id,
            f"📞 Telefon raqamingiz: {phone}",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    if user_id in check_form_states:
        handle_photo_upload(message)
        return
    if user_id in chat_mode:
        responses = {
            "O'zbek": "Kechirasiz, men faqat matnli xabarlarni tushunaman. Iltimos, matn yozing.",
            "English": "Sorry, I only understand text messages. Please send text.",
            "Русский": "Извините, я понимаю только текстовые сообщения. Пожалуйста, отправьте текст."
        }
        lang = get_user_lang(user_id)
        bot.reply_to(message, responses.get(lang, responses["English"]))
        return
    # Umumiy javob
    responses = {
        "O'zbek": "Men faqat matnli xabarlarni tushunaman.",
        "English": "I only understand text messages.",
        "Русский": "Я понимаю только текстовые сообщения."
    }
    lang = get_user_lang(user_id)
    bot.reply_to(message, responses.get(lang, responses["English"]))

if __name__ == "__main__":
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("✅ Bot ishga tushdi...")
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"❌ Botda kutilmagan xatolik: {e}")
