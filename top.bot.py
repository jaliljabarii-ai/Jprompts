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

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# ==============================================================================
# --- ۱. تعریف حالت‌های مکالمه (States) ---
# ==============================================================================
PERSONA, MISSION, CONTEXT, FORMAT_OUTPUT, EXTRA_DETAILS, PROMPT_CONFIRMATION = range(6)
MENU_CHOICE = 6

# ==============================================================================
# --- ۲. تنظیمات و کلیدهای API (مناسب برای محیط ابری/Render) ---
# ==============================================================================

# --- کلیدهای محیطی (Render باید این متغیرها را تامین کند) ---
TELEGRAM_BOT_TOKEN = os.environ.get("8211274452:AAE7H8VqzQYS-BAKsxkGmW5Y2BxBPEa7ldc", "MISSING_TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.environ.get("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", "MISSING_OPENROUTER_KEY")

# شناسه چت ادمین (Admin Chat ID)
# این را به صورت عددی در Render در متغیر محیطی ADMIN_CHAT_ID_RAW تنظیم کنید
try:
    ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID_RAW", 0))
except ValueError:
    ADMIN_CHAT_ID = 0

# --- ثابت‌های API ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "x-ai/grok-4-fast" 
SITE_URL = "https://t.me/jalil_jabari" 
SITE_TITLE = "Jprompts Bot" 

# --- ثابت‌های مدیریت کاربران ---
USER_IDS_FILE = "user_ids.txt"


# --- ثابت‌های محیط کاربری و دکمه‌ها ---
DEVELOPER_USERNAME = "@jalil_jabari"
DEVELOPER_TEXT = "توسعه‌دهنده: "

# تعریف ثابت‌های متن دکمه‌ها
PROMPT_ASSISTANT_BUTTON = "🤖 دستیار پرامپ‌نویسی"
ADMIN_COUNT_BUTTON_TEXT = "📊 شمارش اعضا" # کلید ادمین


# حذف سایر دکمه‌ها
MAIN_MENU_KEYBOARD = [
    [KeyboardButton(PROMPT_ASSISTANT_BUTTON)], 
]
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True, resize_keyboard=True)


# ==============================================================================
# --- ۳. توابع هسته هوش مصنوعی (AI Core) ---
# ==============================================================================

