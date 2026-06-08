"""
Telegram Trading Bot - Quantum Physics Theory
Main bot file with all command handlers.

Commands:
/start - Welcome message & instructions
/crypto <pair> - Analyze crypto pair (e.g., /crypto BTCUSDT)
/forex <pair> - Analyze forex pair (e.g., /forex EURUSD)
/pivot <H> <L> <C> - Manual pivot calculator
/list - Show supported pairs
/help - Show help message
/manual <pair> <open> <prev_open> <high> <low> <close> - Manual input analysis
/price <pair> - Get real-time price
/alert <pair> <direction> <entry> <sl> <tp> - Set price alert with SL/TP
/myalerts - View your active alerts
/removealert <id> - Remove an alert
/quick - Quick analysis buttons
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN, FOREX_PAIRS, CRYPTO_PAIRS,
    CRYPTO_POLL_INTERVAL, FOREX_POLL_INTERVAL, MAX_ALERTS_PER_USER
)
from quantum_engine import QuantumEngine, QuantumSignal
from pivot_calculator import calculate_pivot_points, format_pivot_table
from data_fetcher import DataFetcher
from price_monitor import PriceMonitor
from alert_manager import AlertManager, AlertStatus

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
engine = QuantumEngine()
fetcher = DataFetcher()
alert_manager: AlertManager = None  # Initialized in post_init
price_monitor: PriceMonitor = None  # Initialized in post_init
app_instance: Application = None    # Reference to bot app for sending messages


# ========== NOTIFICATION CALLBACK ==========

async def send_alert_notification(alert, trigger_type: str, current_price: float):
    """Send Telegram notification when SL/TP is hit."""
    if not app_instance:
        return

    message = AlertManager.format_trigger_notification(alert, trigger_type, current_price)

    try:
        await app_instance.bot.send_message(
            chat_id=alert.chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"📨 Notification sent to chat {alert.chat_id} for {alert.symbol}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


# ========== PRICE UPDATE CALLBACK ==========

async def on_price_update(symbol: str, price: float):
    """Called by PriceMonitor on every price update. Checks alerts."""
    if alert_manager:
        await alert_manager.check_price(symbol, price)


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
        "• /price `BTCUSDT` — Harga real-time\n"
        "• /alert — Set alert SL/TP\n"
        "• /myalerts — Lihat alert aktif\n"
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
        "`/price BTCUSDT` — Harga real-time\n"
        "`/alert BTCUSDT long 67000 66000 69000` — Set alert\n"
        "`/myalerts` — Lihat alert aktif kamu\n"
        "`/removealert A17000001` — Hapus alert\n"
        "`/pivot 1.1050 1.0980 1.1020` — Hitung pivot (H L C)\n"
        "`/manual BTCUSDT 67000 66500 67500 66000 67200` — Full manual\n"
        "`/list` — Lihat semua pair\n"
        "\n"
        "📝 *Format Alert:*\n"
        "`/alert <PAIR> <long/short> <ENTRY> <SL> <TP>`\n"
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


# ========== REAL-TIME PRICE COMMAND ==========

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get real-time price for a pair. Usage: /price BTCUSDT"""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan pair! Contoh: `/price BTCUSDT` atau `/price EURUSD`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    symbol = context.args[0].upper()

    # Determine if crypto or forex
    is_crypto = symbol in CRYPTO_PAIRS
    is_forex = symbol in FOREX_PAIRS

    if not is_crypto and not is_forex:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung. Gunakan /list",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text("⏳ Mengambil harga real-time...")

    if is_crypto:
        # Get 24h stats for richer data
        stats = await fetcher.get_crypto_24h_stats(symbol)
        if stats:
            change_emoji = "🟢" if stats["change_pct"] >= 0 else "🔴"
            message = (
                f"💰 *HARGA REAL-TIME — {symbol}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"💵 Harga: `{stats['price']}`\n"
                f"{change_emoji} 24h: `{stats['change_pct']:+.2f}%`\n"
                f"📈 High 24h: `{stats['high_24h']}`\n"
                f"📉 Low 24h: `{stats['low_24h']}`\n"
                f"🔄 Volume: `{stats['volume']:,.0f}`\n"
                f"🕐 Open: `{stats['open']}`\n"
            )
        else:
            price = await fetcher.get_realtime_price(symbol, is_crypto=True)
            if price:
                message = f"💰 *{symbol}*: `{price}`"
            else:
                message = f"❌ Gagal mengambil harga untuk {symbol}"
    else:
        price = await fetcher.get_realtime_price(symbol, is_crypto=False)
        if price:
            message = (
                f"💱 *HARGA REAL-TIME — {symbol}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"💵 Harga: `{price}`\n"
            )
        else:
            message = f"❌ Gagal mengambil harga forex untuk {symbol}"

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


