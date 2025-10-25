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
from google import genai
from google.genai.errors import APIError
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

# ==============================================================================
# --- ۲. تنظیمات و کلیدهای API (برای محیط Gemini) ---
# ==============================================================================

# --- کلیدهای محیطی (از Environment Variables خوانده می‌شوند) ---
TELEGRAM_BOT_TOKEN = os.environ.get("8293849771:AAFuKBcwhSKn6h8OzEScoTWo5_OGAgwruuo","8293849771:AAFuKBcwhSKn6h8OzEScoTWo5_OGAgwruuo")
GEMINI_API_KEY = os.environ.get("AIzaSyCwMxeXRBovnYUwC2EMAg67pU-uv4Msbug", "AIzaSyCwMxeXRBovnYUwC2EMAg67pU-uv4Msbug")

# شناسه چت ادمین
try:
    ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID_RAW", 0))
except ValueError:
    ADMIN_CHAT_ID = 0

# --- ثابت‌های مدل Gemini ---
# مدل پیش‌فرض: ارتقاء به Pro برای پایداری و کیفیت بهتر پرامپت
GEMINI_MODEL_TEXT = "gemini-2.5-pro" 
MAX_INPUT_LENGTH = 1500 # حداکثر 1500 کاراکتر برای هر ورودی کاربر (برای جلوگیری از خطای طول پیام)

# --- ثابت‌های مدیریت کاربران ---
USER_IDS_FILE = "user_ids.txt"


# --- ثابت‌های محیط کاربری و دکمه‌ها ---
DEVELOPER_USERNAME = "@jalil_jabari"
DEVELOPER_TEXT = "توسعه‌دهنده: "
ADMIN_COUNT_BUTTON_TEXT = "📊 شمارش اعضا" 
PROMPT_ASSISTANT_BUTTON = "🤖 شروع دستیار پرامپ‌نویسی"

MAIN_MENU_KEYBOARD = [
    [KeyboardButton(PROMPT_ASSISTANT_BUTTON)], 
]
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=False, resize_keyboard=True)

# --- تنظیم کلاینت Gemini در خارج از توابع ---
GEMINI_CLIENT = None
if GEMINI_API_KEY != "MISSING_GEMINI_KEY":
    try:
        GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logging.error(f"Failed to initialize Gemini Client: {e}")
        GEMINI_CLIENT = None


# ==============================================================================
# --- ۳. توابع هسته هوش مصنوعی (AI Core) ---
# ==============================================================================

async def call_ai_api(messages: list, model_name: str, context: CallbackContext) -> str:
    """فراخوانی API رسمی Gemini."""
    
    if GEMINI_CLIENT is None:
        return f"**[پاسخ شبیه‌سازی شده]**\n\nکلید Gemini API یافت نشد. لطفاً متغیر `GEMINI_API_KEY_RAW` را تنظیم کنید."

    # تبدیل فرمت پیام‌ها به فرمت مورد نیاز genai.Client
    # توجه: کتابخانه genai.Client به صورت مستقیم از همان فرمت
    # {"role": "user", "content": "..."} استفاده می کند
    # اما اگر شامل تصاویر بود، باید به فرمت {"role": "user", "parts": [Part, ...]} تبدیل می شد.
    # در اینجا چون فقط متن است، از همان فرمت ورودی استفاده می کنیم.
    
    try:
        # فراخوانی API
        response = GEMINI_CLIENT.models.generate_content(
            model=model_name,
            contents=messages,
            config={"max_output_tokens": 2048},
        )
        
        return response.text

    except APIError as e:
        logging.error(f"Gemini API Error: {e}")
        # مدیریت خطاهای رایج، از جمله خطای Message is too long
        if "Message is too long" in str(e):
             return "**خطا در API:** پرامپت نهایی شما بسیار طولانی است و از محدودیت ورودی مدل فراتر رفته است. لطفاً پرامپت را کوتاه‌تر کنید."
        return f"**خطا در API:** ارتباط با Gemini برقرار نشد. (جزئیات: {e})"
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
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
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
                f"👤 یوزرنیم: @{username if username else 'ندارد'}\n"
                f"🏷 نام: {first_name if first_name else 'ندارد'}\n"
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
    context.user_data.clear() 

    inline_keyboard = [
        [InlineKeyboardButton(DEVELOPER_TEXT + DEVELOPER_USERNAME,
                              url=f"https://t.me/{DEVELOPER_USERNAME.lstrip('@')}")]
    ]
    
    if update.effective_user.id == ADMIN_CHAT_ID:
         inline_keyboard.append(
             [InlineKeyboardButton(ADMIN_COUNT_BUTTON_TEXT, callback_data='admin_user_count')]
         )

    reply_markup_inline = InlineKeyboardMarkup(inline_keyboard)

    welcome_message = (
        "سلام! به ربات **Jprompts Bot** خوش آمدید. 👋\n\n"
        "من به شما کمک می‌کنم تا بهترین پرامپت‌ها را برای مدل‌های هوش مصنوعی مختلف ایجاد کنید.\n\n"
        "لطفاً برای شروع **دستیار پرامپ‌نویسی** را انتخاب کنید."
    )

    message_source = update.message if update.message else update.effective_message

    await message_source.reply_text(
        welcome_message,
        reply_markup=reply_markup_inline
    )
    
    await message_source.reply_text(
        "منوی اصلی:",
        reply_markup=MAIN_MENU_MARKUP
    )

    return PERSONA 


