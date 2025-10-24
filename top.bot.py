from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction 
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)
import logging
import os
import httpx 
import json

# ==============================================================================
# --- تنظیمات لاگینگ ---
# ==============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# ==============================================================================
# --- ۱. تعریف حالت‌های مکالمه (States) ---
# ==============================================================================
PERSONA, MISSION, CONTEXT, FORMAT_OUTPUT, EXTRA_DETAILS, PROMPT_CONFIRMATION = range(6)
MENU_CHOICE = 6
IMAGE_PROMPT = 7 # حالت جدید برای قابلیت تشخیص تصویر

# ==============================================================================
# --- ۲. تنظیمات و کلیدهای API (مناسب برای محیط ابری/Render) ---
# ==============================================================================

# --- کلیدهای محیطی (Render باید این متغیرها را تامین کند) ---
TELEGRAM_BOT_TOKEN = os.environ.get("8211274452:AAE7H8VqzQYS-BAKsxkGmW5Y2BxBPEa7ldc", "8211274452:AAE7H8VqzQYS-BAKsxkGmW5Y2BxBPEa7ldc")
OPENROUTER_API_KEY = os.environ.get("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", "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")

# شناسه چت ادمین (Admin Chat ID)
try:
    ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID_RAW", 0))
except ValueError:
    ADMIN_CHAT_ID = 0

# --- ثابت‌های API ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
# مدل پیش‌فرض برای ساخت پرامپت (متنی)
OPENROUTER_MODEL_TEXT = "x-ai/grok-4-fast" 
# مدل پیش‌فرض برای تحلیل تصویر (باید چندرسانه‌ای باشد)
OPENROUTER_MODEL_IMAGE = "meta-llama/llama-4-maverick:free" 
SITE_URL = "https://t.me/jalil_jabari" 
SITE_TITLE = "Jprompts Bot" 

# --- ثابت‌های مدیریت کاربران ---
USER_IDS_FILE = "user_ids.txt"


# --- ثابت‌های محیط کاربری و دکمه‌ها ---
DEVELOPER_USERNAME = "@jalil_jabari"
DEVELOPER_TEXT = "توسعه‌دهنده: "

# تعریف ثابت‌های متن دکمه‌ها
PROMPT_ASSISTANT_BUTTON = "🤖 دستیار پرامپ‌نویسی (متن)"
IMAGE_ANALYSIS_BUTTON = "🖼️ تحلیل تصویر"
ADMIN_COUNT_BUTTON_TEXT = "📊 شمارش اعضا" # کلید ادمین


MAIN_MENU_KEYBOARD = [
    [KeyboardButton(PROMPT_ASSISTANT_BUTTON)], 
    [KeyboardButton(IMAGE_ANALYSIS_BUTTON)],
]
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=False, resize_keyboard=True)
# one_time_keyboard=False برای ماندگاری دکمه‌های اصلی


# ==============================================================================
# --- ۳. توابع هسته هوش مصنوعی (AI Core) ---
# ==============================================================================