# ========== ALERT COMMANDS ==========

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set a price alert with SL/TP.
    Usage: /alert <PAIR> <long/short> <ENTRY> <SL> <TP>
    Example: /alert BTCUSDT long 67000 66000 69000
    """
    if not context.args or len(context.args) < 5:
        await update.message.reply_text(
            "🔔 *SET ALERT — Format:*\n"
            "`/alert <PAIR> <long/short> <ENTRY> <SL> <TP>`\n\n"
            "*Contoh:*\n"
            "`/alert BTCUSDT long 67000 66000 69000`\n"
            "`/alert EURUSD short 1.0900 1.0950 1.0800`\n\n"
            "*Keterangan:*\n"
            "• PAIR = Trading pair\n"
            "• long = buy (TP di atas, SL di bawah)\n"
            "• short = sell (TP di bawah, SL di atas)\n"
            "• ENTRY = Harga entry\n"
            "• SL = Stop Loss\n"
            "• TP = Take Profit\n\n"
            "Bot akan kirim notifikasi saat harga menyentuh SL atau TP! 🚨",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        symbol = context.args[0].upper()
        direction = context.args[1].lower()
        entry_price = float(context.args[2])
        stop_loss = float(context.args[3])
        take_profit = float(context.args[4])
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Format salah! Harga harus berupa angka.\n"
            "Contoh: `/alert BTCUSDT long 67000 66000 69000`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Validate direction
    if direction not in ("long", "short"):
        await update.message.reply_text(
            "❌ Direction harus `long` atau `short`!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Validate pair
    is_crypto = symbol in CRYPTO_PAIRS
    is_forex = symbol in FOREX_PAIRS

    if not is_crypto and not is_forex:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung. Gunakan /list",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Validate SL/TP logic
    if direction == "long":
        if take_profit <= entry_price:
            await update.message.reply_text(
                "❌ LONG: Take Profit harus *di atas* Entry price!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if stop_loss >= entry_price:
            await update.message.reply_text(
                "❌ LONG: Stop Loss harus *di bawah* Entry price!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:  # short
        if take_profit >= entry_price:
            await update.message.reply_text(
                "❌ SHORT: Take Profit harus *di bawah* Entry price!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if stop_loss <= entry_price:
            await update.message.reply_text(
                "❌ SHORT: Stop Loss harus *di atas* Entry price!",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Check user alert limit
    user_id = update.effective_user.id
    user_alerts = alert_manager.get_user_alerts(user_id)
    if len(user_alerts) >= MAX_ALERTS_PER_USER:
        await update.message.reply_text(
            f"❌ Maksimal {MAX_ALERTS_PER_USER} alert aktif per user!\n"
            f"Hapus alert lama dengan /removealert <ID>",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Create alert
    alert = alert_manager.create_alert(
        user_id=user_id,
        chat_id=update.effective_chat.id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        is_crypto=is_crypto,
    )

    # Add symbol to price monitor
    if is_crypto:
        price_monitor.add_crypto_symbol(symbol)
    else:
        price_monitor.add_forex_symbol(symbol)

    # Format confirmation
    pnl_tp = abs(take_profit - entry_price) / entry_price * 100
    pnl_sl = abs(stop_loss - entry_price) / entry_price * 100
    rr = pnl_tp / pnl_sl if pnl_sl > 0 else 0
    dir_emoji = "🟢 LONG" if direction == "long" else "🔴 SHORT"

    message = (
        f"✅ *ALERT CREATED!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"📊 {symbol} — {dir_emoji}\n"
        f"📍 Entry: `{entry_price}`\n"
        f"🎯 TP: `{take_profit}` (+{pnl_tp:.2f}%)\n"
        f"🛑 SL: `{stop_loss}` (-{pnl_sl:.2f}%)\n"
        f"📊 R:R = `1:{rr:.1f}`\n"
        f"🆔 ID: `{alert.alert_id}`\n"
        f"\n"
        f"🔔 Kamu akan dinotif saat SL/TP tercapai!\n"
        f"Hapus: `/removealert {alert.alert_id}`"
    )

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def myalerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's active alerts."""
    user_id = update.effective_user.id
    alerts = alert_manager.get_user_alerts(user_id)

    message = alert_manager.format_alert_list(alerts)

    if alerts:
        message += "\n\n💡 Hapus alert: `/removealert <ID>`"

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def removealert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an alert. Usage: /removealert <alert_id>"""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan ID alert! Contoh: `/removealert A17000001`\n"
            "Lihat ID dengan /myalerts",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    alert_id = context.args[0].upper()
    user_id = update.effective_user.id

    success = alert_manager.remove_alert(alert_id, user_id)

    if success:
        await update.message.reply_text(
            f"✅ Alert `{alert_id}` berhasil dihapus!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Alert `{alert_id}` tidak ditemukan atau bukan milikmu.",
            parse_mode=ParseMode.MARKDOWN
        )


# ========== ANALYSIS COMMANDS ==========

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a crypto pair."""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan pair! Contoh: `/crypto BTCUSDT`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    symbol = context.args[0].upper()

    if symbol not in CRYPTO_PAIRS:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung.\n"
            f"Gunakan /list untuk melihat pair yang tersedia.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text("⏳ Mengambil data dan menganalisis...")

    data = await fetcher.get_analysis_data(symbol, is_crypto=True)

    if not data:
        await update.message.reply_text(
            "❌ Gagal mengambil data. Coba lagi nanti atau gunakan /manual."
        )
        return

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

    message = engine.format_signal(signal, pivots)

    # Add real-time price
    rt_price = await fetcher.get_realtime_price(symbol, is_crypto=True)
    if rt_price:
        message += f"\n\n💰 *Harga Saat Ini:* `{rt_price}`"

    message += (
        f"\n\n📈 *Raw Data:*\n"
        f"  Open: `{data['current_open']}`\n"
        f"  Prev Open: `{data['previous_open']}`\n"
        f"  PDH: `{data['pdh']}`\n"
        f"  PDL: `{data['pdl']}`"
    )

    # Add quick alert suggestion
    if signal.entry_levels:
        entry_name, entry_price = signal.entry_levels[0]
        if signal.bias == "UP":
            sl_price = pivots["S2"]
            tp_price = data["pdh"]
            direction = "long"
        else:
            sl_price = pivots["R2"]
            tp_price = data["pdl"]
            direction = "short"
        message += (
            f"\n\n💡 *Quick Alert:*\n"
            f"`/alert {symbol} {direction} {entry_price} {sl_price} {tp_price}`"
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

    if symbol not in FOREX_PAIRS:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung.\n"
            f"Gunakan /list untuk melihat pair yang tersedia.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text("⏳ Mengambil data dan menganalisis...")

    data = await fetcher.get_analysis_data(symbol, is_crypto=False)

    if not data:
        await update.message.reply_text(
            "❌ Gagal mengambil data forex. Gunakan /manual untuk input manual.\n"
            "Contoh: `/manual EURUSD 1.0850 1.0820 1.0900 1.0800 1.0870`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

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

    message = engine.format_signal(signal, pivots)

    # Add real-time price
    rt_price = await fetcher.get_realtime_price(symbol, is_crypto=False)
    if rt_price:
        message += f"\n\n💰 *Harga Saat Ini:* `{rt_price}`"

    message += (
        f"\n\n📈 *Raw Data:*\n"
        f"  Open: `{data['current_open']}`\n"
        f"  Prev Open: `{data['previous_open']}`\n"
        f"  PDH: `{data['pdh']}`\n"
        f"  PDL: `{data['pdl']}`"
    )

    # Add quick alert suggestion
    if signal.entry_levels:
        entry_name, entry_price = signal.entry_levels[0]
        if signal.bias == "UP":
            sl_price = pivots["S2"]
            tp_price = data["pdh"]
            direction = "long"
        else:
            sl_price = pivots["R2"]
            tp_price = data["pdl"]
            direction = "short"
        message += (
            f"\n\n💡 *Quick Alert:*\n"
            f"`/alert {symbol} {direction} {entry_price} {sl_price} {tp_price}`"
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

    pdh = prev_high
    pdl = prev_low

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

    message = engine.format_signal(signal, pivots)

    message += (
        f"\n\n📈 *Input Data:*\n"
        f"  Open Today: `{current_open}`\n"
        f"  Open Yesterday: `{previous_open}`\n"
        f"  H: `{prev_high}` | L: `{prev_low}` | C: `{prev_close}`"
    )

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


# ========== QUICK BUTTONS ==========

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
        [
            InlineKeyboardButton("💰 BTC Price", callback_data="price_BTCUSDT"),
            InlineKeyboardButton("💰 ETH Price", callback_data="price_ETHUSDT"),
            InlineKeyboardButton("💰 XAU Price", callback_data="price_XAUUSD"),
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

    if data.startswith("price_"):
        # Quick price check
        symbol = data.replace("price_", "")
        is_crypto = symbol in CRYPTO_PAIRS

        if is_crypto:
            stats = await fetcher.get_crypto_24h_stats(symbol)
            if stats:
                change_emoji = "🟢" if stats["change_pct"] >= 0 else "🔴"
                message = (
                    f"💰 *{symbol}*\n"
                    f"💵 `{stats['price']}`\n"
                    f"{change_emoji} 24h: `{stats['change_pct']:+.2f}%`\n"
                    f"📈 H: `{stats['high_24h']}` | 📉 L: `{stats['low_24h']}`"
                )
            else:
                message = f"❌ Gagal mengambil harga {symbol}"
        else:
            price = await fetcher.get_realtime_price(symbol, is_crypto=False)
            if price:
                message = f"💱 *{symbol}*: `{price}`"
            else:
                message = f"❌ Gagal mengambil harga {symbol}"

        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("crypto_"):
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

        # Add real-time price
        rt_price = await fetcher.get_realtime_price(symbol, is_crypto=True)
        if rt_price:
            message += f"\n\n💰 *Live:* `{rt_price}`"

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


# ========== LIFECYCLE ==========

async def post_init(application: Application):
    """Called after the application is initialized. Start price monitor."""
    global alert_manager, price_monitor, app_instance

    app_instance = application

    # Initialize alert manager with notification callback
    alert_manager = AlertManager(notify_callback=send_alert_notification)

    # Initialize price monitor
    price_monitor = PriceMonitor(
        on_price_update=on_price_update,
        check_interval=CRYPTO_POLL_INTERVAL
    )

    # Load existing alert symbols into monitor
    crypto_symbols, forex_symbols = alert_manager.get_all_active_symbols()
    for s in crypto_symbols:
        price_monitor.add_crypto_symbol(s)
    for s in forex_symbols:
        price_monitor.add_forex_symbol(s)

    # Start the monitor
    await price_monitor.start()

    active_count = alert_manager.get_active_count()
    logger.info(f"✅ Bot initialized | {active_count} active alerts loaded")


async def post_shutdown(application: Application):
    """Called when application is shutting down."""
    if price_monitor:
        await price_monitor.stop()
    logger.info("👋 Bot shutdown complete")


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
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("crypto", crypto_command))
    app.add_handler(CommandHandler("forex", forex_command))
    app.add_handler(CommandHandler("pivot", pivot_command))
    app.add_handler(CommandHandler("manual", manual_command))
    app.add_handler(CommandHandler("quick", quick_buttons))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("myalerts", myalerts_command))
    app.add_handler(CommandHandler("removealert", removealert_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Error handler
    app.add_error_handler(error_handler)

    # Start polling
    print("🚀 Quantum Trading Agent is running!")
    print("📡 Real-time price monitor: ACTIVE")
    print("🔔 Alert system: ACTIVE")
    print("Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