async def handle_first_input(update: Update, context: CallbackContext) -> int:
    """مدیریت ورودی اولیه برای شروع توالی سوالات."""
    text = update.message.text
    
    if text == PROMPT_ASSISTANT_BUTTON:
        context.user_data['prompt_data'] = {}
        message = (
            "**دستیار پرامپ‌نویسی (۵ سوال)**\n"
            "برای لغو در هر زمان، /cancel را ارسال کنید.\n\n"
            f"**سوال ۱ از ۵: پرسونا (Persona) 🎭** (حداکثر {MAX_INPUT_LENGTH} کاراکتر)\n"
            "هوش مصنوعی باید چه نقشی را ایفا کند؟ (مثلاً یک متخصص سئو، یک شاعر، یک برنامه‌نویس پایتون)"
        )
        await update.message.reply_text(message, reply_markup=None) 
        return MISSION 
    else:
        await update.message.reply_text("لطفاً از دکمه **'🤖 شروع دستیار پرامپ‌نویسی'** استفاده کنید.")
        return PERSONA


async def cancel(update: Update, context: CallbackContext) -> int:
    """لغو مکالمه توسط کاربر و بازگشت به منو."""
    
    context.user_data.clear()

    await update.message.reply_text(
        'مکالمه لغو و به منوی اصلی بازگشت. برای شروع مجدد /start را ارسال کنید.',
        reply_markup=MAIN_MENU_MARKUP
    )
    return ConversationHandler.END


# ==============================================================================
# --- ۵. توابع دستیار پرامپ‌نویسی (توالی سوالات) ---
# ==============================================================================

def check_length(text: str, max_len: int = MAX_INPUT_LENGTH) -> bool:
    """بررسی می کند که طول متن از حداکثر مجاز فراتر نرود."""
    return len(text) <= max_len