async def call_ai_api(messages: list, api_key: str, model_name: str, context: CallbackContext) -> str:
    """
    فراخوانی واقعی API هوش مصنوعی (OpenRouter) با استفاده از httpx.
    این تابع برای پشتیبانی از Multimodal به روز رسانی شده است.
    """
    if api_key == "MISSING_OPENROUTER_KEY": 
        # شبیه‌سازی پاسخ در صورت عدم مقداردهی صحیح کلید
        return f"**[پاسخ شبیه‌سازی شده]**\n\nکلید OpenRouter یافت نشد. لطفاً متغیر محیطی 'OPENROUTER_API_KEY_RAW' را تنظیم کنید."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": SITE_TITLE,
    }
    
    data = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url=OPENROUTER_BASE_URL,
                headers=headers,
                json=data, 
            )

        response.raise_for_status() # بررسی خطاهای HTTP (مانند 4xx یا 5xx)
        
        response_json = response.json()
        if response_json.get('choices') and response_json['choices'][0]['message']['content']:
            return response_json['choices'][0]['message']['content']
        else:
            logging.error(f"OpenRouter empty response: {response_json}")
            return "**خطا در پردازش پاسخ:** پاسخ معتبری از OpenRouter دریافت نشد."

    except httpx.HTTPStatusError as e:
        logging.error(f"OpenRouter HTTP Error: {e}")
        status_code = e.response.status_code
        if status_code in [401, 402]:
             return f"**خطا در API:** ارتباط با سرورهای OpenRouter برقرار نشد. (کد خطا: {status_code}). احتمالاً کلید API نامعتبر یا اعتبار حساب کم است."
        elif status_code == 400:
             return f"**خطا در درخواست:** درخواست شما نامعتبر بود (کد خطا: {status_code}). شاید فرمت ورودی (مثل URL تصویر) اشتباه باشد."
        return f"**خطا در API:** ارتباط با سرورهای OpenRouter برقرار نشد. (کد خطا: {status_code})."
    except Exception as e:
        logging.error(f"Unknown API Error: {e}")
        return f"**خطای ناشناخته:** در اجرای پرامپت خطایی رخ داد: {e}"


# ==============================================================================
# --- ۴. توابع مدیریت کاربران و شروع (Start, Menu, Cancel) ---
# ==============================================================================

def get_user_count() -> int:
    """خواندن تعداد کاربران ثبت شده از فایل."""
    if not os.path.exists(USER_IDS_FILE):
        return 0
    # در محیط Worker، از 'r' با مدیریت خطا استفاده می‌کنیم
    try:
        with open(USER_IDS_FILE, 'r') as f:
            # شمارش خطوط غیر خالی
            return len([line.strip() for line in f if line.strip()])
    except Exception as e:
        logging.warning(f"Could not read user file (OK if first run): {e}")
        return 0


async def check_and_register_user(update: Update, context: CallbackContext) -> None:
    """بررسی و ثبت کاربر جدید و ارسال گزارش به ادمین."""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    registered_users = set()
    try:
        if os.path.exists(USER_IDS_FILE):
            with open(USER_IDS_FILE, 'r') as f:
                registered_users = set(line.strip() for line in f if line.strip())
    except Exception as e:
        logging.error(f"Error reading user file: {e}")
        # در صورت خطا، فرض می‌کنیم کاربر ثبت شده نیست تا ثبت شود
        if user_id in registered_users:
             registered_users.remove(user_id)


    if user_id not in registered_users:
        # کاربر جدید است: ثبت، گزارش و به‌روزرسانی شمارنده
        try:
            # از 'a+' برای ایجاد فایل در صورت عدم وجود و اضافه کردن استفاده می‌کنیم
            with open(USER_IDS_FILE, 'a+') as f:
                f.write(f"{user_id}\n")
            
            # شمارش مجدد کاربران
            new_count = get_user_count()

            admin_message = (
                "🔔 **کاربر جدید!**\n"
                f"👤 یوزرنیم: @{username if username else 'ندارد'}\n"
                f"🏷 نام: {first_name if first_name else 'ندارد'}\n"
                f"🆔 شناسه: `{user_id}`\n\n"
                f"📊 **تعداد کل کاربران:** {new_count}"
            )
            
            if ADMIN_CHAT_ID != 0:
                # ارسال پیام گزارش با حالت HTML
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID, 
                    text=admin_message, 
                    parse_mode='Markdown'
                )

        except Exception as e:
             logging.error(f"Failed to register user or send admin report: {e}")


