import logging
import sqlite3
import threading
import random
import hashlib
import hmac
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. الإعدادات ---
TOKEN = '8591830873:AAGFtx93_W9jB2EuEy84t8dOK4WsfmG1eDQ' # ضع التوكن هنا
ADMIN_ID = 8410208108 # ضع رقم الآيدي الخاص بك
BOT_USERNAME = 'ichancey_cash_bot'

SYRIATEL_NUMBER = "43117338"
CURRENCY = "ل.س"
MIN_DEPOSIT = 300
MIN_WITHDRAW = 100
MIN_BALANCE_TO_SPIN = 2000
SPIN_COST = 2000

WEB_APP_URL = "https://abdallasaobe-lab.github.io/whill-spin11/" 

# --- 2. قاعدة البيانات ---
DB_FILE = 'wheel_final.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE users ADD COLUMN free_spin INTEGER DEFAULT 0")
    except:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        password TEXT,
        balance INTEGER DEFAULT 0, 
        last_deposit INTEGER DEFAULT 0,
        free_spin INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        type TEXT, 
        amount INTEGER, 
        status TEXT, 
        details TEXT, 
        date TEXT
    )''')
    conn.commit()
    conn.close()

init_db()
logging.basicConfig(level=logging.INFO)

# --- 3. إعدادات اللعبة ---
PRIZES = [
    {"name": "5,000,000", "type": "jackpot", "chance": 1},
    {"name": "آيفون 15", "type": "phone", "chance": 2},
    {"name": "1,000,000", "type": "cash", "amount": 1000000, "chance": 5},
    {"name": "سامسونج S24", "type": "phone", "chance": 3},
    {"name": "500,000", "type": "cash", "amount": 500000, "chance": 8},
    {"name": "ساعة ذكية", "type": "gadget", "chance": 8},
    {"name": "لفة مجانية", "type": "free_spin", "chance": 10},
    {"name": "AirPods", "type": "gadget", "chance": 10},
    {"name": "100,000", "type": "cash", "amount": 100000, "chance": 15},
    {"name": "حظ أوفر", "type": "lose", "chance": 38},
]

# --- 4. واجهات المفاتيح ---
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎡 العب عجلة الحظ", callback_data='play')],
        [InlineKeyboardButton("👤 حسابي", callback_data='profile'), InlineKeyboardButton("📜 السجل", callback_data='history')],
        [InlineKeyboardButton("💳 شحن الرصيد", callback_data='deposit'), InlineKeyboardButton("💸 سحب", callback_data='withdraw')],
        [InlineKeyboardButton("💎 استرداد 10%", callback_data='bonus')],
        [InlineKeyboardButton("📞 الدعم", callback_data='support')]
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')]])

def play_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 افتح العجلة", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')]
    ])

def get_user(user_id):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT balance, username, password, last_deposit, free_spin FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()
    finally:
        conn.close()

# --- 5. سيرفر الويب (Flask) ---
app_flask = Flask(__name__)

# === 1. الرابط الخاص بجلب بيانات المستخدم (أضفناه للتواصل مع العجلة) ===
@app_flask.route('/api/get_me', methods=['POST'])
def api_get_me():
    data = request.json
    user_id = str(data.get('user_id'))
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT balance, free_spin FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        
        if user:
            return jsonify({
                "success": True,
                "balance": user['balance'],
                "has_free_spin": user['free_spin'] == 1
            })
        else:
            return jsonify({"success": False, "message": "User not found"})
    finally:
        conn.close()

# === 2. الرابط الخاص بالدوران ===
@app_flask.route('/api/spin', methods=['POST'])
def handle_spin():
    data = request.json
    user_id = str(data.get('user_id'))
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT balance, free_spin FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404
        
        balance = user['balance']
        has_free = user['free_spin'] == 1
        is_free_spin = data.get('is_free_spin', False)

        if not is_free_spin and balance < SPIN_COST:
            return jsonify({"success": False, "message": "Insufficient balance"}), 400

        new_balance = balance
        if is_free_spin:
            c.execute("UPDATE users SET free_spin = 0 WHERE user_id = ?", (user_id,))
            has_free = False
        else:
            new_balance -= SPIN_COST
        
        # اختيار الجائزة
        total_chance = sum(p['chance'] for p in PRIZES)
        rand_num = random.randint(1, total_chance)
        current_sum = 0
        prize_index = 9
        
        for i, p in enumerate(PRIZES):
            current_sum += p['chance']
            if rand_num <= current_sum:
                prize_index = i
                break
        
        prize = PRIZES[prize_index]

        if prize['type'] == 'cash':
            new_balance += prize['amount']
        elif prize['type'] == 'jackpot':
            new_balance += 5000000 
        elif prize['type'] == 'free_spin':
            c.execute("UPDATE users SET free_spin = 1 WHERE user_id = ?", (user_id,))
            has_free = True

        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        conn.commit()

        return jsonify({
            "success": True,
            "prize_index": prize_index,
            "new_balance": new_balance,
            "has_free_spin": has_free
        })
    except Exception as e:
        print(f"Spin Error: {e} - main.py:193")
        return jsonify({"success": False, "message": "Server Error"}), 500
    finally:
        conn.close()

def run_flask():
    app_flask.run(host='0.0.0.0', port=5000, debug=False)

# --- 6. معالجات البوت ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        context.user_data['state'] = 'REG_USER'
        await update.message.reply_text("👋 **أهلاً بك!**\n\nللتسجيل، أرسل **اسم المستخدم** الخاص بك أولاً:")
    else:
        await update.message.reply_text(f"👋 **أهلاً بك مجدداً!**\n\n💰 رصيدك: {user['balance']:,} {CURRENCY}", parse_mode='Markdown', reply_markup=play_kb())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("⚠️ يجب التسجيل أولاً عبر /start")
        return

    balance = user['balance']
    last_deposit = user['last_deposit']
    free_spin = user['free_spin']

    if data == "main_menu":
        await query.edit_message_text(f"🏠 **الرئيسية**\n💰 الرصيد: {balance:,}", parse_mode='Markdown', reply_markup=main_menu_kb())

    elif data == "play":
        free_text = "\n⚠️ لديك لفة مجانية!" if free_spin == 1 else ""
        await query.edit_message_text(f"🎰 **استعد للعب!**\n💰 رصيدك: {balance:,}{free_text}", parse_mode='Markdown', reply_markup=play_kb())

    elif data == "profile":
        text = f"👤 **حسابك**\n\n💳 الرصيد: {balance:,} {CURRENCY}\n📊 آخر شحن: {last_deposit:,}"
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=back_kb())

    elif data == "deposit":
        context.user_data['state'] = 'DEP_AMOUNT'
        await query.edit_message_text(f"💳 **شحن الرصيد**\n\nحول إلى: `{SYRIATEL_NUMBER}`\nالحد الأدنى: {MIN_DEPOSIT:,}\n\nأرسل **المبلغ** الآن:", parse_mode='Markdown', reply_markup=back_kb())

    elif data == "withdraw":
        context.user_data['state'] = 'WIT_WALLET'
        await query.edit_message_text(f"💸 **سحب الأرباح**\n\nرصيدك: {balance:,}\nالحد الأدنى: {MIN_WITHDRAW:,}\n\nأرسل **رقم المحفظة**:", parse_mode='Markdown', reply_markup=back_kb())

    elif data == "bonus":
        if last_deposit > 1000:
            bonus_amount = int(last_deposit * (10 / 100))
            new_balance = balance + bonus_amount
            conn = get_db_connection()
            conn.execute("UPDATE users SET balance = ?, last_deposit = 0 WHERE user_id = ?", (new_balance, user_id))
            conn.commit()
            conn.close()
            await query.edit_message_text(f"🎁 **تهانينا!**\n\nتم إضافة {bonus_amount:,} {CURRENCY} إلى رصيدك.", parse_mode='Markdown', reply_markup=back_kb())
        else:
            await query.answer("❌ لا تستحق المكافأة حالياً.", show_alert=True)

    elif data == "history":
        conn = get_db_connection()
        trans = conn.execute("SELECT type, amount, status FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,)).fetchall()
        conn.close()
        text = "📜 **آخر العمليات:**\n\n"
        for t in trans:
            text += f"{t['type']}: {t['amount']:,} ({t['status']})\n"
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=back_kb())

    elif data == "support":
        context.user_data['state'] = 'SUPPORT_MSG'
        await query.edit_message_text("📞 **أرسل رسالتك الآن:**", reply_markup=back_kb())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    state = context.user_data.get('state')
    
    if state == 'REG_USER':
        context.user_data['temp_user'] = text
        context.user_data['state'] = 'REG_PASS'
        await update.message.reply_text("✅ اسم المستخدم محفوظ.\n\nالآن أرسل **كلمة المرور**:")
        return

    if state == 'REG_PASS':
        username = context.user_data.get('temp_user')
        password = text
        conn = get_db_connection()
        conn.execute("INSERT INTO users (user_id, username, password, balance) VALUES (?, ?, ?, 2000)", (user_id, username, password))
        conn.commit()
        conn.close()
        context.user_data.clear()
        await update.message.reply_text("🎉 **تم التسجيل بنجاح!**\n\nهديتك التسجيل: 2,000 ل.س", reply_markup=play_kb())
        return

    user = get_user(user_id)
    if not user: return

    if state == 'DEP_AMOUNT':
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل الأرقام فقط.")
            return
        amount = int(text)
        if amount < MIN_DEPOSIT:
            await update.message.reply_text(f"❌ الحد الأدنى للشحن {MIN_DEPOSIT}.")
            return
        
        context.user_data['dep_amt'] = amount
        context.user_data['state'] = 'DEP_PROOF'
        await update.message.reply_text(f"💵 المبلغ: {amount:,}\n\nأرسل **صورة الإيصال** أو رقم العملية:", reply_markup=back_kb())
        return

    if state == 'DEP_PROOF':
        amount = context.user_data.get('dep_amt')
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, status, details, date) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, 'شحن', amount, 'pending', text, str(datetime.now())))
        conn.commit()
        t_id = c.lastrowid
        conn.close()
        
        admin_text = f"💳 **طلب شحن جديد**\nUser: `{user_id}`\nAmount: `{amount}`\nProof: `{text}`"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ موافقة", callback_data=f'approve_{t_id}'),
            InlineKeyboardButton("❌ رفض", callback_data=f'reject_{t_id}')
        ]])
        await context.bot.send_message(ADMIN_ID, admin_text, parse_mode='Markdown', reply_markup=kb)
        
        await update.message.reply_text("✅ تم إرسال الطلب للمراجعة.", reply_markup=main_menu_kb())
        context.user_data.clear()
        return

    if state == 'WIT_WALLET':
        context.user_data['wit_wallet'] = text
        context.user_data['state'] = 'WIT_AMT'
        await update.message.reply_text("💳 أرسل **المبلغ** الآن:", reply_markup=back_kb())
        return

    if state == 'WIT_AMT':
        if not text.isdigit():
            await update.message.reply_text("❌ أرقام فقط.")
            return
        amount = int(text)
        if amount < MIN_WITHDRAW or amount > user['balance']:
            await update.message.reply_text(f"❌ خطأ في المبلغ أو رصيد غير كافٍ.")
            return
        
        wallet = context.user_data.get('wit_wallet')
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        c.execute("INSERT INTO transactions (user_id, type, amount, status, details, date) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, 'سحب', amount, 'pending', wallet, str(datetime.now())))
        conn.commit()
        t_id = c.lastrowid
        conn.close()
        
        admin_text = f"💸 **طلب سحب**\nUser: `{user_id}`\nAmount: `{amount}`\nWallet: `{wallet}`"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تم التحويل", callback_data=f'approve_{t_id}'),
            InlineKeyboardButton("❌ رفض", callback_data=f'reject_{t_id}')
        ]])
        await context.bot.send_message(ADMIN_ID, admin_text, parse_mode='Markdown', reply_markup=kb)
        
        await update.message.reply_text("✅ تم إرسال طلب السحب وخصم المبلغ من رصيدك.", reply_markup=main_menu_kb())
        context.user_data.clear()
        return
    
    if state == 'SUPPORT_MSG':
        await context.bot.send_message(ADMIN_ID, f"📞 **دعم** من `{user_id}`:\n\n{text}", parse_mode='Markdown')
        await update.message.reply_text("✅ تم إرسال رسالتك.", reply_markup=main_menu_kb())
        context.user_data.clear()
        return

# --- أوامر الأدمن (موافقة ورفض) ---
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    parts = data.split('_')
    action = parts[0]
    t_id = parts[1]
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id, type, amount, status FROM transactions WHERE id = ?", (t_id,))
        trans = c.fetchone()
        
        if not trans:
            await query.answer("الطلب غير موجود.", show_alert=True)
            return
            
        if trans['status'] != 'pending':
            await query.answer("تمت معالجة هذا الطلب مسبقاً!", show_alert=True)
            return
            
        t_user = trans['user_id']
        t_type = trans['type']
        t_amount = trans['amount']
        
        if action == 'approve':
            if t_type == 'شحن':
                c.execute("UPDATE users SET balance = balance + ?, last_deposit = ? WHERE user_id = ?", (t_amount, t_amount, t_user))
                c.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (t_id,))
                await context.bot.send_message(t_user, f"✅ **تم شحن رصيدك بمبلغ {t_amount:,}**", parse_mode='Markdown')
                
            elif t_type == 'سحب':
                c.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (t_id,))
                await context.bot.send_message(t_user, f"✅ **تم تأكيد سحبك وتحويل المبلغ**", parse_mode='Markdown')
            
            conn.commit()
            await query.edit_message_text(f"✅ تمت معالجة الطلب #{t_id} (موافقة).")

        elif action == 'reject':
            if t_type == 'شحن':
                c.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (t_id,))
                await context.bot.send_message(t_user, f"❌ **تم رفض طلب الشحن**\nالسبب: راجع الدعم.", parse_mode='Markdown')
                
            elif t_type == 'سحب':
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (t_amount, t_user))
                c.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (t_id,))
                await context.bot.send_message(t_user, f"❌ **تم رفض طلب السحب وإعادة المبلغ لرصيدك**", parse_mode='Markdown')
            
            conn.commit()
            await query.edit_message_text(f"❌ تم رفض الطلب #{t_id}.")
            
    except Exception as e:
        print(f"Admin Action Error: {e} - main.py:429")
        await query.answer("حدث خطأ أثناء المعالجة.", show_alert=True)
    finally:
        conn.close()

# --- التشغيل ---
# ... (باقي الكود كما هو) ...

def run_flask():
    # ملاحظة: الاستضافات تعطيك بورت متغير، نستخدم متغير البيئة PORT
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port, debug=False)

# --- التشغيل ---
def main():
    # تشغيل Flask في Thread منفصل
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # تشغيل البوت
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_actions, pattern='^approve_|^reject_'))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))
    
    print("Bot & Server are running on Cloud... - main.py:457")
    app.run_polling()

if __name__ == '__main__':
    main()