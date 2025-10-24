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
# حالت‌های اضافی (MENU_CHOICE, IMAGE_PROMPT) حذف شدند.

# ==============================================================================
# --- ۲. تنظیمات و کلیدهای API ---
# ==============================================================================

# --- کلیدهای محیطی ---
TELEGRAM_BOT_TOKEN = os.environ.get("8211274452:AAE7H8VqzQYS-BAKsxkGmW5Y2BxBPEa7ldc", "8211274452:AAE7H8VqzQYS-BAKsxkGmW5Y2BxBPEa7ldc")
OPENROUTER_API_KEY = os.environ.get("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", "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")

# شناسه چت ادمین
try:
    ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID_RAW", 0))
except ValueError:
    ADMIN_CHAT_ID = 0

# --- ثابت‌های API ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
# مدل پیش‌فرض برای ساخت پرامپت
OPENROUTER_MODEL_TEXT = "x-ai/grok-4-fast" 
SITE_URL = "https://t.me/jalil_jabari" 
SITE_TITLE = "Jprompts Bot" 

# --- ثابت‌های مدیریت کاربران ---
USER_IDS_FILE = "user_ids.txt"


# --- ثابت‌های محیط کاربری و دکمه‌ها ---
DEVELOPER_USERNAME = "@jalil_jabari"
DEVELOPER_TEXT = "توسعه‌دهنده: "
ADMIN_COUNT_BUTTON_TEXT = "📊 شمارش اعضا" 

# دکمه‌ای که مکالمه را شروع می‌کند
PROMPT_ASSISTANT_BUTTON = "🤖 شروع دستیار پرامپ‌نویسی"

MAIN_MENU_KEYBOARD = [
    [KeyboardButton(PROMPT_ASSISTANT_BUTTON)], 
]
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=False, resize_keyboard=True)


# ==============================================================================
# --- ۳. توابع هسته هوش مصنوعی (AI Core) ---
# ==============================================================================

async def call_ai_api(messages: list, api_key: str, model_name: str, context: CallbackContext) -> str:
    """فراخوانی OpenRouter API با httpx."""
    if api_key == "MISSING_OPENROUTER_KEY": 
        return f"**[پاسخ شبیه‌سازی شده]**\n\nکلید OpenRouter یافت نشد."

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

        response.raise_for_status() 
        
        response_json = response.json()
        if response_json.get('choices') and response_json['choices'][0]['message']['content']:
            return response_json['choices'][0]['message']['content']
        else:
            logging.error(f"OpenRouter empty response: {response_json}")
            return "**خطا در پردازش پاسخ:** پاسخ معتبری از OpenRouter دریافت نشد."

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code in [401, 402]:
             return f"**خطا در API:** ارتباط با OpenRouter برقرار نشد. (کد خطا: {status_code})."
        elif status_code == 400:
             return f"**خطا در درخواست:** درخواست شما نامعتبر بود (کد خطا: {status_code})."
        return f"**خطا در API:** ارتباط با OpenRouter برقرار نشد. (کد خطا: {status_code})."
    except Exception as e:
        logging.error(f"Unknown API Error: {e}")
        return f"**خطای ناشناخته:** در اجرای پرامپت خطایی رخ داد: {e}"


# ==============================================================================
# --- ۴. توابع مدیریت کاربران و شروع (Start, Cancel) ---
# ==============================================================================

def get_user_count() -> int:
    """خواندن تعداد کاربران ثبت شده از فایل."""
    if not os.path.exists(USER_IDS_FILE):
        return 0
    try:
        with open(USER_IDS_FILE, 'r') as f:
            return len([line.strip() for line in f if line.strip()])
    except Exception as e:
        logging.warning(f"Could not read user file (OK if first run): {e}")
        return 0