async def start(update: Update, context: CallbackContext) -> int:
    """شروع مکالمه، نمایش توسعه‌دهنده و منوی اصلی."""
    
    # [قابلیت جدید]: بررسی و ثبت کاربر جدید
    await check_and_register_user(update, context)

    # حذف تمام داده‌های ذخیره شده کاربر برای ریست (فوری)
    context.user_data.clear()

    # ساخت کیبورد Inline (شامل دکمه مدیریت برای ادمین)
    inline_keyboard = [
        [InlineKeyboardButton(DEVELOPER_TEXT + DEVELOPER_USERNAME,
                              url=f"https://t.me/{DEVELOPER_USERNAME.lstrip('@')}")]
    ]
    
    # افزودن دکمه مدیریت فقط در صورتی که کاربر ادمین باشد
    if update.effective_user.id == ADMIN_CHAT_ID:
         inline_keyboard.append(
             [InlineKeyboardButton(ADMIN_COUNT_BUTTON_TEXT, callback_data='admin_user_count')]
         )

    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    welcome_message = (
        "سلام! به ربات **Jprompts Bot** خوش آمدید. 👋\n\n"
        "من به شما کمک می‌کنم تا بهترین پرامپت‌ها را برای مدل‌های هوش مصنوعی مختلف ایجاد کنید یا تصاویر را تحلیل کنید.\n\n"
        "لطفاً گزینه مورد نظر را برای شروع انتخاب کنید:"
    )

    message_source = update.message if update.message else update.effective_message

    await message_source.reply_text(
        welcome_message,
        reply_markup=reply_markup
    )

    await message_source.reply_text(
        "منوی اصلی:",
        reply_markup=MAIN_MENU_MARKUP
    )

    return MENU_CHOICE


async def handle_menu_choice(update: Update, context: CallbackContext) -> int:
    """مدیریت انتخاب کاربر از منوی اصلی."""

    choice = update.message.text

    # پاک کردن داده‌های مکالمه قبلی
    context.user_data.clear()

    if choice == PROMPT_ASSISTANT_BUTTON:
        return await start_prompt_assistant(update, context)
        
    elif choice == IMAGE_ANALYSIS_BUTTON:
        return await start_image_analysis(update, context)

    else:
        await update.message.reply_text("لطفاً از دکمه‌های موجود استفاده کنید.")
        return MENU_CHOICE


async def cancel(update: Update, context: CallbackContext) -> int:
    """لغو مکالمه توسط کاربر و بازگشت به منو."""
    
    # حذف تمام داده‌های ذخیره شده کاربر
    context.user_data.clear()

    await update.message.reply_text(
        'مکالمه لغو و به منوی اصلی بازگشت. برای شروع مجدد /start را ارسال کنید.',
        reply_markup=MAIN_MENU_MARKUP
    )
    return ConversationHandler.END


# ==============================================================================
# --- ۵. توابع دستیار پرامپ‌نویسی (متن) ---
# ==============================================================================

async def start_prompt_assistant(update: Update, context: CallbackContext) -> int:
    """شروع مکالمه دستیار پرامپ با سوال اول (پرسونا)."""
    context.user_data['prompt_data'] = {}
    message = (
        "**دستیار پرامپ‌نویسی (۵ سوال)**\n"
        "برای لغو در هر زمان، /cancel را ارسال کنید.\n\n"
        "**سوال ۱ از ۵: پرسونا (Persona) 🎭**\n"
        "هوش مصنوعی باید چه نقشی را ایفا کند؟ (مثلاً یک متخصص سئو، یک شاعر، یک برنامه‌نویس پایتون)"
    )
    await update.message.reply_text(message)
    return PERSONA


async def get_persona(update: Update, context: CallbackContext) -> int:
    persona = update.message.text
    context.user_data['prompt_data']['persona'] = persona
    message = "**سوال ۲ از ۵: مأموریت (Mission) 🎯**\nمأموریت اصلی شما چیست؟ (چه خروجی‌ای می‌خواهید؟)"
    await update.message.reply_text(message)
    return MISSION


async def get_mission(update: Update, context: CallbackContext) -> int:
    mission = update.message.text
    context.user_data['prompt_data']['mission'] = mission
    message = "**سوال ۳ از ۵: زمینه کار (Context) 📚**\nزمینه یا شرایط خاصی که باید در نظر گرفته شود؟ (مثلاً برای یک شرکت استارتاپی، یا برای یک مخاطب خاص)"
    await update.message.reply_text(message)
    return CONTEXT


