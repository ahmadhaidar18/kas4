from dotenv import load_dotenv
import os
import sqlite3
from datetime import datetime

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

# ================= LOAD ENV =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN tidak terbaca")
if ADMIN_ID == 0:
    raise RuntimeError("❌ ADMIN_ID tidak terbaca")
if CHANNEL_ID == 0:
    raise RuntimeError("❌ CHANNEL_ID tidak terbaca")

ADMIN_IDS = [ADMIN_ID]

# ================= DATABASE =================
conn = sqlite3.connect("kas.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS transaksi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal TEXT,
    jenis TEXT,
    jumlah INTEGER,
    keterangan TEXT
)
""")
conn.commit()

# ================= UTIL =================
def rupiah(n: int) -> str:
    return f"{n:,}".replace(",", ".")

def is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_IDS

def get_saldo() -> int:
    cur.execute("""
        SELECT SUM(
            CASE WHEN jenis='MASUK' THEN jumlah ELSE -jumlah END
        ) FROM transaksi
    """)
    r = cur.fetchone()[0]
    return r if r else 0

async def kirim_ke_channel(context, text: str):
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=text,
        parse_mode="Markdown"
    )

# ================= KEYBOARD =================
def menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Pemasukan", callback_data="MASUK"),
            InlineKeyboardButton("🔴 Pengeluaran", callback_data="KELUAR")
        ],
        [
            InlineKeyboardButton("💰 Saldo", callback_data="SALDO"),
            InlineKeyboardButton("📒 Riwayat", callback_data="RIWAYAT")
        ]
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data="MENU")]
    ])

def transaksi_keyboard(trx_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"EDIT_{trx_id}"),
            InlineKeyboardButton("🗑️ Hapus", callback_data=f"HAPUS_{trx_id}")
        ],
        [
            InlineKeyboardButton("⬅️ Kembali", callback_data="MENU")
        ]
    ])

def konfirmasi_hapus_keyboard(trx_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ya", callback_data=f"HAPUSYA_{trx_id}"),
            InlineKeyboardButton("❌ Tidak", callback_data="MENU")
        ]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Akses ditolak")
        return

    await update.message.reply_text(
        "🤖 *BOT KAS BENDAHARA*\n\nLogin berhasil ✅",
        parse_mode="Markdown",
        reply_markup=menu_keyboard()
    )

# ================= CALLBACK =================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not is_admin(update):
        return

    data = q.data

    if data == "MENU":
        await q.message.reply_text(
            "📋 *MENU UTAMA*",
            parse_mode="Markdown",
            reply_markup=menu_keyboard()
        )

    elif data in ("MASUK", "KELUAR"):
        context.user_data.clear()
        context.user_data["jenis"] = data
        await q.message.reply_text(
            "Kirim format:\n`jumlah keterangan`\n\nContoh:\n`50000 iuran`",
            parse_mode="Markdown"
        )

    elif data == "SALDO":
        saldo = get_saldo()
        await kirim_ke_channel(
            context,
            f"💰 *SALDO KAS*\n\nRp {rupiah(saldo)}"
        )
        await q.message.reply_text(
            f"💰 *SALDO SAAT INI*\nRp {rupiah(saldo)}",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )

    elif data == "RIWAYAT":
        cur.execute(
            "SELECT id, tanggal, jenis, jumlah, keterangan FROM transaksi ORDER BY id DESC"
        )
        rows = cur.fetchall()

        if not rows:
            await q.message.reply_text("📒 Belum ada transaksi")
            return

        for r in rows:
            trx_id, tgl, jenis, jml, ket = r
            emoji = "🟢" if jenis == "MASUK" else "🔴"

            text = (
                f"*ID:* {trx_id}\n"
                f"*Tanggal:* {tgl}\n"
                f"*Jenis:* {jenis}\n"
                f"*Jumlah:* {emoji} Rp {rupiah(jml)}\n"
                f"*Ket:* {ket}"
            )

            await q.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=transaksi_keyboard(trx_id)
            )

    elif data.startswith("EDIT_"):
        trx_id = int(data.split("_")[1])
        context.user_data.clear()
        context.user_data["edit_id"] = trx_id

        await q.message.reply_text(
            f"✏️ *Lanjut edit transaksi ID {trx_id}*\n\n"
            "Kirim format:\n`jumlah keterangan`",
            parse_mode="Markdown"
        )

    elif data.startswith("HAPUS_"):
        trx_id = int(data.split("_")[1])
        await q.message.reply_text(
            f"🗑️ *Yakin hapus transaksi ID {trx_id}?*",
            parse_mode="Markdown",
            reply_markup=konfirmasi_hapus_keyboard(trx_id)
        )

    elif data.startswith("HAPUSYA_"):
        trx_id = int(data.split("_")[1])
        cur.execute("DELETE FROM transaksi WHERE id=?", (trx_id,))
        conn.commit()

        await q.message.reply_text(
            "✅ Transaksi berhasil dihapus",
            reply_markup=menu_keyboard()
        )

# ================= INPUT TEXT =================
async def input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    text = update.message.text

    # MODE EDIT
    if "edit_id" in context.user_data:
        trx_id = context.user_data.pop("edit_id")

        try:
            jml, ket = text.split(" ", 1)
            jml = int(jml)
        except:
            await update.message.reply_text("❌ Format salah")
            return

        cur.execute(
            "UPDATE transaksi SET jumlah=?, keterangan=? WHERE id=?",
            (jml, ket, trx_id)
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ Transaksi ID {trx_id} berhasil diupdate",
            reply_markup=menu_keyboard()
        )
        return

    # MODE INPUT BARU
    if "jenis" not in context.user_data:
        return

    try:
        jml, ket = text.split(" ", 1)
        jml = int(jml)
    except:
        await update.message.reply_text("❌ Format salah")
        return

    jenis = context.user_data.pop("jenis")
    tgl = datetime.now().strftime("%d-%m-%Y")

    cur.execute(
        "INSERT INTO transaksi (tanggal, jenis, jumlah, keterangan) VALUES (?,?,?,?)",
        (tgl, jenis, jml, ket)
    )
    conn.commit()

    await update.message.reply_text(
        "✅ Transaksi tersimpan",
        reply_markup=menu_keyboard()
    )

# ================= MAIN =================
if __name__ == "__main__":
    print("🤖 Bot kas bendahara berjalan...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_text))

    app.run_polling()