async def check_and_register_user(update: Update, context: CallbackContext) -> None:
    """بررسی و ثبت کاربر جدید و ارسال گزارش به ادمین."""
    user_id = str(update.effective_user.id)
    # ... منطق ثبت نام و ارسال گزارش به ادمین (بدون تغییر) ...
    # این تابع منطق ثبت کاربر را در فایل `user_ids.txt` حفظ می‌کند.
    
    registered_users = set()
    try:
        if os.path.exists(USER_IDS_FILE):
            with open(USER_IDS_FILE, 'r') as f:
                registered_users = set(line.strip() for line in f if line.strip())
    except Exception as e:
        logging.error(f"Error reading user file: {e}")
        if user_id in registered_users:
             registered_users.remove(user_id)


    if user_id not in registered_users:
        try:
            with open(USER_IDS_FILE, 'a+') as f:
                f.write(f"{user_id}\n")
            
            new_count = get_user_count()

            admin_message = (
                "🔔 **کاربر جدید!**\n"
                f"👤 یوزرنیم: @{update.effective_user.username if update.effective_user.username else 'ندارد'}\n"
                f"🏷 نام: {update.effective_user.first_name if update.effective_user.first_name else 'ندارد'}\n"
                f"🆔 شناسه: `{user_id}`\n\n"
                f"📊 **تعداد کل کاربران:** {new_count}"
            )
            
            if ADMIN_CHAT_ID != 0:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID, 
                    text=admin_message, 
                    parse_mode='Markdown'
                )

        except Exception as e:
             logging.error(f"Failed to register user or send admin report: {e}")
             