async def call_ai_api(prompt: str, api_key: str, model_name: str = OPENROUTER_MODEL) -> str:
    """
    فراخوانی واقعی API هوش مصنوعی (OpenRouter/Grok-4) با استفاده از httpx.
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
        "messages": [
            {
                "role": "user",
                "content": prompt 
            }
        ],
        "max_tokens": 2048
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=OPENROUTER_BASE_URL,
                headers=headers,
                json=data, 
                timeout=60.0 # افزایش مهلت زمانی
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
        if e.response.status_code in [401, 402]:
             return f"**خطا در API:** ارتباط با سرورهای OpenRouter برقرار نشد. (کد خطا: {e.response.status_code}). احتمالاً کلید API نامعتبر یا اعتبار حساب کم است."
        return f"**خطا در API:** ارتباط با سرورهای OpenRouter برقرار نشد. (کد خطا: {e.response.status_code})."
    except Exception as e:
        logging.error(f"Unknown API Error: {e}")
        return f"**خطای ناشناخته:** در اجرای پرامپت خطایی رخ داد: {e}"


# ==============================================================================
# --- ۴. توابع اصلی (Start, Menu, Cancel) ---
# ==============================================================================

def get_user_count() -> int:
    """خواندن تعداد کاربران ثبت شده از فایل."""
    if not os.path.exists(USER_IDS_FILE):
        return 0
    with open(USER_IDS_FILE, 'r') as f:
        # شمارش خطوط غیر خالی
        return len([line.strip() for line in f if line.strip()])

async def check_and_register_user(update: Update, context: CallbackContext) -> None:
    """بررسی و ثبت کاربر جدید و ارسال گزارش به ادمین."""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    # خواندن کاربران فعلی
    registered_users = set()
    if os.path.exists(USER_IDS_FILE):
        try:
            with open(USER_IDS_FILE, 'r') as f:
                # حذف خطوط خالی برای شمارش دقیق
                registered_users = set(line.strip() for line in f if line.strip())
        except Exception as e:
            logging.error(f"Error reading user file: {e}")

    if user_id not in registered_users:
        # کاربر جدید است: ثبت، گزارش و به‌روزرسانی شمارنده
        try:
            with open(USER_IDS_FILE, 'a') as f:
                f.write(f"{user_id}\n")
            
            new_count = len(registered_users) + 1

            admin_message = (
                "🔔 **کاربر جدید!**\n"
                f"👤 یوزرنیم: @{username if username else 'ندارد'}\n"
                f"🏷 نام: {first_name if first_name else 'ندارد'}\n"
                f"🆔 شناسه: `{user_id}`\n\n"
                f"📊 **تعداد کل کاربران:** {new_count}"
            )
            
            if ADMIN_CHAT_ID != 0:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)

        except Exception as e:
             logging.error(f"Failed to register user or send admin report: {e}")


async def start(update: Update, context: CallbackContext) -> int:
    """شروع مکالمه، نمایش توسعه‌دهنده و منوی اصلی."""
    
    # [قابلیت جدید]: بررسی و ثبت کاربر جدید
    await check_and_register_user(update, context)

    # حذف تمام داده‌های ذخیره شده کاربر برای ریست (فوری)
    if 'prompt_data' in context.user_data:
        del context.user_data['prompt_data']
    if 'final_creative_prompt' in context.user_data:
        del context.user_data['final_creative_prompt']

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
        "سلام! به ربات خوش آمدید.\n\n"
        "لطفاً گزینه پرامپ‌نویسی را برای شروع انتخاب کنید:"
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

    if choice == PROMPT_ASSISTANT_BUTTON:
        return await start_prompt_assistant(update, context)
        
    else:
        # اگر دکمه دیگری فشرده شد (که نباید وجود داشته باشد)
        await update.message.reply_text("لطفاً از دکمه '🤖 دستیار پرامپ‌نویسی' استفاده کنید.")
        return MENU_CHOICE


async def cancel(update: Update, context: CallbackContext) -> int:
    """لغو مکالمه توسط کاربر و بازگشت به منو."""
    
    # حذف تمام داده‌های ذخیره شده کاربر
    if 'prompt_data' in context.user_data:
        del context.user_data['prompt_data']
    if 'final_creative_prompt' in context.user_data:
        del context.user_data['final_creative_prompt']

    await update.message.reply_text(
        'مکالمه لغو و به منوی اصلی بازگشت. برای شروع مجدد /start را ارسال کنید.',
        reply_markup=MAIN_MENU_MARKUP
    )
    return ConversationHandler.END


# ==============================================================================
# --- ۵. توابع دستیار پرامپ‌نویسی (۵ سوال و مرحله تأیید) ---
# ==============================================================================

async def start_prompt_assistant(update: Update, context: CallbackContext) -> int:
    """شروع مکالمه دستیار پرامپ با سوال اول (پرسونا)."""
    context.user_data['prompt_data'] = {}
    message = (
        "**دستیار پرامپ‌نویسی (۵ سوال)**\n"
        "برای لغو در هر زمان، /cancel را ارسال کنید.\n\n"
        "**سوال ۱ از ۵: پرسونا (Persona)**\n"
        "هوش مصنوعی باید چه نقشی را ایفا کند؟ (مثلاً یک متخصص سئو، یک شاعر، یک برنامه‌نویس پایتون)"
    )
    await update.message.reply_text(message)
    return PERSONA


async def get_persona(update: Update, context: CallbackContext) -> int:
    persona = update.message.text
    context.user_data['prompt_data']['persona'] = persona
    message = "**سوال ۲ از ۵: مأموریت (Mission)**\nمأموریت اصلی شما چیست؟"
    await update.message.reply_text(message)
    return MISSION


async def get_mission(update: Update, context: CallbackContext) -> int:
    mission = update.message.text
    context.user_data['prompt_data']['mission'] = mission
    message = "**سوال ۳ از ۵: زمینه کار (Context)**\nزمینه یا شرایط خاصی که باید در نظر گرفته شود؟"
    await update.message.reply_text(message)
    return CONTEXT


async def get_context(update: Update, context: CallbackContext) -> int:
    context_data = update.message.text
    context.user_data['prompt_data']['context'] = context_data
    message = "**سوال ۴ از ۵: فرمت خروجی (Output Format)**\nفرمت خروجی را مشخص کنید."
    await update.message.reply_text(message)
    return FORMAT_OUTPUT


async def get_format_output(update: Update, context: CallbackContext) -> int:
    format_output = update.message.text
    context.user_data['prompt_data']['format_output'] = format_output
    message = "**سوال ۵ از ۵: توضیحات و جزئیات نهایی (Final Details)**\nهرگونه توضیحات یا جزئیات نهایی که باید به پرامپت اضافه شود."
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
        f"**پرسونا:** {data['persona']}. "
        f"**مأموریت:** {data['mission']}. "
        f"**زمینه:** {data['context']}. "
        f"**فرمت خروجی:** {data['format_output']}. "
        f"**جزئیات نهایی:** {data['extra_details']}."
    )

    # --- ۲. ساخت پرامپت نهایی برای Grok-4 (دستور ساخت پرامپت خلاقانه) ---
    final_prompt_to_grok = (
        "بر اساس جزئیات زیر، یک پرامپت خلاقانه و حرفه‌ای برای یک مدل زبان بزرگ (مثل خودت) بساز. "
        "پرامپت خروجی را به صورت مستقیم و بدون هیچ مقدمه‌ای ارائه کن. "
        "پرامپت باید تمام سرفصل‌های داده شده را در خود جای دهد:\n\n"
        f"**سرفصل‌ها:**\n{persian_details}"
    )
    
    # ذخیره پرامپت نهایی برای استفاده در مرحله تأیید
    context.user_data['final_prompt_to_grok'] = final_prompt_to_grok

    # --- ۳. نمایش گزارش و دکمه‌های تأیید ---
    await update.message.reply_text(
        "✅ **گزارش نهایی پرامپت شما آماده است!**\n\n"
        "--- **گزارش جزئیات** ---\n"
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
        await query.message.edit_text("عملیات ساخت پرامپت لغو شد.")
        if 'prompt_data' in context.user_data:
            del context.user_data['prompt_data']
        # ریست فوری و نمایش منو
        return await start(update, context) 

    elif query.data == 'confirm_send':
        
        final_prompt_to_grok = context.user_data.get('final_prompt_to_grok')
        if not final_prompt_to_grok:
            await query.message.edit_text("خطا: پرامپت نهایی پیدا نشد. لطفاً از ابتدا شروع کنید.")
            return await start(update, context)

        await query.message.edit_text("... **در حال ارسال به Grok-4/OpenRouter برای ساخت پرامپت خلاقانه** ...")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            # فراخوانی تابع هسته هوش مصنوعی
            creative_prompt_response = await call_ai_api(final_prompt_to_grok, OPENROUTER_API_KEY)
            
            # ذخیره پرامپت خلاقانه ساخته شده
            context.user_data['final_creative_prompt'] = creative_prompt_response

            # نمایش پاسخ Grok-4 (پرامپت خلاقانه)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"**پرامپت خلاقانه ساخته شده توسط هوش مصنوعی:**\n\n`{creative_prompt_response}`"
            )
            
            # --- بازگشت به منوی اصلی بلافاصله ---
            
            # پاک کردن داده‌های موقت (مانند داده‌های ۵ سوال)
            if 'prompt_data' in context.user_data:
                del context.user_data['prompt_data']
            
            # نمایش منوی اصلی بلافاصله
            await context.bot.send_message(
                chat_id=chat_id, 
                text="✅ **عملیات انجام شد!** لطفاً گزینه بعدی خود را انتخاب کنید.",
                reply_markup=MAIN_MENU_MARKUP
            )


        except Exception as e:
            logging.error(f"Error executing confirmed prompt: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="متأسفانه، در ساخت پرامپت خلاقانه خطایی رخ داد. لطفاً کلید API خود را بررسی کنید.",
                reply_markup=MAIN_MENU_MARKUP
            )
            return ConversationHandler.END


    # پایان مکالمه دستیار پرامپ‌نویسی
    return ConversationHandler.END


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
            f"📊 **آمار کاربران:**\nتعداد کل کاربران ثبت شده: **{user_count}**"
        )

# ==============================================================================
# --- ۸. تابع اصلی (Main) ---
# ==============================================================================

def main() -> None:
    """اجرای ربات."""

    # بررسی برای توقف در صورت عدم مقداردهی صحیح توکن تلگرام
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("خطا: لطفاً TELEGRAM_BOT_TOKEN را در خط مشخص شده در بخش ۲ جایگزین کنید.")
        return

    # بررسی ادمین چت آیدی
    if ADMIN_CHAT_ID == 0:
        print("هشدار: ADMIN_CHAT_ID تنظیم نشده است. گزارش‌دهی و دکمه مدیریت کاربران فعال نخواهد شد.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # CallbackHandler برای مدیریت دکمه‌های Inline
    # مدیریت دکمه‌های تأیید پرامپت
    application.add_handler(CallbackQueryHandler(handle_prompt_confirmation, pattern='^confirm_'))
    # مدیریت دکمه شمارش اعضا
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern='^admin_user_count$'))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={
            MENU_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_choice)],

            # حالت‌های دستیار پرامپ (۵ مرحله)
            PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_persona)],
            MISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mission)],
            CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_context)],
            FORMAT_OUTPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_output)],
            EXTRA_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_prompt)], 
            
            # حالت تأیید پرامپت (انتظار برای Callback)
            PROMPT_CONFIRMATION: [CallbackQueryHandler(handle_prompt_confirmation)],
        },

        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    print("ربات در حال اجرا است...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':

    main()
