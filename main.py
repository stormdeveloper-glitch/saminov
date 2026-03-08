import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import json
import os
from datetime import datetime
import random 

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

TOKEN_ENV = os.environ.get("BOT_TOKEN")
  
if not TOKEN_ENV:
    print("⚠️ BOT_TOKEN muhitdan topilmadi, vaqtinchalik tokendan foydalanilmoqda.")
else:
    BOT_TOKEN = TOKEN_ENV
    print(f"✅ BOT_TOKEN yuklandi: {BOT_TOKEN[:10]}...")

ADMINS = [6340253146, ]
bot = telebot.TeleBot(BOT_TOKEN)

DB_FILE = "db.json"
user_languages = {}  # {user_id: language}
chat_mode = {}        # {user_id: True} – chat rejimida ekanligini bildiradi

# --- JSON DATABASE ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"students": [], "arizalar": []}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


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

    # If nothing detected, return existing language (if any)
    if not detected:
        return user_languages.get(user_id)

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
    "android": "📱 Android dasturlash (mobil ilova yaratish)",
    "computer": "🖥 Kompyuter savodxonligi (0 dan o‘rgatish)",
    "Ingliz_tili": "🇬🇧 Ingliz tili (0 dan o‘rgatish)",
    "Rus_tili": "🇷🇺 Rus tili (0 dan o‘rgatish)",
    "Matematika": "➗ Matematika (maktab va oliy matematika)",
    "Koreys_tili": "🇰🇷 Koreys tili (0 dan o‘rgatish va professional)",
    "Biologiya": "🧬 Biologiya (maktab va oliy biologiya)",
    "Kimyo": "⚗️ Kimyo (maktab va oliy kimyo)",
    "Fizika": "🔭 Fizika (maktab va oliy fizika)",
    "Tarix": "📜 Tarix (maktab va oliy tarix)",
    "Geografiya": "🌍 Geografiya (maktab va oliy geografiya)",
}

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
    "python": "💻 Python dasturlash kursi 3 oy davom etadi, haftada 3 dars. Narxi 600.000 so'm.",
    "web": "🌐 Web dasturlash kursi HTML, CSS, JavaScript va React o'rgatadi. 3 oy davomiyligi, 500.000 so'm.",
    "android": "📱 Android dasturlash kursi Kotlin/Java o'rgatadi. 4 oy davomiyligi, 700.000 so'm.",
    "kurs": "📚 Bizda turli xil kurslar mavjud: kerakli kursni tanlab o'qishingiz mumkin.",
    "narx": "💰 Kurslar narxi 300.000 dan 700.000 so'm gacha.",
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
        "android": "📱 Android kursi Kotlin/Java bo'yicha.",
        "kurs": "📚 Bizda bir nechta kurs mavjud — qaysi birini xohlaysiz?",
        "narx": "💰 Kurslar narxi kursga qarab 300k-700k orasida.",
        "vaqt": "⏰ Darslar odatda haftada 3-4 marta bo'ladi.",
        "ingliz": "🇬🇧 Ingliz tili kursi 3 oy, haftada 3 marta.",
        "rus": "🇷🇺 Rus tili kursi 3 oy, haftada 3 marta."
    },
    "English": {
        "python": "💻 The Python course runs for 3 months, three lessons per week.",
        "web": "🌐 Web course covers HTML, CSS, JavaScript and React.",
        "android": "📱 Android course focuses on Kotlin/Java.",
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
            "facebook": "📘 Facebook"
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
            "facebook": "📘 Facebook"
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
            "facebook": "📘 Facebook"
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

def get_check_state(user_id):
    return check_form_states.get(user_id, {})

def set_check_state(user_id, data):
    check_form_states[user_id] = data

def clear_check_state(user_id):
    check_form_states.pop(user_id, None)

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
    if user_id in user_languages:
        # Already detected and set — show localized chat prompt
        lang = user_languages[user_id]
        lang_messages = {
            "O'zbek": "🇺🇿 Til avtomatik aniqlandi! Endi menyudan davom eting.",
            "English": "🇬🇧 Language auto-detected! Continue from the menu.",
            "Русский": "🇷🇺 Язык определён автоматически! Продолжайте из меню.",
            "Turkish": "🇹🇷 Dil otomatik algılandı! Menüden devam edin.",
            "한국어": "🇰🇷 언어가 자동으로 감지되었습니다! 메뉴에서 계속 하세요.",
            "العربية": "🇸🇦 تم اكتشاف اللغة تلقائيًا! تابع من القائمة.",
            "中文": "🇨🇳 语言已自动检测！请从菜单继续.",
            "日本語": "🇯🇵 言語が自動的に検出されました！メニューから続行してください。"
        }
        bot.send_message(message.chat.id, lang_messages.get(lang, lang_messages["O'zbek"]), reply_markup=main_menu_lang(lang))
    else:
        bot.send_message(
            message.chat.id,
            "👋 Xush kelibsiz! Iltimos til tanlang:\n\n*Choose your language:*\n*Выберите язык:*\n*Dil seçiniz:*\n*언어를 선택하십시오:*\n*اختر لغتك:*\n*请选择语言:*\n*言語を選択してください:*",
            parse_mode="Markdown",
            reply_markup=language_menu()
        )

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
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id
        is_mention = f"@{bot.get_me().username}" in (message.text or "")
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

def add_subscriber(user_id):
    db = load_db()
    subs = set(db.get("subscribers", []))
    subs.add(int(user_id))
    db["subscribers"] = list(subs)
    save_db(db)

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
        except:
            pass
        return

    # APPROVE CHECK
    if call.data.startswith("approve_check:"):
        if call.from_user.id not in ADMINS:
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
        if call.from_user.id not in ADMINS:
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
        text = "💻 Trial kurs:\nPython dasturlashning kirish darslari bepul."
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=back_button()
        )
    
    # motivation quote
    elif call.data == "motivation":
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
        bot.edit_message_text(
            info,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_button()
        )
    
    # O‘QITUVCHILAR
    elif call.data == "teachers":
        markup = InlineKeyboardMarkup(row_width=1)
        for key in teachers:
            markup.add(InlineKeyboardButton(teachers[key]["name"], callback_data=key))
        bot.edit_message_text(
            "👨‍🏫 O‘qituvchini tanlang:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif call.data in teachers:
        bot.edit_message_text(
            teachers[call.data]["info"],
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_button()
        )

    # FANLAR — subjects tugmalari (xuddi kurslar bilan bir xil)
    elif call.data == "subjects":
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
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("📄 Kursga yozilish", callback_data="ariza_course"),
            InlineKeyboardButton("💼 Ishga kirish", callback_data="ariza_job"),
        )
        bot.edit_message_text(
            "📝 Ariza bo‘limi",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

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
        lang = get_user_lang(call.from_user.id)
        bot.edit_message_text(
            localized_texts["welcome"].get(lang, localized_texts["welcome"]["O'zbek"]),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu_lang(lang)
        )    
    
    # QUIZ
    elif call.data == "quiz":
        markup = InlineKeyboardMarkup(row_width=1)
        for k in quiz_data.keys():
            markup.add(InlineKeyboardButton(quiz_data[k]["name"], callback_data=f"quiz:{k}"))
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
        msg_text = localized_texts["quiz_started"].get(lang, localized_texts["quiz_started"]["O'zbek"]).format(name=quiz_data[key]["name"])
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
        except:
            pass
    
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
            msg = bot.send_message(call.message.chat.id, "📞 Telefon raqamingizni yozing:")
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
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "yangi"
            }
            db["arizalar"].append(ariza)
            save_db(db)
            
            bot.send_message(call.message.chat.id, "✅ Ariza muvaffaqiyatli yuborildi!", reply_markup=main_menu_lang(lang))
            
            subject_name = subjects.get(form.get("subject"), form.get("subject"))
            admin_text = f"📩 Yangi ariza:\n👤 {form.get('name')}\n📞 {form.get('phone')}\n📚 {subject_name}\n🕒 {ariza['time']}"
            for admin in ADMINS:
                try:
                    bot.send_message(admin, admin_text)
                except:
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
    if quiz_key not in quiz_data:
        return
    
    questions = quiz_data[quiz_key]["questions"]
    if question_idx >= len(questions):
        # Quiz tugadi
        bot.send_message(
            chat_id,
            f"🎉 Quiz tugadi!\n\nSizning ballangiz: {score}/{len(questions)}\n\n{(score/len(questions))*100:.0f}%"
        )
        return
    
    q = questions[question_idx]
    markup = InlineKeyboardMarkup(row_width=1)
    
    for idx, option in enumerate(q["options"]):
        callback_data = f"answer:{quiz_key}:{question_idx}:{idx}:{score}"
        markup.add(InlineKeyboardButton(option, callback_data=callback_data))
    
    user_quiz_state[chat_id] = {"quiz_key": quiz_key, "question_idx": question_idx, "score": score}
    quiz_question_time[chat_id] = datetime.now()  # Record when question was shown
    
    msg = f"Savol {question_idx + 1}/{len(questions)}:\n\n⏱️ Vaqt: {QUIZ_TIME_LIMIT} soniya\n\n{q['q']}"
    bot.send_message(chat_id, msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def handle_quiz_answer(call):
    parts = call.data.split(":")
    quiz_key = parts[1]
    question_idx = int(parts[2])
    selected = int(parts[3])
    score = int(parts[4])
    
    if quiz_key not in quiz_data:
        return
    
    # Vaqt chegarasi tekshirish
    chat_id = call.message.chat.id
    if chat_id not in quiz_question_time:
        show_quiz_question(chat_id, quiz_key, question_idx + 1, score)
        return
    
    time_elapsed = (datetime.now() - quiz_question_time[chat_id]).total_seconds()
    
    if time_elapsed > QUIZ_TIME_LIMIT:
        # Vaqt tugadi
        q = quiz_data[quiz_key]["questions"][question_idx]
        bot.send_message(call.message.chat.id, f"⏱️ Vaqt tugadi! To'g'ri javob: {q['options'][q['correct']]}")
        show_quiz_question(call.message.chat.id, quiz_key, question_idx + 1, score)
        return
    
    q = quiz_data[quiz_key]["questions"][question_idx]
    is_correct = selected == q["correct"]
    
    if is_correct:
        score += 1
        bot.send_message(call.message.chat.id, f"✅ To'g'ri! ({time_elapsed:.1f}s)")
    else:
        bot.send_message(call.message.chat.id, f"❌ Noto'g'ri. To'g'ri javob: {q['options'][q['correct']]}")
    
    show_quiz_question(call.message.chat.id, quiz_key, question_idx + 1, score)

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
    phone = message.text.strip()
    
    # Store phone in form state
    if user_id in user_form_state:
        user_form_state[user_id]["phone"] = phone
    
    # Ask for confirmation
    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_phone_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_phone_no")
    )
    bot.send_message(message.chat.id, f"✅ Telefon: {phone} — to'g'rimi?", reply_markup=confirm_markup)