async def get_context(update: Update, context: CallbackContext) -> int:
    context_data = update.message.text
    context.user_data['prompt_data']['context'] = context_data
    message = "**سوال ۴ از ۵: فرمت خروجی (Output Format) 📄**\nفرمت خروجی را مشخص کنید. (مثلاً در قالب JSON، یک جدول مارک‌داون، یک مقاله ۵۰۰ کلمه‌ای)"
    await update.message.reply_text(message)
    return FORMAT_OUTPUT


async def get_format_output(update: Update, context: CallbackContext) -> int:
    format_output = update.message.text
    context.user_data['prompt_data']['format_output'] = format_output
    message = "**سوال ۵ از ۵: توضیحات و جزئیات نهایی (Final Details) 💡**\nهرگونه توضیحات یا جزئیات نهایی که باید به پرامپت اضافه شود. (مثلاً محدودیت‌ها، لحن، یا مثال‌ها)"
    await update.message.reply_text(message)
    return EXTRA_DETAILS


async def generate_prompt(update: Update, context: CallbackContext) -> int:
    """
    تولید پرامپت خام و نمایش دکمه‌های تأیید/شروع مجدد.
    """
    extra_details = update.message.text
    context.user_data['prompt_data']['extra_details'] = extra_details
    data = context.user_data['prompt_data']

    # --- ۱. ساختاردهی پرامپت داخلی (Persian/Details) ---
    persian_details = (
        f"**پرسونا:** {data['persona']}.\n"
        f"**مأموریت:** {data['mission']}.\n"
        f"**زمینه:** {data['context']}.\n"
        f"**فرمت خروجی:** {data['format_output']}.\n"
        f"**جزئیات نهایی:** {data['extra_details']}."
    )

    # --- ۲. ساخت پرامپت نهایی برای Grok-4 (دستور ساخت پرامپت خلاقانه) ---
    final_prompt_to_grok = (
        "بر اساس جزئیات زیر، یک پرامپت خلاقانه، حرفه‌ای و بهینه برای یک مدل زبان بزرگ (مثل خودت) بساز. "
        "پرامپت خروجی باید به صورت مستقیم، بدون هیچ مقدمه‌ای و در زبان فارسی ارائه شود. "
        "پرامپت باید تمام سرفصل‌های داده شده را در خود جای دهد:\n\n"
        f"**سرفصل‌ها:**\n{persian_details}"
    )
    
    # ساخت پیام‌های ورودی برای call_ai_api
    messages = [
        {
            "role": "user",
            "content": final_prompt_to_grok
        }
    ]

    # ذخیره پیام‌ها برای استفاده در مرحله تأیید
    context.user_data['messages_to_ai'] = messages

    # --- ۳. نمایش گزارش و دکمه‌های تأیید ---
    await update.message.reply_text(
        "✅ **گزارش نهایی پرامپت شما آماده است!**\n\n"
        "--- **جزئیات وارد شده** ---\n"
        f"{persian_details}\n\n"
        "آیا این جزئیات را تأیید می‌کنید تا پرامپت خلاقانه ساخته شود؟"
    )

    keyboard = [
        [InlineKeyboardButton("✅ تأیید و ارسال به AI", callback_data='confirm_send')],
        [InlineKeyboardButton("❌ شروع مجدد دستیار پرامپ‌نویسی", callback_data='confirm_restart')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "انتخاب کنید:",
        reply_markup=reply_markup
    )

    # رفتن به حالت تأیید
    return PROMPT_CONFIRMATION


async def handle_prompt_confirmation(update: Update, context: CallbackContext) -> int:
    """مدیریت دکمه‌های تأیید پرامپت خلاقانه."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    
    if query.data == 'confirm_restart':
        # پاک کردن داده‌های مکالمه فعلی دستیار پرامپ‌نویسی و بازگشت به منوی اصلی
        await query.message.edit_text("عملیات ساخت پرامپت لغو شد. 🔄")
        context.user_data.clear()
        # ریست فوری و نمایش منو
        return await start(update, context) 

    elif query.data == 'confirm_send':
        
        messages_to_ai = context.user_data.get('messages_to_ai')
        if not messages_to_ai:
            await query.message.edit_text("خطا: پرامپت نهایی پیدا نشد. لطفاً از ابتدا شروع کنید.")
            return await start(update, context)

        await query.message.edit_text(f"... **در حال ارسال به {OPENROUTER_MODEL_TEXT} برای ساخت پرامپت خلاقانه** ... ⏳")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            # فراخوانی تابع هسته هوش مصنوعی
            creative_prompt_response = await call_ai_api(
                messages=messages_to_ai, 
                api_key=OPENROUTER_API_KEY,
                model_name=OPENROUTER_MODEL_TEXT,
                context=context
            )
            
            # نمایش پاسخ Grok-4 (پرامپت خلاقانه)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"**پرامپت خلاقانه ساخته شده توسط هوش مصنوعی:**\n\n`{creative_prompt_response}`",
                parse_mode='Markdown'
            )
            
            # --- بازگشت به منوی اصلی بلافاصله ---
            
            context.user_data.clear()
            
            await context.bot.send_message(
                chat_id=chat_id, 
                text="✅ **عملیات انجام شد!** لطفاً گزینه بعدی خود را انتخاب کنید.",
                reply_markup=MAIN_MENU_MARKUP
            )


        except Exception as e:
            logging.error(f"Error executing confirmed prompt: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ متأسفانه، در ساخت پرامپت خلاقانه خطایی رخ داد: {e}\nلطفاً کلید API خود را بررسی کنید.",
                reply_markup=MAIN_MENU_MARKUP
            )
            return ConversationHandler.END


    # پایان مکالمه دستیار پرامپ‌نویسی
    return ConversationHandler.END

# ==============================================================================
# --- ۶. توابع تحلیل تصویر (Multimodal) ---
# ==============================================================================

async def start_image_analysis(update: Update, context: CallbackContext) -> int:
    """شروع حالت تحلیل تصویر."""
    context.user_data.clear()
    message = (
        "**🖼️ تحلیل تصویر (Multimodal)**\n"
        "برای لغو در هر زمان، /cancel را ارسال کنید.\n\n"
        "لطفاً **تصویر** مورد نظر خود را ارسال کنید. (شما می‌توانید یک توضیح متنی یا سوال نیز همراه تصویر ارسال کنید.)"
    )
    await update.message.reply_text(message)
    return IMAGE_PROMPT

async def analyze_image(update: Update, context: CallbackContext) -> int:
    """دریافت تصویر و متن، ارسال به مدل Multimodal و نمایش پاسخ."""
    
    # 1. بررسی وجود عکس
    if not update.message.photo:
        await update.message.reply_text("لطفاً یک **تصویر** برای تحلیل ارسال کنید. 🖼️")
        return IMAGE_PROMPT # در همین حالت می‌مانیم

    # --- ۱. استخراج تصویر و متن ---
    photo_file = update.message.photo[-1] # بزرگ‌ترین نسخه
    
    # دریافت URL مستقیم تصویر از تلگرام
    file = await context.bot.get_file(photo_file.file_id)
    image_url = file.file_path 
    
    # دریافت متن همراه تصویر (Caption) یا متن ساده
    user_caption = update.message.caption if update.message.caption else ""
    user_text = user_caption.strip()
    
    # اگر متنی وجود ندارد، یک درخواست پیش‌فرض می‌گذاریم
    if not user_text:
        user_text = "این تصویر را به دقت تحلیل کن و یک توضیح مفصل در مورد محتوای آن به زبان فارسی ارائه بده."

    
    # --- ۲. ساختاردهی پیام Multimodal برای OpenRouter ---
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_text 
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url 
                    }
                }
            ]
        }
    ]

    chat_id = update.message.chat_id
    await update.message.reply_text(f"... **در حال ارسال به {OPENROUTER_MODEL_IMAGE} برای تحلیل تصویر** ... ⏳")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # فراخوانی تابع هسته هوش مصنوعی با مدل تحلیل تصویر
        analysis_response = await call_ai_api(
            messages=messages, 
            api_key=OPENROUTER_API_KEY,
            model_name=OPENROUTER_MODEL_IMAGE,
            context=context
        )
        
        # نمایش پاسخ تحلیل تصویر
        await update.message.reply_text(
            f"**✅ تحلیل تصویر با استفاده از {OPENROUTER_MODEL_IMAGE}:**\n\n{analysis_response}",
            reply_markup=MAIN_MENU_MARKUP, # بازگشت به منوی اصلی
            parse_mode='Markdown'
        )

    except Exception as e:
        logging.error(f"Error executing image analysis: {e}")
        await update.message.reply_text(
            f"❌ متأسفانه، در تحلیل تصویر خطایی رخ داد: {e}\nلطفاً کلید API خود را بررسی کنید.",
            reply_markup=MAIN_MENU_MARKUP
        )

    # پایان مکالمه تحلیل تصویر
    return ConversationHandler.END


# ==============================================================================
# --- ۷. توابع مدیریت ادمین ---
# ==============================================================================

async def handle_admin_callback(update: Update, context: CallbackContext) -> None:
    """مدیریت دکمه شمارش اعضا."""
    query = update.callback_query
    await query.answer()

    if query.data == 'admin_user_count':
        # استفاده از == برای مقایسه مستقیم شناسه عددی
        if query.from_user.id != ADMIN_CHAT_ID:
            await query.message.reply_text("❌ دسترسی غیرمجاز.")
            return

        user_count = get_user_count()
        await query.message.reply_text(
            f"📊 **آمار کاربران:**\nتعداد کل کاربران ثبت شده: **{user_count}**",
            parse_mode='Markdown'
        )

# ==============================================================================
# --- ۸. تابع اصلی (Main) ---
# ==============================================================================

def main() -> None:
    """اجرای ربات."""

    if TELEGRAM_BOT_TOKEN == "MISSING_TELEGRAM_TOKEN":
        print("❌ خطا: لطفاً متغیر محیطی 'TELEGRAM_BOT_TOKEN_RAW' را در Render تنظیم کنید.")
        return

    if ADMIN_CHAT_ID == 0:
        print("⚠️ هشدار: ADMIN_CHAT_ID تنظیم نشده است. گزارش‌دهی و دکمه مدیریت کاربران فعال نخواهد شد.")
    
    if OPENROUTER_API_KEY == "MISSING_OPENROUTER_KEY":
        print("⚠️ هشدار: OPENROUTER_API_KEY تنظیم نشده است. قابلیت‌های هوش مصنوعی فعال نخواهد شد.")


    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # CallbackHandler برای مدیریت دکمه‌های Inline
    application.add_handler(CallbackQueryHandler(handle_prompt_confirmation, pattern='^confirm_'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern='^admin_user_count$'))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={
            # ورود به منوی اصلی
            MENU_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_choice)],

            # حالت‌های دستیار پرامپ (متنی)
            PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_persona)],
            MISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mission)],
            CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_context)],
            FORMAT_OUTPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_output)],
            EXTRA_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_prompt)], 
            
            # حالت تأیید پرامپت (انتظار برای Callback)
            PROMPT_CONFIRMATION: [CallbackQueryHandler(handle_prompt_confirmation)],

            # حالت تحلیل تصویر (چندرسانه‌ای) - دریافت عکس یا متن
            IMAGE_PROMPT: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), analyze_image)],
        },

        # Fallbacks: مدیریت دستورات /cancel و /start در هر مرحله
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    print("✅ ربات در حال اجرا است (Polling Mode)...")
    # run_polling برای محیط Worker در Render مناسب است.
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
