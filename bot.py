import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import requests
import pandas as pd
import numpy as np
from io import BytesIO

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Credentials ---
TELEGRAM_BOT_TOKEN = "7790080100:AAGwX4riIDhZ9JKn6qnQ1UsDEa4EkNZSlE8"
TWELVE_DATA_API_KEY = "f7249b9c22574caea6d71ac931d3f8e0"
PAYPAL_EMAIL = "susanzeedy4259@gmail.com"
MPESA_PHONE = "0701767822"
BINANCE_BNB = "0x412930bc47da7a7b5929ae8876ac41e7d39bc9e2"
BINANCE_USDT = "TD6TWzH3NW9Phfws6DUDKkpgWLjf9924md"
ADMIN_TELEGRAM_ID = 7239427141

# In-memory user database
users = {}  # {user_id: {"trial_end": datetime, "premium": bool}}

# Forex pairs
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "NZD/USD"]

# --- Helper Functions ---
def is_premium(user_id):
    user = users.get(user_id)
    now = datetime.utcnow()
    if user:
        if user.get("premium") or (user.get("trial_end") and now <= user["trial_end"]):
            return True
    return False

def fetch_historical(pair, interval="1h", outputsize=100):
    try:
        symbol = pair.replace("/", "")
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
        resp = requests.get(url).json()
        values = resp.get("values", [])
        df = pd.DataFrame(values)
        df = df[::-1]  # Oldest first
        df['close'] = df['close'].astype(float)
        return df
    except:
        return pd.DataFrame()

def calculate_indicators(df):
    # Moving Averages
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    return df

def generate_signal(df):
    latest = df.iloc[-1]
    signal = ""
    if latest['MA20'] > latest['MA50']:
        signal += "📈 Bullish Trend\n"
    else:
        signal += "📉 Bearish Trend\n"
    if latest['RSI'] < 30:
        signal += "🟢 Oversold – Possible Buy\n"
    elif latest['RSI'] > 70:
        signal += "🔴 Overbought – Possible Sell\n"
    if latest['MACD'] > latest['Signal']:
        signal += "MACD indicates upward momentum\n"
    else:
        signal += "MACD indicates downward momentum\n"
    entry = latest['close']
    stop_loss = round(entry - 0.0020, 4)
    take_profit = round(entry + 0.0040, 4)
    return f"{signal}Entry: {entry}\nStop Loss: {stop_loss}\nTake Profit: {take_profit}"

def get_chart_image(pair, interval="1h"):
    try:
        chart_url = f"https://api.twelvedata.com/chart?symbol={pair.replace('/','')}&interval={interval}&apikey={TWELVE_DATA_API_KEY}"
        img_resp = requests.get(chart_url)
        return BytesIO(img_resp.content)
    except:
        return None

# --- Bot Commands ---
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        users[user_id] = {"trial_end": datetime.utcnow() + timedelta(days=3), "premium": False}
        trial_msg = "🎉 You have started a 3-day free trial! Enjoy full features."
    else:
        trial_msg = ""
    welcome_text = f"🤖 Welcome to Pro Forex Bot!\n{trial_msg}\n\nUse the buttons below to navigate:"
    keyboard = [
        [InlineKeyboardButton("📈 Signals", callback_data="signals")],
        [InlineKeyboardButton("📊 Charts", callback_data="charts")],
        [InlineKeyboardButton("📰 News", callback_data="news")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(welcome_text, reply_markup=reply_markup)

def signals(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if not is_premium(user_id):
        query.edit_message_text("⚠️ Your trial/premium has expired. Please subscribe to continue.")
        return
    text = ""
    for pair in PAIRS:
        df = fetch_historical(pair)
        if df.empty:
            continue
        df = calculate_indicators(df)
        text += f"💹 {pair}\n{generate_signal(df)}\n\n"
    query.edit_message_text(text)

def charts(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if not is_premium(user_id):
        query.edit_message_text("⚠️ Your trial/premium has expired. Please subscribe to continue.")
        return
    intervals = ["1h", "4h", "1d"]
    buttons = [[InlineKeyboardButton(i, callback_data=f"chart_{i}")] for i in intervals]
    query.edit_message_text("Select chart interval:", reply_markup=InlineKeyboardMarkup(buttons))

def chart_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if not is_premium(user_id):
        query.edit_message_text("⚠️ Your trial/premium has expired.")
        return
    data = query.data
    interval = data.split("_")[1]
    for pair in PAIRS[:3]:
        img = get_chart_image(pair, interval=interval)
        if img:
            query.message.reply_photo(photo=img, caption=f"{pair} - {interval} Chart")

def news(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if not is_premium(user_id):
        query.edit_message_text("⚠️ Your trial/premium has expired. Please subscribe to continue.")
        return
    news_text = "📰 USD News Alert\nEvent: Non-Farm Payrolls\nTime: 14:30 GMT\nImpact: High\nAffected Pairs: USD/JPY, EUR/USD"
    query.edit_message_text(news_text)

def premium(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if is_premium(user_id):
        query.edit_message_text("✅ You already have active premium or trial!")
        return
    keyboard = [
        [InlineKeyboardButton("PayPal", callback_data="pay_paypal")],
        [InlineKeyboardButton("Mpesa", callback_data="pay_mpesa")],
        [InlineKeyboardButton("Binance BNB", callback_data="pay_bnb")],
        [InlineKeyboardButton("Binance USDT", callback_data="pay_usdt")],
    ]
    query.edit_message_text("⚠️ Choose payment method. Admin will approve:", reply_markup=InlineKeyboardMarkup(keyboard))

def payment_request(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    method = query.data.replace("pay_", "")
    context.bot.send_message(ADMIN_TELEGRAM_ID, f"💰 Payment Request\nUser: {user_id}\nMethod: {method}\nApprove with /approve {user_id}")
    query.answer()
    query.edit_message_text(f"✅ Payment request via {method} sent to admin.")

def approve(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_TELEGRAM_ID:
        update.message.reply_text("❌ Unauthorized.")
        return
    if len(context.args) < 1:
        update.message.reply_text("Usage: /approve <user_id>")
        return
    target_id = int(context.args[0])
    if target_id in users:
        users[target_id]["premium"] = True
        users[target_id]["trial_end"] = None
    else:
        users[target_id] = {"premium": True, "trial_end": None}
    update.message.reply_text(f"✅ User {target_id} approved for premium.")

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    if data.startswith("pay_"):
        payment_request(update, context)
    elif data.startswith("chart_"):
        chart_selected(update, context)
    elif data == "signals":
        signals(update, context)
    elif data == "charts":
        charts(update, context)
    elif data == "news":
        news(update, context)
    elif data == "premium":
        premium(update, context)

def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("approve", approve))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()