async def start(update: Update, context: CallbackContext) -> int:
    """شروع مکالمه و نمایش منو."""
    
    await check_and_register_user(update, context)
    context.user_data.clear() # ریست کردن داده‌ها

    inline_keyboard = [
        [InlineKeyboardButton(DEVELOPER_TEXT + DEVELOPER_USERNAME,
                              url=f"https://t.me/{DEVELOPER_USERNAME.lstrip('@')}")]
    ]
    
    # دکمه ادمین
    if update.effective_user.id == ADMIN_CHAT_ID:
         inline_keyboard.append(
             [InlineKeyboardButton(ADMIN_COUNT_BUTTON_TEXT, callback_data='admin_user_count')]
         )

    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    welcome_message = (
        "سلام! به ربات **Jprompts Bot** خوش آمدید. 👋\n\n"
        "من به شما کمک می‌کنم تا بهترین پرامپت‌ها را برای مدل‌های هوش مصنوعی مختلف ایجاد کنید.\n\n"
        "لطفاً برای شروع **دستیار پرامپ‌نویسی** را انتخاب کنید."
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

    # پس از نمایش منو، باید منتظر انتخاب دکمه PROMPT_ASSISTANT_BUTTON باشیم.
    return PERSONA # از این حالت برای دریافت ورودی دکمه اصلی استفاده می‌کنیم


async def handle_first_input(update: Update, context: CallbackContext) -> int:
    """
    مدیریت ورودی اولیه. اگر دکمه "شروع دستیار پرامپ‌نویسی" فشرده شده باشد،
    مکالمه را به سوال اول هدایت می‌کند.
    """
    text = update.message.text
    
    if text == PROMPT_ASSISTANT_BUTTON:
        # مستقیم وارد منطق شروع دستیار پرامپ‌نویسی می‌شویم
        return await start_prompt_assistant_sequence(update, context)
    else:
        # اگر کاربر چیزی غیر از دکمه ارسال کرد، او را راهنمایی می‌کنیم
        await update.message.reply_text("لطفاً از دکمه **'🤖 شروع دستیار پرامپ‌نویسی'** استفاده کنید.")
        return PERSONA # در همین حالت می‌مانیم تا دکمه فشرده شود


async def cancel(update: Update, context: CallbackContext) -> int:
    """لغو مکالمه توسط کاربر و بازگشت به منو."""
    
    context.user_data.clear()

    await update.message.reply_text(
        'مکالمه لغو و به منوی اصلی بازگشت. برای شروع مجدد /start را ارسال کنید.',
        reply_markup=MAIN_MENU_MARKUP
    )
    return ConversationHandler.END


# ==============================================================================
# --- ۵. توابع دستیار پرامپ‌نویسی (متن) ---
# ==============================================================================

async def start_prompt_assistant_sequence(update: Update, context: CallbackContext) -> int:
    """شروع توالی سوالات با سوال اول (پرسونا)."""
    message_source = update.message if update.message else update.effective_message
    
    context.user_data['prompt_data'] = {}
    message = (
        "**دستیار پرامپ‌نویسی (۵ سوال)**\n"
        "برای لغو در هر زمان، /cancel را ارسال کنید.\n\n"
        "**سوال ۱ از ۵: پرسونا (Persona) 🎭**\n"
        "هوش مصنوعی باید چه نقشی را ایفا کند؟ (مثلاً یک متخصص سئو، یک شاعر، یک برنامه‌نویس پایتون)"
    )
    # **توجه:** ReplyKeyboardMarkup را حذف می‌کنیم تا فقط ورودی متنی انتظار رود
    await message_source.reply_text(message, reply_markup=None) 
    return MISSION # توجه: حالت بعدی برای دریافت پاسخ سوال ۱ است


async def get_persona(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۱ (پرسونا) و پرسیدن سوال ۲."""
    persona = update.message.text
    context.user_data['prompt_data']['persona'] = persona
    message = "**سوال ۲ از ۵: مأموریت (Mission) 🎯**\nمأموریت اصلی شما چیست؟ (چه خروجی‌ای می‌خواهید؟)"
    await update.message.reply_text(message)
    return CONTEXT # توجه: حالت بعدی برای دریافت پاسخ سوال ۲ است


async def get_mission(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۲ (مأموریت) و پرسیدن سوال ۳."""
    mission = update.message.text
    context.user_data['prompt_data']['mission'] = mission
    message = "**سوال ۳ از ۵: زمینه کار (Context) 📚**\nزمینه یا شرایط خاصی که باید در نظر گرفته شود؟ (مثلاً برای یک شرکت استارتاپی، یا برای یک مخاطب خاص)"
    await update.message.reply_text(message)
    return FORMAT_OUTPUT # توجه: حالت بعدی برای دریافت پاسخ سوال ۳ است


async def get_context(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۳ (زمینه کار) و پرسیدن سوال ۴."""
    context_data = update.message.text
    context.user_data['prompt_data']['context'] = context_data
    message = "**سوال ۴ از ۵: فرمت خروجی (Output Format) 📄**\nفرمت خروجی را مشخص کنید. (مثلاً در قالب JSON، یک جدول مارک‌داون، یک مقاله ۵۰۰ کلمه‌ای)"
    await update.message.reply_text(message)
    return EXTRA_DETAILS # توجه: حالت بعدی برای دریافت پاسخ سوال ۴ است


async def get_format_output(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۴ (فرمت خروجی) و پرسیدن سوال ۵."""
    format_output = update.message.text
    context.user_data['prompt_data']['format_output'] = format_output
    message = "**سوال ۵ از ۵: توضیحات و جزئیات نهایی (Final Details) 💡**\nهرگونه توضیحات یا جزئیات نهایی که باید به پرامپت اضافه شود. (مثلاً محدودیت‌ها، لحن، یا مثال‌ها)"
    await update.message.reply_text(message)
    return PROMPT_CONFIRMATION # توجه: حالت بعدی برای دریافت پاسخ سوال ۵ و رفتن به تأیید است


async def generate_prompt(update: Update, context: CallbackContext) -> int:
    """
    دریافت پاسخ سوال ۵ (جزئیات نهایی)، ساخت پرامپت و نمایش دکمه‌های تأیید.
    """
    extra_details = update.message.text
    context.user_data['prompt_data']['extra_details'] = extra_details
    data = context.user_data['prompt_data']

    # --- ساختاردهی پرامپت داخلی ---
    persian_details = (
        f"**پرسونا:** {data['persona']}.\n"
        f"**مأموریت:** {data['mission']}.\n"
        f"**زمینه:** {data['context']}.\n"
        f"**فرمت خروجی:** {data['format_output']}.\n"
        f"**جزئیات نهایی:** {data['extra_details']}."
    )

    # --- ساخت پرامپت نهایی برای Grok-4 ---
    final_prompt_to_grok = (
        "بر اساس جزئیات زیر، یک پرامپت خلاقانه، حرفه‌ای و بهینه برای یک مدل زبان بزرگ (مثل خودت) بساز. "
        "پرامپت خروجی باید به صورت مستقیم، بدون هیچ مقدمه‌ای و در زبان فارسی ارائه شود. "
        "پرامپت باید تمام سرفصل‌های داده شده را در خود جای دهد:\n\n"
        f"**سرفصل‌ها:**\n{persian_details}"
    )
    
    messages = [{"role": "user", "content": final_prompt_to_grok}]
    context.user_data['messages_to_ai'] = messages

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

    # در حالت PROMPT_CONFIRMATION می‌مانیم تا کاربر روی دکمه کلیک کند
    return PROMPT_CONFIRMATION 


async def handle_prompt_confirmation(update: Update, context: CallbackContext) -> int:
    """مدیریت دکمه‌های تأیید پرامپت خلاقانه."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    
    if query.data == 'confirm_restart':
        await query.message.edit_text("عملیات ساخت پرامپت لغو شد. 🔄")
        context.user_data.clear()
        # شروع مجدد از منو
        return await start(update, context) 

    elif query.data == 'confirm_send':
        
        messages_to_ai = context.user_data.get('messages_to_ai')
        if not messages_to_ai:
            await query.message.edit_text("خطا: پرامپت نهایی پیدا نشد. لطفاً از ابتدا شروع کنید.")
            return await start(update, context)

        await query.message.edit_text(f"... **در حال ارسال به {OPENROUTER_MODEL_TEXT} برای ساخت پرامپت خلاقانه** ... ⏳")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            creative_prompt_response = await call_ai_api(
                messages=messages_to_ai, 
                api_key=OPENROUTER_API_KEY,
                model_name=OPENROUTER_MODEL_TEXT,
                context=context
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"**پرامپت خلاقانه ساخته شده توسط هوش مصنوعی:**\n\n`{creative_prompt_response}`",
                parse_mode='Markdown'
            )
            
            # پایان و بازگشت به منوی اصلی
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

    return ConversationHandler.END


# ==============================================================================
# --- ۶. توابع مدیریت ادمین ---
# ==============================================================================

async def handle_admin_callback(update: Update, context: CallbackContext) -> None:
    """مدیریت دکمه شمارش اعضا."""
    query = update.callback_query
    await query.answer()

    if query.data == 'admin_user_count':
        if query.from_user.id != ADMIN_CHAT_ID:
            await query.message.reply_text("❌ دسترسی غیرمجاز.")
            return

        user_count = get_user_count()
        await query.message.reply_text(
            f"📊 **آمار کاربران:**\nتعداد کل کاربران ثبت شده: **{user_count}**",
            parse_mode='Markdown'
        )

# ==============================================================================
# --- ۷. تابع اصلی (Main) ---
# ==============================================================================

def main() -> None:
    """اجرای ربات."""

    # ... بررسی کلیدها و تنظیمات (حذف شده برای خلاصه‌سازی) ...

    if TELEGRAM_BOT_TOKEN == "MISSING_TELEGRAM_TOKEN":
        print("❌ خطا: لطفاً متغیر محیطی 'TELEGRAM_BOT_TOKEN_RAW' را در Render تنظیم کنید.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CallbackQueryHandler(handle_prompt_confirmation, pattern='^confirm_'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern='^admin_user_count$'))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={
            # حالت اولیه: نمایش منو و انتظار برای کلیک روی دکمه "شروع"
            PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_first_input)],
            
            # توالی دریافت سوالات
            MISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_persona)],
            CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mission)],
            FORMAT_OUTPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_context)],
            EXTRA_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_output)], 
            
            # حالت نهایی برای دریافت پاسخ سوال ۵ و نمایش دکمه‌های Inline
            PROMPT_CONFIRMATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_prompt),
                CallbackQueryHandler(handle_prompt_confirmation) # برای مدیریت دکمه‌های Inline
            ],
        },

        # Fallbacks: مدیریت دستورات /cancel و /start در هر مرحله
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    print("✅ ربات در حال اجرا است (Polling Mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
