import sqlite3, io, qrcode, asyncio, logging
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from PIL import Image

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from bakong_khqr import KHQR

# --- CONFIGURATION ---
TOKEN = "8771476967:AAFVM-HfPJRSsO3I-nZkUcGpd_8rYAZcw88"
ADMIN_ID = 8756326457
BAKONG_TOKEN = "rbkUyfi6Vs2hNb7jBYreOQW7E--qmeFknBwsBYfoTWJ7bs"
MERCHANT_ID = "nyx_shop@bkjr" # ត្រូវប្រាកដថា Account នេះត្រឹមត្រូវ
SHOP_NAME = "Nyx Shop"

khqr_tool = KHQR(BAKONG_TOKEN)
logging.basicConfig(level=logging.INFO)

PLANS = {
    "yt_1m": {"label": "Premium ⭐️ ១ ខែ", "price": 2.50},
    "p_3m":  {"label": "Premium ⭐️ ៣ ខែ", "price": 13.99},
    "p_6m":  {"label": "Premium ⭐️ ៦ ខែ", "price": 18.99},
    "p_1y":  {"label": "Premium ⭐️ ១ ឆ្នាំ", "price": 38.99}
}

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('imdara_shop.db')
    conn.execute('CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id TEXT, info TEXT, is_sold INTEGER DEFAULT 0)')
    conn.execute('CREATE TABLE IF NOT EXISTS sales (md5 TEXT PRIMARY KEY, user_id INTEGER, plan TEXT, date TEXT, price REAL)')
    conn.commit()
    conn.close()

# --- REPLIT KEEP-ALIVE ---
server = Flask('')
@server.route('/')
def home(): return "KHQR SYSTEM ONLINE"
def keep_alive(): Thread(target=lambda: server.run(host='0.0.0.0', port=8080)).start()

# --- AUTO CHECK & DELETE SYSTEM ---
async def start_auto_monitor(context, chat_id, message_id, md5, plan_key):
    start_time = datetime.now()
    while datetime.now() - start_time < timedelta(minutes=5):
        await asyncio.sleep(10)
        try:
            status = khqr_tool.check_payment(md5)
            if status == "PAID":
                conn = sqlite3.connect('imdara_shop.db')
                delivery_txt = ""
                # Auto Delivery Logic
                res = conn.execute("SELECT id, info FROM stock WHERE prod_id=? AND is_sold=0 LIMIT 1", (plan_key,)).fetchone()
                if res:
                    conn.execute("UPDATE stock SET is_sold=1 WHERE id=?", (res[0],))
                    delivery_txt = f"\n\n🔑 **Account:** `{res[1]}`"
                
                conn.execute("INSERT OR IGNORE INTO sales VALUES (?, ?, ?, ?, ?)", 
                             (md5, chat_id, plan_key, datetime.now().strftime("%Y-%m-%d"), PLANS[plan_key]['price']))
                conn.commit()
                conn.close()

                await context.bot.delete_message(chat_id, message_id) # លុប QR ស្វ័យប្រវត្តិ
                await context.bot.send_message(chat_id, f"✅ **ការបង់ប្រាក់ជោគជ័យ!**{delivery_txt}\n\nសូមអរគុណសម្រាប់ការគាំទ្រ!", parse_mode="Markdown")
                await context.bot.send_message(ADMIN_ID, f"💰 **លក់ដាច់:** {PLANS[plan_key]['label']} ទៅកាន់ ID: `{chat_id}`")
                return 
        except: continue
    try: await context.bot.delete_message(chat_id, message_id)
    except: pass

# --- HANDLERS ---
async def start(update, context):
    kb = [[KeyboardButton("💎 ទិញ Premium")], [KeyboardButton("📊 Sales"), KeyboardButton("📦 Stock")]]
    await update.message.reply_text(f"👋 **សូមស្វាគមន៍មកកាន់ {SHOP_NAME}**", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def handle_purchase(update, context):
    query = update.callback_query
    user = query.from_user
    plan_key = query.data.replace('buy_', '')
    plan = PLANS[plan_key]

    # ជូនដំណឹងទៅ Admin
    await context.bot.send_message(ADMIN_ID, f"🔍 **User Checkout:** {user.first_name}\n🆔 `{user.id}`\n📦 {plan['label']}")

    # 1. បង្កើត KHQR String ឱ្យត្រូវតាមស្តង់ដារ
    qr_data = khqr_tool.create_qr(
        bank_account=MERCHANT_ID,
        merchant_name=SHOP_NAME,
        amount=float(plan['price']),
        bill_number=f"INV{int(datetime.now().timestamp())}",
        currency="USD"
    )
    md5_hash = khqr_tool.generate_md5(qr_data)

    # 2. បង្កើតរូបភាព QR (High Quality)
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    await query.message.delete()
    
    # 3. ផ្ញើសារដែលមានរូបភាព និងព័ត៌មានច្បាស់ៗដូចក្នុងរូប
    caption = (
        f"━━━━━━━━━━━━━━━\n"
        f"🛒 **ទិញផលិតផល:** {plan['label']}\n"
        f"💰 **តម្លៃ:** ${plan['price']} USD\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📱 **សូមបើកកម្មវិធី Bakong ឬ App ធនាគាររបស់អ្នកដើម្បី Scan**\n\n"
        f"⚡️ *ប្រព័ន្ធនឹងធ្វើការឆែកការបង់ប្រាក់ និងផ្ញើទំនិញឱ្យស្វ័យប្រវត្តិ*"
    )
    
    sent_msg = await context.bot.send_photo(
        chat_id=user.id,
        photo=buf,
        caption=caption,
        parse_mode="Markdown"
    )

    # ចាប់ផ្តើមឆែកលុយស្វ័យប្រវត្តិ
    asyncio.create_task(start_auto_monitor(context, user.id, sent_msg.message_id, md5_hash, plan_key))

# --- ADMIN CMDS ---
async def admin_stats(update, context):
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect('imdara_shop.db')
    if update.message.text == "📊 Sales":
        today = datetime.now().strftime("%Y-%m-%d")
        res = conn.execute("SELECT COUNT(*), SUM(price) FROM sales WHERE date=?", (today,)).fetchone()
        await update.message.reply_text(f"📊 **លក់បានថ្ងៃនេះ:** {res[0]} ដង\n💵 **ទឹកប្រាក់:** ${res[1] if res[1] else 0}")
    elif update.message.text == "📦 Stock":
        res = conn.execute("SELECT prod_id, COUNT(*) FROM stock WHERE is_sold=0 GROUP BY prod_id").fetchall()
        txt = "📦 **ស្តុកក្នុង Bot:**\n" + "\n".join([f"- {r[0]}: {r[1]}" for r in res])
        await update.message.reply_text(txt if res else "❌ អស់ស្តុក")
    conn.close()

def main():
    init_db(); keep_alive()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text(["📊 Sales", "📦 Stock"]), admin_stats))
    app.add_handler(MessageHandler(filters.Text("💎 ទិញ Premium"), lambda u, c: u.message.reply_text("ជ្រើសរើសគម្រោង៖", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{v['label']} - ${v['price']}", callback_data=f"buy_{k}")] for k, v in PLANS.items()]))))
    app.add_handler(CallbackQueryHandler(handle_purchase, pattern="^buy_"))
    app.run_polling()

if __name__ == '__main__': main()