def job_phone(message, name):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    phone = message.text.strip()
    
    if user_id in user_form_state:
        user_form_state[user_id]["phone"] = phone
    
    confirm_markup = InlineKeyboardMarkup()
    confirm_markup.add(
        InlineKeyboardButton("✅ Ha", callback_data="ariza_confirm_phone_yes"),
        InlineKeyboardButton("❌ Yo'q", callback_data="ariza_confirm_phone_no")
    )
    bot.send_message(message.chat.id, f"✅ Telefon: {phone} — to'g'rimi?", reply_markup=confirm_markup)

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
        if search_name in teacher["name"].lower():
            found_teachers.append((key, teacher))
    
    if found_teachers:
        response = "🎓 Topilgan o'qituvchilar:\n\n"
        for key, teacher in found_teachers:
            response += teacher["info"] + "\n" + "=" * 40 + "\n"
        bot.send_message(message.chat.id, response, reply_markup=back_button())
    else:
        bot.send_message(
            message.chat.id,
            f"❌ '{search_name}' nomli o'qituvchi topilmadi.\n\nBiz quyidagi o'qituvchilarni taklif qilamiz:\n" + 
            "\n".join([f"👤 {t['name']}" for k, t in teachers.items()]),
            reply_markup=back_button()
        )

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
    
    check_id = len(db["checks"]) + 1
    check_entry = {
        "id": check_id,
        "user_id": user_id,
        "name": form_data.get("name", "N/A"),
        "teacher": form_data.get("teacher", "N/A"),
        "subject": form_data.get("subject", "N/A"),
        "amount": form_data.get("amount", "N/A"),
        "photo_id": photo_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
    for admin in ADMINS:
        try:
            bot.send_photo(admin, photo_id, caption=admin_msg, reply_markup=admin_confirmation)
        except:
            pass

@bot.message_handler(content_types=['photo', 'document', 'audio', 'voice', 'location', 'contact', 'sticker', 'video'])
def handle_media(message):
    """Handle media messages"""
    user_id = message.from_user.id
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
