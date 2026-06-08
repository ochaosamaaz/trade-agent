"""
Telegram Trading Bot - Quantum Physics Theory
Main bot file with all command handlers.

Commands:
/start - Welcome message & instructions
/signal <pair> - Get quantum signal for a specific pair
/crypto <pair> - Analyze crypto pair (e.g., /crypto BTCUSDT)
/forex <pair> - Analyze forex pair (e.g., /forex EURUSD)
/pivot <H> <L> <C> - Manual pivot calculator
/list - Show supported pairs
/help - Show help message
/manual <pair> <open> <prev_open> <high> <low> <close> - Manual input analysis
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, FOREX_PAIRS, CRYPTO_PAIRS
from quantum_engine import QuantumEngine, QuantumSignal
from pivot_calculator import calculate_pivot_points, format_pivot_table
from data_fetcher import DataFetcher

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
engine = QuantumEngine()
fetcher = DataFetcher()


# ========== COMMAND HANDLERS ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with bot introduction."""
    welcome = (
        "🔮 *QUANTUM TRADING AGENT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "Selamat datang! Bot ini menggunakan *Quantum Physics Trading Theory* "
        "untuk menganalisis Forex & Crypto.\n"
        "\n"
        "📐 *Teori:*\n"
        "• Open < Prev Open → Sweep PDL (Down)\n"
        "• Open > Prev Open → Sweep PDH (Up)\n"
        "• Entry di Pivot zones setelah validasi\n"
        "\n"
        "🎮 *Commands:*\n"
        "• /crypto `BTCUSDT` — Analisis crypto\n"
        "• /forex `EURUSD` — Analisis forex\n"
        "• /pivot `H L C` — Hitung pivot manual\n"
        "• /manual — Input data manual\n"
        "• /list — Daftar pair tersedia\n"
        "• /help — Bantuan lengkap\n"
        "\n"
        "⚡ Mulai dengan mengetik /crypto BTCUSDT atau /forex EURUSD\n"
        "\n"
        "⚠️ _Disclaimer: Ini bukan financial advice. Always DYOR!_"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed help message."""
    help_text = (
        "📖 *BANTUAN — QUANTUM TRADING AGENT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🔮 *Quantum Physics Theory:*\n"
        "Teori ini berdasarkan perbandingan Open Price hari ini vs kemarin:\n"
        "• Jika Open < Previous Open → Bias DOWN (target sweep PDL)\n"
        "• Jika Open > Previous Open → Bias UP (target sweep PDH)\n"
        "\n"
        "Setelah misi sweep selesai, harga mengikuti struktur & trend.\n"
        "Down TIDAK berarti harus bearish — bisa rebound setelah sweep PDL.\n"
        "\n"
        "📊 *Entry Setup:*\n"
        "• UP → Entry di Pivot (PP) dan S1 sebagai buy zone\n"
        "• DOWN → Entry di Pivot (PP) dan R1 sebagai sell zone\n"
        "\n"
        "❌ *Invalidation:*\n"
        "• DOWN + Open sudah di bawah Pivot → Entry PP invalid\n"
        "• UP + Open sudah di atas Pivot → Entry PP invalid\n"
        "\n"
        "🎮 *Commands:*\n"
        "`/crypto BTCUSDT` — Signal crypto (auto-fetch data)\n"
        "`/forex EURUSD` — Signal forex (auto-fetch data)\n"
        "`/pivot 1.1050 1.0980 1.1020` — Hitung pivot (H L C)\n"
        "`/manual BTCUSDT 67000 66500 67500 66000 67200` — Full manual\n"
        "`/list` — Lihat semua pair\n"
        "\n"
        "📝 *Format Manual:*\n"
        "`/manual <PAIR> <OPEN> <PREV_OPEN> <HIGH> <LOW> <CLOSE>`\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show supported pairs."""
    crypto_list = " | ".join([f"`{p}`" for p in CRYPTO_PAIRS])
    forex_list = " | ".join([f"`{p}`" for p in FOREX_PAIRS])
    
    text = (
        "📋 *SUPPORTED PAIRS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"🪙 *Crypto:*\n{crypto_list}\n"
        "\n"
        f"💱 *Forex:*\n{forex_list}\n"
        "\n"
        "💡 Gunakan `/crypto <PAIR>` atau `/forex <PAIR>`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a crypto pair."""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan pair! Contoh: `/crypto BTCUSDT`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    symbol = context.args[0].upper()
    
    # Validate pair
    if symbol not in CRYPTO_PAIRS:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung.\n"
            f"Gunakan /list untuk melihat pair yang tersedia.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await update.message.reply_text("⏳ Mengambil data dan menganalisis...")
    
    # Fetch data
    data = await fetcher.get_analysis_data(symbol, is_crypto=True)
    
    if not data:
        await update.message.reply_text(
            "❌ Gagal mengambil data. Coba lagi nanti atau gunakan /manual."
        )
        return
    
    # Run analysis
    signal = engine.analyze(
        symbol=symbol,
        current_open=data["current_open"],
        previous_open=data["previous_open"],
        prev_high=data["prev_high"],
        prev_low=data["prev_low"],
        prev_close=data["prev_close"],
        prev_day_high=data["pdh"],
        prev_day_low=data["pdl"]
    )
    
    pivots = calculate_pivot_points(data["prev_high"], data["prev_low"], data["prev_close"])
    
    # Format and send
    message = engine.format_signal(signal, pivots)
    
    # Add raw data info
    message += (
        f"\n\n📈 *Raw Data:*\n"
        f"  Open: `{data['current_open']}`\n"
        f"  Prev Open: `{data['previous_open']}`\n"
        f"  PDH: `{data['pdh']}`\n"
        f"  PDL: `{data['pdl']}`"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def forex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a forex pair."""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan pair! Contoh: `/forex EURUSD`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    symbol = context.args[0].upper()
    
    # Validate pair
    if symbol not in FOREX_PAIRS:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung.\n"
            f"Gunakan /list untuk melihat pair yang tersedia.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await update.message.reply_text("⏳ Mengambil data dan menganalisis...")
    
    # Fetch data
    data = await fetcher.get_analysis_data(symbol, is_crypto=False)
    
    if not data:
        await update.message.reply_text(
            "❌ Gagal mengambil data forex. Gunakan /manual untuk input manual.\n"
            "Contoh: `/manual EURUSD 1.0850 1.0820 1.0900 1.0800 1.0870`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Run analysis
    signal = engine.analyze(
        symbol=symbol,
        current_open=data["current_open"],
        previous_open=data["previous_open"],
        prev_high=data["prev_high"],
        prev_low=data["prev_low"],
        prev_close=data["prev_close"],
        prev_day_high=data["pdh"],
        prev_day_low=data["pdl"]
    )
    
    pivots = calculate_pivot_points(data["prev_high"], data["prev_low"], data["prev_close"])
    
    # Format and send
    message = engine.format_signal(signal, pivots)
    
    message += (
        f"\n\n📈 *Raw Data:*\n"
        f"  Open: `{data['current_open']}`\n"
        f"  Prev Open: `{data['previous_open']}`\n"
        f"  PDH: `{data['pdh']}`\n"
        f"  PDL: `{data['pdl']}`"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def pivot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate pivot points manually. Usage: /pivot <high> <low> <close>"""
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "❌ Format: `/pivot <HIGH> <LOW> <CLOSE>`\n"
            "Contoh: `/pivot 1.1050 1.0980 1.1020`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        high = float(context.args[0])
        low = float(context.args[1])
        close = float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Harga harus berupa angka!")
        return
    
    pivots = calculate_pivot_points(high, low, close)
    message = format_pivot_table(pivots, "Manual")
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual analysis input.
    Usage: /manual <PAIR> <OPEN> <PREV_OPEN> <HIGH> <LOW> <CLOSE>
    """
    if not context.args or len(context.args) < 6:
        await update.message.reply_text(
            "❌ Format: `/manual <PAIR> <OPEN> <PREV_OPEN> <HIGH> <LOW> <CLOSE>`\n\n"
            "Contoh:\n"
            "`/manual BTCUSDT 67000 66500 67500 66000 67200`\n"
            "`/manual EURUSD 1.0850 1.0820 1.0900 1.0800 1.0870`\n\n"
            "Keterangan:\n"
            "• OPEN = Open hari ini\n"
            "• PREV\\_OPEN = Open kemarin\n"
            "• HIGH = High kemarin\n"
            "• LOW = Low kemarin\n"
            "• CLOSE = Close kemarin",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        symbol = context.args[0].upper()
        current_open = float(context.args[1])
        previous_open = float(context.args[2])
        prev_high = float(context.args[3])
        prev_low = float(context.args[4])
        prev_close = float(context.args[5])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Format salah! Semua harga harus berupa angka.")
        return
    
    # PDH and PDL are the previous day high and low
    pdh = prev_high
    pdl = prev_low
    
    # Run analysis
    signal = engine.analyze(
        symbol=symbol,
        current_open=current_open,
        previous_open=previous_open,
        prev_high=prev_high,
        prev_low=prev_low,
        prev_close=prev_close,
        prev_day_high=pdh,
        prev_day_low=pdl
    )
    
    pivots = calculate_pivot_points(prev_high, prev_low, prev_close)
    
    # Format and send
    message = engine.format_signal(signal, pivots)
    
    message += (
        f"\n\n📈 *Input Data:*\n"
        f"  Open Today: `{current_open}`\n"
        f"  Open Yesterday: `{previous_open}`\n"
        f"  H: `{prev_high}` | L: `{prev_low}` | C: `{prev_close}`"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def quick_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quick analysis buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🪙 BTC", callback_data="crypto_BTCUSDT"),
            InlineKeyboardButton("🪙 ETH", callback_data="crypto_ETHUSDT"),
            InlineKeyboardButton("🪙 SOL", callback_data="crypto_SOLUSDT"),
        ],
        [
            InlineKeyboardButton("🪙 BNB", callback_data="crypto_BNBUSDT"),
            InlineKeyboardButton("🪙 XRP", callback_data="crypto_XRPUSDT"),
            InlineKeyboardButton("🪙 DOGE", callback_data="crypto_DOGEUSDT"),
        ],
        [
            InlineKeyboardButton("💱 EURUSD", callback_data="forex_EURUSD"),
            InlineKeyboardButton("💱 GBPUSD", callback_data="forex_GBPUSD"),
            InlineKeyboardButton("💱 XAUUSD", callback_data="forex_XAUUSD"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚡ *Quick Analysis* — Pilih pair:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("crypto_"):
        symbol = data.replace("crypto_", "")
        await query.edit_message_text("⏳ Menganalisis...")
        
        market_data = await fetcher.get_analysis_data(symbol, is_crypto=True)
        
        if not market_data:
            await query.edit_message_text(f"❌ Gagal mengambil data untuk {symbol}")
            return
        
        signal = engine.analyze(
            symbol=symbol,
            current_open=market_data["current_open"],
            previous_open=market_data["previous_open"],
            prev_high=market_data["prev_high"],
            prev_low=market_data["prev_low"],
            prev_close=market_data["prev_close"],
            prev_day_high=market_data["pdh"],
            prev_day_low=market_data["pdl"]
        )
        
        pivots = calculate_pivot_points(
            market_data["prev_high"], market_data["prev_low"], market_data["prev_close"]
        )
        
        message = engine.format_signal(signal, pivots)
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("forex_"):
        symbol = data.replace("forex_", "")
        await query.edit_message_text("⏳ Menganalisis...")
        
        market_data = await fetcher.get_analysis_data(symbol, is_crypto=False)
        
        if not market_data:
            await query.edit_message_text(
                f"❌ Gagal mengambil data forex untuk {symbol}. Gunakan /manual."
            )
            return
        
        signal = engine.analyze(
            symbol=symbol,
            current_open=market_data["current_open"],
            previous_open=market_data["previous_open"],
            prev_high=market_data["prev_high"],
            prev_low=market_data["prev_low"],
            prev_close=market_data["prev_close"],
            prev_day_high=market_data["pdh"],
            prev_day_low=market_data["pdl"]
        )
        
        pivots = calculate_pivot_points(
            market_data["prev_high"], market_data["prev_low"], market_data["prev_close"]
        )
        
        message = engine.format_signal(signal, pivots)
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ Terjadi error. Coba lagi nanti."
        )


# ========== MAIN ==========

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set!")
        print("Set it in .env file: TELEGRAM_BOT_TOKEN=your_token_here")
        return
    
    # Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("crypto", crypto_command))
    app.add_handler(CommandHandler("forex", forex_command))
    app.add_handler(CommandHandler("pivot", pivot_command))
    app.add_handler(CommandHandler("manual", manual_command))
    app.add_handler(CommandHandler("quick", quick_buttons))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    # Start polling
    print("🚀 Quantum Trading Agent is running!")
    print("Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
