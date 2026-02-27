import sqlite3
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = "8271855633:AAEOQ0ymg-NFiXHhIu2QtNC3dL_cWtmTwxQ"
ADMIN_ID = 7662708655  # <-- apni Telegram numeric ID dalo

# ---------------- DATABASE ---------------- #

conn = sqlite3.connect("store.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price INTEGER,
    stock INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    utr TEXT UNIQUE,
    screenshot TEXT UNIQUE,
    status TEXT
)
""")

conn.commit()

# ---------------- START ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📦 View Products", callback_data="admin_products")],
            [InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product")],
            [InlineKeyboardButton("📊 Pending Orders", callback_data="admin_pending")]
        ]
        await update.message.reply_text(
            "👑 Admin Panel",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await show_products(update)

# ---------------- SHOW PRODUCTS ---------------- #

async def show_products(update):
    cursor.execute("SELECT * FROM products WHERE stock > 0")
    products = cursor.fetchall()

    if not products:
        await update.message.reply_text("❌ Out of Stock")
        return

    keyboard = []
    for p in products:
        keyboard.append([
            InlineKeyboardButton(
                f"{p[1]} - ₹{p[2]} ({p[3]} left)",
                callback_data=f"buy_{p[0]}"
            )
        ])

    await update.message.reply_text(
        "🛍 Available Products:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------- BUTTON HANDLER ---------------- #

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # BUY PRODUCT
    if data.startswith("buy_"):
        product_id = int(data.split("_")[1])
        context.user_data["product_id"] = product_id

        await query.message.reply_text(
            "💳 Payment karo aur 12 digit UTR bhejo.\n\nPhir screenshot bhejo."
        )

    # ADMIN VIEW PRODUCTS
    elif data == "admin_products" and user_id == ADMIN_ID:
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()

        text = "📦 Products List:\n\n"
        for p in products:
            text += f"{p[1]} | ₹{p[2]} | Stock: {p[3]}\n"

        await query.message.reply_text(text)

    # ADMIN ADD PRODUCT
    elif data == "admin_add_product" and user_id == ADMIN_ID:
        await query.message.reply_text(
            "Format bhejo:\n\nName,Price,Stock\n\nExample:\nCoupon500,20,10"
        )
        context.user_data["adding_product"] = True

    # ADMIN PENDING
    elif data == "admin_pending" and user_id == ADMIN_ID:
        cursor.execute("SELECT * FROM orders WHERE status='pending'")
        orders = cursor.fetchall()

        if not orders:
            await query.message.reply_text("No Pending Orders")
            return

        for order in orders:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{order[0]}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order[0]}")
                ]
            ]
            await query.message.reply_text(
                f"Order ID: {order[0]}\nUTR: {order[3]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # CONFIRM
    elif data.startswith("confirm_") and user_id == ADMIN_ID:
        order_id = int(data.split("_")[1])
        cursor.execute("UPDATE orders SET status='confirmed' WHERE id=?", (order_id,))
        conn.commit()
        await query.message.reply_text("✅ Order Confirmed")

    # REJECT
    elif data.startswith("reject_") and user_id == ADMIN_ID:
        order_id = int(data.split("_")[1])
        cursor.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
        conn.commit()
        await query.message.reply_text("❌ Order Rejected")

# ---------------- TEXT HANDLER ---------------- #

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ADD PRODUCT
    if context.user_data.get("adding_product") and user_id == ADMIN_ID:
        try:
            name, price, stock = text.split(",")
            cursor.execute(
                "INSERT INTO products (name, price, stock) VALUES (?, ?, ?)",
                (name.strip(), int(price), int(stock))
            )
            conn.commit()
            await update.message.reply_text("✅ Product Added")
            context.user_data["adding_product"] = False
        except:
            await update.message.reply_text("❌ Wrong Format")

    # UTR CHECK
    elif re.fullmatch(r"\d{12}", text):
        product_id = context.user_data.get("product_id")

        if not product_id:
            await update.message.reply_text("❌ No product selected")
            return

        context.user_data["utr"] = text

        await update.message.reply_text("📸 Screenshot bhejo")

    else:
        await update.message.reply_text("❌ Invalid Input")

# ---------------- PHOTO HANDLER ---------------- #

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    utr = context.user_data.get("utr")
    product_id = context.user_data.get("product_id")

    if not utr or not product_id:
        return

    file_id = update.message.photo[-1].file_id

    try:
        cursor.execute(
            "INSERT INTO orders (user_id, product_id, utr, screenshot, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, product_id, utr, file_id, "pending")
        )
        conn.commit()

        await update.message.reply_text("✅ Order Submitted for Verification")

        await context.bot.send_message(
            ADMIN_ID,
            f"🆕 New Order\nUser: {user_id}\nUTR: {utr}"
        )

    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ Duplicate UTR or Screenshot Detected")

# ---------------- MAIN ---------------- #

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

app.run_polling()