async def get_persona(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۱ (پرسونا) و پرسیدن سوال ۲."""
    persona = update.message.text
    
    if not check_length(persona):
        await update.message.reply_text(
            f"❌ **خطا:** ورودی شما ({len(persona)} کاراکتر) بیش از حد طولانی است. "
            f"لطفاً پاسخ خود را حداکثر به {MAX_INPUT_LENGTH} کاراکتر محدود کنید و دوباره ارسال نمایید."
        )
        return MISSION # در همین حالت می‌مانیم

    context.user_data['prompt_data']['persona'] = persona
    message = f"**سوال ۲ از ۵: مأموریت (Mission) 🎯** (حداکثر {MAX_INPUT_LENGTH} کاراکتر)\nمأموریت اصلی شما چیست؟ (چه خروجی‌ای می‌خواهید؟)"
    await update.message.reply_text(message)
    return CONTEXT


async def get_mission(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۲ (مأموریت) و پرسیدن سوال ۳."""
    mission = update.message.text
    
    if not check_length(mission):
        await update.message.reply_text(
            f"❌ **خطا:** ورودی شما ({len(mission)} کاراکتر) بیش از حد طولانی است. "
            f"لطفاً پاسخ خود را حداکثر به {MAX_INPUT_LENGTH} کاراکتر محدود کنید و دوباره ارسال نمایید."
        )
        return CONTEXT # در همین حالت می‌مانیم

    context.user_data['prompt_data']['mission'] = mission
    message = f"**سوال ۳ از ۵: زمینه کار (Context) 📚** (حداکثر {MAX_INPUT_LENGTH} کاراکتر)\nزمینه یا شرایط خاصی که باید در نظر گرفته شود؟ (مثلاً برای یک شرکت استارتاپی، یا برای یک مخاطب خاص)"
    await update.message.reply_text(message)
    return FORMAT_OUTPUT


async def get_context(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۳ (زمینه کار) و پرسیدن سوال ۴."""
    context_data = update.message.text
    
    if not check_length(context_data):
        await update.message.reply_text(
            f"❌ **خطا:** ورودی شما ({len(context_data)} کاراکتر) بیش از حد طولانی است. "
            f"لطفاً پاسخ خود را حداکثر به {MAX_INPUT_LENGTH} کاراکتر محدود کنید و دوباره ارسال نمایید."
        )
        return FORMAT_OUTPUT # در همین حالت می‌مانیم

    context.user_data['prompt_data']['context'] = context_data
    message = f"**سوال ۴ از ۵: فرمت خروجی (Output Format) 📄** (حداکثر {MAX_INPUT_LENGTH} کاراکتر)\nفرمت خروجی را مشخص کنید. (مثلاً در قالب JSON، یک جدول مارک‌داون، یک مقاله ۵۰۰ کلمه‌ای)"
    await update.message.reply_text(message)
    return EXTRA_DETAILS


async def get_format_output(update: Update, context: CallbackContext) -> int:
    """دریافت پاسخ سوال ۴ (فرمت خروجی) و پرسیدن سوال ۵."""
    format_output = update.message.text
    
    if not check_length(format_output):
        await update.message.reply_text(
            f"❌ **خطا:** ورودی شما ({len(format_output)} کاراکتر) بیش از حد طولانی است. "
            f"لطفاً پاسخ خود را حداکثر به {MAX_INPUT_LENGTH} کاراکتر محدود کنید و دوباره ارسال نمایید."
        )
        return EXTRA_DETAILS # در همین حالت می‌مانیم

    context.user_data['prompt_data']['format_output'] = format_output
    message = f"**سوال ۵ از ۵: توضیحات و جزئیات نهایی (Final Details) 💡** (حداکثر {MAX_INPUT_LENGTH} کاراکتر)\nهرگونه توضیحات یا جزئیات نهایی که باید به پرامپت اضافه شود. (مثلاً محدودیت‌ها، لحن، یا مثال‌ها)"
    await update.message.reply_text(message)
    return PROMPT_CONFIRMATION


async def generate_prompt(update: Update, context: CallbackContext) -> int:
    """
    دریافت پاسخ سوال ۵ (جزئیات نهایی)، ساخت پرامپت و نمایش دکمه‌های تأیید.
    """
    extra_details = update.message.text
    
    if not check_length(extra_details):
        await update.message.reply_text(
            f"❌ **خطا:** ورودی شما ({len(extra_details)} کاراکتر) بیش از حد طولانی است. "
            f"لطفاً پاسخ خود را حداکثر به {MAX_INPUT_LENGTH} کاراکتر محدود کنید و دوباره ارسال نمایید."
        )
        return PROMPT_CONFIRMATION # در همین حالت می‌مانیم

    context.user_data['prompt_data']['extra_details'] = extra_details
    data = context.user_data['prompt_data']

    # --- ساختاردهی پرامپت داخلی (دستورالعمل‌های مدل) ---
    persian_details = (
        f"**پرسونا:** {data['persona']}.\n"
        f"**مأموریت:** {data['mission']}.\n"
        f"**زمینه:** {data['context']}.\n"
        f"**فرمت خروجی:** {data['format_output']}.\n"
        f"**جزئیات نهایی:** {data['extra_details']}."
    )

    # --- ساخت پرامپت نهایی برای Gemini ---
    final_prompt_to_gemini = (
        "شما یک پرامپت‌نویس حرفه‌ای هوش مصنوعی هستید. بر اساس تمام جزئیات ورودی زیر، "
        "یک پرامپت خلاقانه، حرفه‌ای، جامع و کاملاً بهینه برای یک مدل زبان بزرگ (مثل خودت) بساز. "
        "پرامپت خروجی باید به صورت مستقیم، بدون هیچ مقدمه‌ای، پاراگراف اضافی یا توضیحی، و در زبان فارسی ارائه شود. "
        "پرامپت نهایی باید در نهایت دقت، تمام سرفصل‌های داده شده را در خود جای دهد:\n\n"
        f"**سرفصل‌ها:**\n{persian_details}"
    )
    
    # پیام در فرمت OpenAI برای سازگاری با توابع داخلی
    messages = [{"role": "user", "content": final_prompt_to_gemini}]
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

    return PROMPT_CONFIRMATION


async def handle_prompt_confirmation(update: Update, context: CallbackContext) -> int:
    """مدیریت دکمه‌های تأیید پرامپت خلاقانه و اجرای API."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    
    if query.data == 'confirm_restart':
        await query.message.edit_text("عملیات ساخت پرامپت لغو شد. 🔄")
        context.user_data.clear()
        return await start(update, context) 

    elif query.data == 'confirm_send':
        
        messages_to_ai = context.user_data.get('messages_to_ai')
        if not messages_to_ai:
            await query.message.edit_text("خطا: پرامپت نهایی پیدا نشد. لطفاً از ابتدا شروع کنید.")
            return await start(update, context)

        await query.message.edit_text(f"... **در حال ارسال به {GEMINI_MODEL_TEXT} برای ساخت پرامپت خلاقانه** ... ⏳")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            creative_prompt_response = await call_ai_api(
                messages=messages_to_ai, 
                model_name=GEMINI_MODEL_TEXT,
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

    if TELEGRAM_BOT_TOKEN == "MISSING_TELEGRAM_TOKEN":
        print("❌ خطا: لطفاً متغیر محیطی 'TELEGRAM_BOT_TOKEN_RAW' را در Render تنظیم کنید.")
        return

    if GEMINI_CLIENT is None and GEMINI_API_KEY != "MISSING_GEMINI_KEY":
        # اگر کلید هست ولی ساخت کلاینت ناموفق بوده است
        print("❌ خطا: کلاینت Gemini ساخته نشد. لطفاً از صحت کلید API و نصب بودن 'google-genai' اطمینان حاصل کنید.")
    elif GEMINI_CLIENT is None:
        print("❌ اخطار: متغیر محیطی GEMINI_API_KEY_RAW تنظیم نشده است. ربات بدون اتصال به هوش مصنوعی شروع به کار خواهد کرد.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CallbackQueryHandler(handle_prompt_confirmation, pattern='^confirm_'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern='^admin_user_count$'))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={
            PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_first_input)],
            MISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_persona)],
            CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mission)],
            FORMAT_OUTPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_context)],
            EXTRA_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_output)], 
            PROMPT_CONFIRMATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_prompt),
                CallbackQueryHandler(handle_prompt_confirmation)
            ],
        },

        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    print("✅ ربات در حال اجرا است (Polling Mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

