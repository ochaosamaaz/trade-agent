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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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
from backtester import Backtester
from paper_trader import PaperTrader
from daily_scanner import DailyScanner
from risk_manager import RiskManager

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
engine = QuantumEngine()
fetcher = DataFetcher()
risk_manager = RiskManager()
alert_manager: AlertManager = None  # Initialized in post_init
price_monitor: PriceMonitor = None  # Initialized in post_init
paper_trader: PaperTrader = None    # Initialized in post_init
daily_scanner: DailyScanner = None  # Initialized in post_init
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
    """Welcome message with bot introduction + persistent bottom keyboard."""
    welcome = (
        "🤖 *CIEL AGENT — AI Trading Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "     _Quantum × Smart Money × Pivot_\n"
        "\n"
        "Selamat datang! Ciel Agent menggunakan *Quantum Physics Theory* "
        "+ *Smart Money Concepts* untuk menganalisis Forex & Crypto secara otomatis.\n"
        "\n"
        "📐 *Strategy:*\n"
        "• Open < Prev Open → 📕 SELL (Sweep PDL)\n"
        "• Open > Prev Open → 📗 BUY (Sweep PDH)\n"
        "• Entry di Pivot + SMC confluence filter\n"
        "\n"
        "👇 *Gunakan tombol di bawah untuk navigasi:*\n"
        "\n"
        "⚠️ _Bukan financial advice. Always DYOR!_\n"
        "_Powered by Ciel Agent v2.0_"
    )

    # Persistent reply keyboard (compact - 3 per row)
    reply_keyboard = [
        ["📊 Crypto", "💱 Forex", "📡 Scan"],
        ["💰 Price", "🔔 Alert", "📝 Paper"],
        ["📐 Risk", "🧪 Backtest", "📖 Tutorial"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard, resize_keyboard=True, is_persistent=True
    )

    await update.message.reply_text(
        welcome, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed help message."""
    help_text = (
        "📖 *BANTUAN — CIEL AGENT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🔮 *Quantum Physics Theory:*\n"
        "Teori ini berdasarkan perbandingan Open Price hari ini vs kemarin:\n"
        "• Jika Open < Previous Open → 📕 SELL (target sweep PDL)\n"
        "• Jika Open > Previous Open → 📗 BUY (target sweep PDH)\n"
        "\n"
        "Setelah misi sweep selesai, harga mengikuti struktur & trend.\n"
        "SELL TIDAK berarti harus bearish — bisa rebound setelah sweep PDL.\n"
        "\n"
        "🏦 *Smart Money Concepts (SMC):*\n"
        "• Market Structure (BOS/ChoCH)\n"
        "• Order Blocks & Fair Value Gaps\n"
        "• Liquidity Sweeps\n"
        "• Confluence Score 0-100 (filter signal)\n"
        "\n"
        "📊 *Entry Setup:*\n"
        "• BUY → Entry di Pivot (PP) dan S1\n"
        "• SELL → Entry di Pivot (PP) dan R1\n"
        "\n"
        "❌ *Invalidation:*\n"
        "• SELL + Open sudah di bawah Pivot → PP invalid\n"
        "• BUY + Open sudah di atas Pivot → PP invalid\n"
        "\n"
        "━━━ *COMMANDS* ━━━\n"
        "\n"
        "*Signal:*\n"
        "`/crypto BTCUSDT` — Signal crypto\n"
        "`/forex EURUSD` — Signal forex\n"
        "`/price BTCUSDT` — Harga real-time\n"
        "`/quick` — Quick analysis buttons\n"
        "\n"
        "*Alert:*\n"
        "`/alert BTCUSDT long 67000 66000 69000`\n"
        "`/myalerts` — Lihat alert aktif\n"
        "`/removealert A17000001` — Hapus alert\n"
        "\n"
        "*Paper Trading:*\n"
        "`/paperstart` — Mulai forward test\n"
        "`/paperjournal` — Lihat stats\n"
        "`/paperscan` — Force scan\n"
        "`/paperstop` — Stop\n"
        "\n"
        "*Tools:*\n"
        "`/backtest BTCUSDT 90` — Cek win rate\n"
        "`/pivot 1.1050 1.0980 1.1020` — Hitung pivot\n"
        "`/manual BTCUSDT 67000 66500 67500 66000 67200`\n"
        "`/list` — Lihat semua pair\n"
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

    # Check alert_manager is ready
    if not alert_manager:
        await update.message.reply_text("❌ Alert system belum siap. Coba lagi dalam beberapa detik.")
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
    if not alert_manager:
        await update.message.reply_text("❌ Alert system belum siap.")
        return

    user_id = update.effective_user.id
    alerts = alert_manager.get_user_alerts(user_id)

    message = alert_manager.format_alert_list(alerts)

    if alerts:
        message += "\n\n💡 Hapus alert: `/removealert <ID>`"

    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def removealert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an alert. Usage: /removealert <alert_id>"""
    if not alert_manager:
        await update.message.reply_text("❌ Alert system belum siap.")
        return

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
        prev_day_low=data["pdl"],
        candles=data.get("candles")
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

    # Add quick alert suggestion (only if not SMC-filtered)
    if signal.entry_levels and not signal.smc_filtered:
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
        prev_day_low=data["pdl"],
        candles=data.get("candles")
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

    # Add quick alert suggestion (only if not SMC-filtered)
    if signal.entry_levels and not signal.smc_filtered:
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


# ========== BACKTEST COMMAND ==========

async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Run a backtest on historical data.
    Usage: /backtest <PAIR> [days]
    Example: /backtest BTCUSDT 90
    """
    if not context.args:
        await update.message.reply_text(
            "📊 *BACKTEST — Format:*\n"
            "`/backtest <PAIR> [DAYS]`\n\n"
            "*Contoh:*\n"
            "`/backtest BTCUSDT` — 30 hari (default)\n"
            "`/backtest BTCUSDT 90` — 90 hari\n"
            "`/backtest EURUSD 60` — Forex 60 hari\n\n"
            "*Info:*\n"
            "• Crypto max 500 hari\n"
            "• Forex max 100 hari (API limit)\n"
            "• Menggunakan data historis real dari Binance/TwelveData",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    symbol = context.args[0].upper()

    # Parse days
    days = 30
    if len(context.args) >= 2:
        try:
            days = int(context.args[1])
            days = max(5, min(days, 500))  # Clamp between 5 and 500
        except ValueError:
            await update.message.reply_text("❌ Jumlah hari harus angka!")
            return

    # Determine market type
    is_crypto = symbol in CRYPTO_PAIRS
    is_forex = symbol in FOREX_PAIRS

    if not is_crypto and not is_forex:
        await update.message.reply_text(
            f"❌ Pair `{symbol}` tidak didukung. Gunakan /list",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Forex limit
    if is_forex and days > 100:
        days = 100
        await update.message.reply_text(
            "⚠️ Forex backtest dibatasi 100 hari (API limit). Menggunakan 100 hari."
        )

    await update.message.reply_text(
        f"⏳ Running backtest: *{symbol}* | *{days} hari*...\n"
        f"Mohon tunggu, ini bisa butuh beberapa detik.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Run backtest
    bt = Backtester()
    result = await bt.run_backtest(symbol, days, is_crypto)

    if not result:
        await update.message.reply_text(
            f"❌ Gagal backtest {symbol}. Data tidak tersedia atau API error.\n"
            f"Coba lagi nanti atau gunakan pair lain.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Format and send result
    message = Backtester.format_result(result)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


# ========== PAPER TRADING COMMANDS ==========

async def paperstart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start paper trading. Subscribes this chat to forward test signals."""
    if not paper_trader:
        await update.message.reply_text("❌ Paper trader tidak tersedia. Restart bot.")
        return

    chat_id = update.effective_chat.id

    if paper_trader.is_subscribed(chat_id):
        await update.message.reply_text(
            "✅ Paper trading sudah aktif di chat ini!\n"
            "Gunakan /paperjournal untuk lihat progress.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse optional pairs
    pairs = None
    if context.args:
        pairs = [p.upper() for p in context.args]
        # Validate
        valid_pairs = []
        for p in pairs:
            if p in CRYPTO_PAIRS or p in FOREX_PAIRS:
                valid_pairs.append(p)
        pairs = valid_pairs if valid_pairs else None

    paper_trader.subscribe(chat_id, pairs)

    pair_count = len(pairs) if pairs else len(CRYPTO_PAIRS) + len(FOREX_PAIRS)

    await update.message.reply_text(
        f"📝 *PAPER TRADING ACTIVATED!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔍 Monitoring: `{pair_count} pairs`\n"
        f"⏰ Scan: Setiap 6 jam (auto)\n"
        f"📊 Filter: SMC score >= 50\n\n"
        f"Bot akan otomatis:\n"
        f"1️⃣ Scan semua pair → kirim signal\n"
        f"2️⃣ Cek hasil (TP/SL) keesokan harinya\n"
        f"3️⃣ Update journal & running stats\n\n"
        f"🎮 *Commands:*\n"
        f"• /paperjournal — Lihat journal & stats\n"
        f"• /paperscan — Force scan sekarang\n"
        f"• /paperstop — Berhenti paper trading\n\n"
        f"_Zero risk — validasi strategy sebelum live!_",
        parse_mode=ParseMode.MARKDOWN
    )


async def paperstop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop paper trading for this chat."""
    if not paper_trader:
        await update.message.reply_text("❌ Paper trader tidak tersedia.")
        return

    chat_id = update.effective_chat.id

    if not paper_trader.is_subscribed(chat_id):
        await update.message.reply_text("❌ Paper trading belum aktif di chat ini.")
        return

    paper_trader.unsubscribe(chat_id)

    await update.message.reply_text(
        "⏹️ Paper trading dihentikan.\n"
        "Data journal tetap tersimpan.\n"
        "Gunakan /paperstart untuk aktifkan lagi.",
        parse_mode=ParseMode.MARKDOWN
    )


async def paperjournal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show paper trading journal and stats."""
    if not paper_trader:
        await update.message.reply_text("❌ Paper trader tidak tersedia.")
        return

    journal = paper_trader.get_journal()
    await update.message.reply_text(journal, parse_mode=ParseMode.MARKDOWN)


async def paperscan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force a paper trading scan now."""
    if not paper_trader:
        await update.message.reply_text("❌ Paper trader tidak tersedia.")
        return

    chat_id = update.effective_chat.id

    if not paper_trader.is_subscribed(chat_id):
        await update.message.reply_text(
            "❌ Aktifkan dulu dengan /paperstart",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text("⏳ Scanning all pairs...")

    # Check open trades first
    resolved = await paper_trader.check_open_trades()
    new_trades = await paper_trader.scan_all_pairs()

    # Format response
    lines = ["📝 *PAPER SCAN COMPLETE*", "━━━━━━━━━━━━━━━━━━━━━━━━━", ""]

    if resolved:
        lines.append(f"📊 *Resolved ({len(resolved)}):*")
        for t in resolved:
            if t.status == "win":
                lines.append(f"  ✅ {t.symbol} | +{t.pnl_pct:.2f}%")
            elif t.status == "loss":
                lines.append(f"  ❌ {t.symbol} | {t.pnl_pct:.2f}%")
            else:
                lines.append(f"  ⏭️ {t.symbol} | no hit")
        lines.append("")

    if new_trades:
        lines.append(f"🆕 *New Signals ({len(new_trades)}):*")
        for t in new_trades:
            emoji = "🟢" if t.bias == "UP" else "🔴"
            lines.append(
                f"  {emoji} {t.symbol} | {t.bias} @ {t.entry_type} | SMC:{t.smc_score}"
            )
        lines.append("")
    else:
        lines.append("📭 Tidak ada signal baru yang memenuhi kriteria SMC")
        lines.append("")

    lines.append(f"📈 Running WR: `{paper_trader.stats.win_rate:.1f}%`")
    lines.append(f"💰 Total PnL: `{paper_trader.stats.total_pnl_pct:+.2f}%`")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ========== DAILY SCAN & RISK COMMANDS ==========

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force a daily scan now. Usage: /scan"""
    if not daily_scanner:
        await update.message.reply_text("❌ Daily scanner tidak tersedia.")
        return

    await update.message.reply_text("⏳ Scanning semua pairs... mohon tunggu.")

    message = await daily_scanner.run_daily_scan()
    # Send to this chat directly (in case not subscribed)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe this chat to daily auto-broadcast. Usage: /subscribe"""
    if not daily_scanner:
        await update.message.reply_text("❌ Daily scanner tidak tersedia.")
        return

    chat_id = update.effective_chat.id
    daily_scanner.add_subscriber(chat_id)

    from config import DAILY_SCAN_HOUR, DAILY_SCAN_MINUTE
    wib_hour = (DAILY_SCAN_HOUR + 7) % 24

    await update.message.reply_text(
        f"✅ *SUBSCRIBED — Daily Auto-Scan*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Chat ini akan menerima broadcast signal otomatis:\n"
        f"⏰ Setiap hari jam `{DAILY_SCAN_HOUR:02d}:{DAILY_SCAN_MINUTE:02d} UTC` "
        f"(`{wib_hour:02d}:{DAILY_SCAN_MINUTE:02d} WIB`)\n"
        f"📊 Semua pair (crypto + forex)\n"
        f"🏦 Hanya signal yang lolos SMC filter\n"
        f"📐 Termasuk position sizing\n\n"
        f"🎮 Commands:\n"
        f"• /scan — Force scan sekarang\n"
        f"• /unsubscribe — Berhenti broadcast\n"
        f"• /setrisk — Atur risk management",
        parse_mode=ParseMode.MARKDOWN
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from daily broadcast."""
    if not daily_scanner:
        await update.message.reply_text("❌ Daily scanner tidak tersedia.")
        return

    chat_id = update.effective_chat.id
    daily_scanner.remove_subscriber(chat_id)
    await update.message.reply_text("✅ Unsubscribed dari daily broadcast.")


async def setrisk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set risk management parameters.
    Usage: /setrisk <balance> <risk_pct>
    Example: /setrisk 1000 1.5
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📐 *RISK MANAGEMENT — Setup*\n"
            "`/setrisk <BALANCE_USD> <RISK_%>`\n\n"
            "*Contoh:*\n"
            "`/setrisk 1000 1` — Balance $1000, risk 1%/trade\n"
            "`/setrisk 5000 0.5` — Balance $5000, risk 0.5%/trade\n"
            "`/setrisk 500 2` — Balance $500, risk 2%/trade\n\n"
            f"*Saat ini:*\n"
            f"💰 Balance: `${risk_manager.balance:,.2f}`\n"
            f"⚠️ Risk: `{risk_manager.risk_pct}%` = `${risk_manager.balance * risk_manager.risk_pct / 100:.2f}`/trade\n"
            f"⚡ Leverage: `{risk_manager.leverage}x`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        balance = float(context.args[0])
        risk_pct = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Harus angka! Contoh: `/setrisk 1000 1.5`",
                                         parse_mode=ParseMode.MARKDOWN)
        return

    if balance < 10:
        await update.message.reply_text("❌ Balance minimal $10")
        return
    if risk_pct < 0.1 or risk_pct > 5:
        await update.message.reply_text("❌ Risk harus antara 0.1% - 5%")
        return

    risk_manager.update_balance(balance)
    risk_manager.update_risk(risk_pct)

    # Also update daily scanner's risk manager
    if daily_scanner:
        daily_scanner.risk_manager.update_balance(balance)
        daily_scanner.risk_manager.update_risk(risk_pct)

    risk_per_trade = balance * risk_pct / 100

    await update.message.reply_text(
        f"✅ *RISK UPDATED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Balance: `${balance:,.2f}`\n"
        f"⚠️ Risk/trade: `{risk_pct}%` = `${risk_per_trade:.2f}`\n"
        f"⚡ Leverage: `{risk_manager.leverage}x`\n\n"
        f"Setiap signal sekarang akan include position size\n"
        f"berdasarkan setting ini.",
        parse_mode=ParseMode.MARKDOWN
    )


async def calcsize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Calculate position size.
    Usage: /calcsize <PAIR> <long/short> <ENTRY> <SL> <TP>
    """
    if not context.args or len(context.args) < 5:
        await update.message.reply_text(
            "📐 *POSITION SIZE CALCULATOR*\n"
            "`/calcsize <PAIR> <long/short> <ENTRY> <SL> <TP>`\n\n"
            "*Contoh:*\n"
            "`/calcsize BTCUSDT long 67000 66000 69000`\n"
            "`/calcsize XAUUSD short 4300 4350 4200`\n"
            "`/calcsize EURUSD long 1.0850 1.0800 1.0950`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        symbol = context.args[0].upper()
        direction = context.args[1].lower()
        entry = float(context.args[2])
        sl = float(context.args[3])
        tp = float(context.args[4])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Format salah!")
        return

    is_crypto = symbol in CRYPTO_PAIRS
    is_forex = symbol in FOREX_PAIRS

    if not is_crypto and not is_forex:
        await update.message.reply_text(f"❌ Pair `{symbol}` tidak didukung.", parse_mode=ParseMode.MARKDOWN)
        return

    pos = risk_manager.calculate_position_size(
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        symbol=symbol,
        direction=direction,
        is_crypto=is_crypto
    )

    message = RiskManager.format_position_size(pos, is_crypto)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


# ========== TUTORIAL COMMAND ==========

async def tutorial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show interactive tutorial with buttons."""
    keyboard = [
        [InlineKeyboardButton("1️⃣ Cara Baca Signal", callback_data="tut_signal")],
        [InlineKeyboardButton("2️⃣ Cara Pasang Alert", callback_data="tut_alert")],
        [InlineKeyboardButton("3️⃣ Paper Trading", callback_data="tut_paper")],
        [InlineKeyboardButton("4️⃣ Risk Management", callback_data="tut_risk")],
        [InlineKeyboardButton("5️⃣ Daily Auto-Scan", callback_data="tut_scan")],
        [InlineKeyboardButton("6️⃣ Backtest Strategy", callback_data="tut_backtest")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📖 *TUTORIAL — CIEL AGENT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "Pilih topik yang ingin dipelajari:\n",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )


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

    # ===== MAIN MENU CALLBACKS =====
    if data == "menu_main":
        keyboard = [
            [
                InlineKeyboardButton("📊 Signal Crypto", callback_data="menu_crypto"),
                InlineKeyboardButton("💱 Signal Forex", callback_data="menu_forex"),
            ],
            [
                InlineKeyboardButton("📡 Scan All", callback_data="menu_scan"),
                InlineKeyboardButton("💰 Cek Harga", callback_data="menu_price"),
            ],
            [
                InlineKeyboardButton("🔔 Alert", callback_data="menu_alert"),
                InlineKeyboardButton("📝 Paper Trade", callback_data="menu_paper"),
            ],
            [
                InlineKeyboardButton("📐 Risk Calc", callback_data="menu_risk"),
                InlineKeyboardButton("🧪 Backtest", callback_data="menu_backtest"),
            ],
            [
                InlineKeyboardButton("📖 Tutorial", callback_data="menu_tutorial"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help"),
            ],
        ]
        await query.edit_message_text(
            "🤖 *CIEL AGENT — Main Menu*\n\n👇 Pilih menu:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_crypto":
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
                InlineKeyboardButton("🪙 ADA", callback_data="crypto_ADAUSDT"),
                InlineKeyboardButton("🪙 AVAX", callback_data="crypto_AVAXUSDT"),
                InlineKeyboardButton("🪙 DOT", callback_data="crypto_DOTUSDT"),
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "📊 *Signal Crypto* — Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_forex":
        keyboard = [
            [
                InlineKeyboardButton("💱 EURUSD", callback_data="forex_EURUSD"),
                InlineKeyboardButton("💱 GBPUSD", callback_data="forex_GBPUSD"),
            ],
            [
                InlineKeyboardButton("💱 USDJPY", callback_data="forex_USDJPY"),
                InlineKeyboardButton("💱 XAUUSD", callback_data="forex_XAUUSD"),
            ],
            [
                InlineKeyboardButton("💱 AUDUSD", callback_data="forex_AUDUSD"),
                InlineKeyboardButton("💱 EURJPY", callback_data="forex_EURJPY"),
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "💱 *Signal Forex* — Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_price":
        keyboard = [
            [
                InlineKeyboardButton("💰 BTC", callback_data="price_BTCUSDT"),
                InlineKeyboardButton("💰 ETH", callback_data="price_ETHUSDT"),
                InlineKeyboardButton("💰 SOL", callback_data="price_SOLUSDT"),
            ],
            [
                InlineKeyboardButton("💰 XAU", callback_data="price_XAUUSD"),
                InlineKeyboardButton("💰 EUR", callback_data="price_EURUSD"),
                InlineKeyboardButton("💰 GBP", callback_data="price_GBPUSD"),
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "💰 *Cek Harga Real-time* — Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_scan":
        await query.edit_message_text("⏳ Scanning semua pairs...")
        if daily_scanner:
            message = await daily_scanner.run_daily_scan()
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text("❌ Scanner tidak tersedia. Gunakan /scan")

    elif data == "menu_alert":
        keyboard = [
            [InlineKeyboardButton("📋 My Alerts", callback_data="action_myalerts")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "🔔 *ALERT SYSTEM*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Set alert dan bot kirim notifikasi otomatis saat SL/TP tercapai.\n\n"
            "*Cara pasang:*\n"
            "`/alert BTCUSDT long 67000 66000 69000`\n\n"
            "*Format:*\n"
            "`/alert <PAIR> <long/short> <ENTRY> <SL> <TP>`\n\n"
            "*Manage:*\n"
            "• /myalerts — Lihat alert aktif\n"
            "• /removealert `ID` — Hapus alert",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "action_myalerts":
        if alert_manager:
            user_id = query.from_user.id
            alerts = alert_manager.get_user_alerts(user_id)
            message = alert_manager.format_alert_list(alerts)
        else:
            message = "❌ Alert system belum siap."
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        await query.edit_message_text(
            message, reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_paper":
        keyboard = [
            [InlineKeyboardButton("▶️ Start Paper", callback_data="action_paperstart")],
            [InlineKeyboardButton("📋 Journal", callback_data="action_paperjournal")],
            [InlineKeyboardButton("📡 Force Scan", callback_data="action_paperscan")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "📝 *PAPER TRADING*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Forward test strategy tanpa risiko real money.\n"
            "Bot otomatis scan, catat signal, cek hasil keesokan hari.\n\n"
            "Pilih action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "action_paperstart":
        if paper_trader:
            chat_id = query.message.chat_id
            paper_trader.subscribe(chat_id)
            await query.edit_message_text(
                "✅ Paper trading AKTIF!\n\nBot akan scan & kirim signal otomatis.\n"
                "Cek progress: /paperjournal",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text("❌ Paper trader tidak tersedia.")

    elif data == "action_paperjournal":
        if paper_trader:
            journal = paper_trader.get_journal()
        else:
            journal = "❌ Paper trader tidak tersedia."
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        await query.edit_message_text(
            journal, reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "action_paperscan":
        if paper_trader:
            await query.edit_message_text("⏳ Scanning...")
            await paper_trader.check_open_trades()
            new_trades = await paper_trader.scan_all_pairs()
            msg = f"✅ Scan selesai! {len(new_trades)} signal baru."
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ Paper trader tidak tersedia.")

    elif data == "menu_risk":
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        await query.edit_message_text(
            "📐 *RISK MANAGEMENT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Balance: `${risk_manager.balance:,.2f}`\n"
            f"⚠️ Risk/trade: `{risk_manager.risk_pct}%` = "
            f"`${risk_manager.balance * risk_manager.risk_pct / 100:.2f}`\n"
            f"⚡ Leverage: `{risk_manager.leverage}x`\n\n"
            "*Commands:*\n"
            "`/setrisk 1000 1` — Set balance & risk %\n"
            "`/calcsize BTCUSDT long 67000 66000 69000`\n\n"
            "_Position size otomatis dihitung di setiap signal._",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_backtest":
        keyboard = [
            [
                InlineKeyboardButton("🪙 BTC 30d", callback_data="bt_BTCUSDT_30"),
                InlineKeyboardButton("🪙 ETH 30d", callback_data="bt_ETHUSDT_30"),
            ],
            [
                InlineKeyboardButton("💱 XAU 60d", callback_data="bt_XAUUSD_60"),
                InlineKeyboardButton("💱 EUR 60d", callback_data="bt_EURUSD_60"),
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "🧪 *BACKTEST*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Cek win rate strategy pada data historis.\n\n"
            "Pilih pair, atau ketik manual:\n"
            "`/backtest BTCUSDT 90`\n\n"
            "Quick backtest:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("bt_"):
        parts = data.replace("bt_", "").split("_")
        symbol = parts[0]
        days = int(parts[1])
        is_crypto = symbol in CRYPTO_PAIRS
        await query.edit_message_text(f"⏳ Backtest {symbol} {days} hari...")
        bt = Backtester()
        result = await bt.run_backtest(symbol, days, is_crypto)
        if result:
            message = Backtester.format_result(result)
        else:
            message = f"❌ Gagal backtest {symbol}"
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)

    elif data == "menu_tutorial":
        keyboard = [
            [InlineKeyboardButton("1️⃣ Cara Baca Signal", callback_data="tut_signal")],
            [InlineKeyboardButton("2️⃣ Cara Pasang Alert", callback_data="tut_alert")],
            [InlineKeyboardButton("3️⃣ Paper Trading", callback_data="tut_paper")],
            [InlineKeyboardButton("4️⃣ Risk Management", callback_data="tut_risk")],
            [InlineKeyboardButton("5️⃣ Daily Auto-Scan", callback_data="tut_scan")],
            [InlineKeyboardButton("6️⃣ Backtest Strategy", callback_data="tut_backtest")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "📖 *TUTORIAL — CIEL AGENT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Pilih topik yang ingin dipelajari:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_help":
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        await query.edit_message_text(
            "❓ *SEMUA COMMANDS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Signal:* /crypto, /forex, /price, /quick\n"
            "*Alert:* /alert, /myalerts, /removealert\n"
            "*Paper:* /paperstart, /paperstop, /paperjournal, /paperscan\n"
            "*Scan:* /scan, /subscribe, /unsubscribe\n"
            "*Risk:* /setrisk, /calcsize\n"
            "*Tools:* /backtest, /pivot, /manual, /list\n"
            "*Info:* /start, /help, /tutorial",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # ===== TUTORIAL CALLBACKS =====
    elif data == "tut_signal":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "1️⃣ *CARA BACA SIGNAL*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Contoh signal:*\n"
            "```\n"
            "🟢🔼 QUANTUM SIGNAL — BTCUSDT\n"
            "📐 Bias: BULLISH BIAS\n"
            "📗 Action: BUY (Long)\n"
            "\n"
            "🎯 Entry Levels:\n"
            "  → Pivot — BUY Zone: 67123\n"
            "  → S1 — BUY Zone: 66890\n"
            "\n"
            "🛡️ Invalidation: Below S2 (66500)\n"
            "🏁 Target: PDH: 67890\n"
            "```\n\n"
            "*Penjelasan:*\n"
            "• 📗 BUY = Beli | 📕 SELL = Jual\n"
            "• Entry = Harga masuk posisi\n"
            "• Invalidation = Kalau kena level ini, signal batal\n"
            "• Target = Take Profit\n"
            "• SMC Score = Kualitas signal (0-100)\n\n"
            "*Cara pakai:*\n"
            "1. Ketik `/crypto BTCUSDT` atau `/forex XAUUSD`\n"
            "2. Baca bias (BUY/SELL)\n"
            "3. Entry di level yang ditunjukkan\n"
            "4. Pasang SL & TP sesuai",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "tut_alert":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "2️⃣ *CARA PASANG ALERT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Alert = Bot kirim notifikasi saat harga kena SL/TP.\n\n"
            "*Step 1:* Dapatkan signal\n"
            "`/crypto BTCUSDT`\n\n"
            "*Step 2:* Copy Quick Alert dari signal, atau ketik:\n"
            "`/alert BTCUSDT long 67000 66000 69000`\n\n"
            "*Format:*\n"
            "`/alert <PAIR> <long/short> <ENTRY> <SL> <TP>`\n\n"
            "• `long` = BUY (TP di atas, SL di bawah)\n"
            "• `short` = SELL (TP di bawah, SL di atas)\n\n"
            "*Step 3:* Tunggu notifikasi!\n"
            "🎯 TP Hit → \"PROFIT +2.5%!\"\n"
            "🛑 SL Hit → \"LOSS -1.0%\"\n\n"
            "*Manage:*\n"
            "• /myalerts — Lihat semua alert\n"
            "• /removealert `ID` — Hapus alert",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "tut_paper":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "3️⃣ *PAPER TRADING (FORWARD TEST)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Test strategy pakai data real TANPA uang asli.\n\n"
            "*Cara pakai:*\n"
            "1. `/paperstart` — Aktifkan\n"
            "2. Bot otomatis scan tiap 6 jam\n"
            "3. Kirim signal baru yang lolos SMC filter\n"
            "4. Keesokan hari cek apakah TP/SL kena\n"
            "5. `/paperjournal` — Lihat running win rate\n\n"
            "*Kenapa penting?*\n"
            "• Validasi strategy sebelum pakai uang real\n"
            "• Lihat actual win rate di market live\n"
            "• Bangun confidence sebelum go live\n\n"
            "*Target:*\n"
            "Jalankan minimal 2-4 minggu.\n"
            "Kalau WR > 50% dan PF > 1.5 → siap live!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "tut_risk":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "4️⃣ *RISK MANAGEMENT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "JANGAN pernah risk lebih dari 1-2% per trade!\n\n"
            "*Setup:*\n"
            "`/setrisk 1000 1`\n"
            "→ Balance $1000, risk 1% = $10 per trade\n\n"
            "*Hitung position size:*\n"
            "`/calcsize BTCUSDT long 67000 66000 69000`\n"
            "→ Bot hitung berapa lot/qty yang aman\n\n"
            "*Rules:*\n"
            "• Risk 1% = Konservatif (recommended)\n"
            "• Risk 2% = Moderate\n"
            "• Risk 3%+ = Agresif (berbahaya!)\n\n"
            "*Contoh:*\n"
            "Balance $1000, risk 1%:\n"
            "• Max loss per trade = $10\n"
            "• Kalau SL 1000 pips dari entry\n"
            "• Maka size = $10 / 1000 = 0.01 lot\n\n"
            "_Signal dari /scan sudah include position size otomatis!_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "tut_scan":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "5️⃣ *DAILY AUTO-SCAN*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot scan SEMUA pairs otomatis tiap hari!\n\n"
            "*Setup:*\n"
            "1. `/subscribe` — Daftar broadcast\n"
            "2. Setiap jam 07:05 WIB, bot kirim signal\n"
            "3. Hanya signal yang lolos SMC filter\n"
            "4. Include position size & risk amount\n\n"
            "*Manual scan:*\n"
            "`/scan` — Force scan sekarang\n\n"
            "*Output-nya:*\n"
            "• List semua BUY signals\n"
            "• List semua SELL signals\n"
            "• Entry, TP, SL, R:R, SMC score\n"
            "• Position size berdasarkan risk setting\n\n"
            "*Stop:*\n"
            "`/unsubscribe` — Berhenti broadcast",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "tut_backtest":
        keyboard = [[InlineKeyboardButton("🔙 Tutorial Menu", callback_data="menu_tutorial")]]
        await query.edit_message_text(
            "6️⃣ *BACKTEST STRATEGY*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Cek performa strategy di data historis.\n\n"
            "*Cara pakai:*\n"
            "`/backtest BTCUSDT 90`\n"
            "→ Test BTCUSDT 90 hari terakhir\n\n"
            "`/backtest XAUUSD 60`\n"
            "→ Test XAUUSD 60 hari\n\n"
            "*Yang ditampilkan:*\n"
            "• Win Rate (%)\n"
            "• Total PnL (%)\n"
            "• Profit Factor\n"
            "• Max Drawdown\n"
            "• R:R ratio\n"
            "• SMC filter stats\n"
            "• Trade log (last 5)\n\n"
            "*Interpretasi:*\n"
            "• WR > 50% + PF > 1.5 = Good\n"
            "• WR > 60% = Excellent\n"
            "• WR < 40% = Perlu evaluasi\n\n"
            "_Catatan: Backtest ≠ future results!_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # ===== PRICE CALLBACKS =====
    elif data.startswith("price_"):
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
            prev_day_low=market_data["pdl"],
            candles=market_data.get("candles")
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
            prev_day_low=market_data["pdl"],
            candles=market_data.get("candles")
        )

        pivots = calculate_pivot_points(
            market_data["prev_high"], market_data["prev_low"], market_data["prev_close"]
        )

        message = engine.format_signal(signal, pivots)
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)


# ========== REPLY KEYBOARD HANDLER ==========

async def handle_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from the persistent reply keyboard."""
    text = update.message.text

    if text == "📊 Crypto":
        keyboard = [
            [
                InlineKeyboardButton("BTC", callback_data="crypto_BTCUSDT"),
                InlineKeyboardButton("ETH", callback_data="crypto_ETHUSDT"),
                InlineKeyboardButton("SOL", callback_data="crypto_SOLUSDT"),
            ],
            [
                InlineKeyboardButton("BNB", callback_data="crypto_BNBUSDT"),
                InlineKeyboardButton("XRP", callback_data="crypto_XRPUSDT"),
                InlineKeyboardButton("DOGE", callback_data="crypto_DOGEUSDT"),
            ],
            [
                InlineKeyboardButton("ADA", callback_data="crypto_ADAUSDT"),
                InlineKeyboardButton("AVAX", callback_data="crypto_AVAXUSDT"),
                InlineKeyboardButton("DOT", callback_data="crypto_DOTUSDT"),
            ],
        ]
        await update.message.reply_text(
            "📊 *Signal Crypto* — Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "💱 Forex":
        keyboard = [
            [
                InlineKeyboardButton("EURUSD", callback_data="forex_EURUSD"),
                InlineKeyboardButton("GBPUSD", callback_data="forex_GBPUSD"),
            ],
            [
                InlineKeyboardButton("XAUUSD", callback_data="forex_XAUUSD"),
                InlineKeyboardButton("USDJPY", callback_data="forex_USDJPY"),
            ],
            [
                InlineKeyboardButton("AUDUSD", callback_data="forex_AUDUSD"),
                InlineKeyboardButton("EURJPY", callback_data="forex_EURJPY"),
            ],
        ]
        await update.message.reply_text(
            "💱 *Signal Forex* — Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "📡 Scan":
        if not daily_scanner:
            await update.message.reply_text("❌ Scanner tidak tersedia.")
            return
        await update.message.reply_text("⏳ Scanning semua pairs...")
        message = await daily_scanner.run_daily_scan()
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    elif text == "💰 Price":
        keyboard = [
            [
                InlineKeyboardButton("BTC", callback_data="price_BTCUSDT"),
                InlineKeyboardButton("ETH", callback_data="price_ETHUSDT"),
                InlineKeyboardButton("SOL", callback_data="price_SOLUSDT"),
            ],
            [
                InlineKeyboardButton("XAU", callback_data="price_XAUUSD"),
                InlineKeyboardButton("EUR", callback_data="price_EURUSD"),
                InlineKeyboardButton("GBP", callback_data="price_GBPUSD"),
            ],
        ]
        await update.message.reply_text(
            "💰 *Harga Real-time* — Pilih:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "🔔 Alert":
        await update.message.reply_text(
            "🔔 *ALERT SYSTEM*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot notif otomatis saat SL/TP tercapai.\n\n"
            "*Pasang:*\n"
            "`/alert BTCUSDT long 67000 66000 69000`\n\n"
            "*Manage:*\n"
            "• /myalerts — Lihat aktif\n"
            "• /removealert `ID` — Hapus\n\n"
            "💡 _Signal sudah include Quick Alert!_",
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "📝 Paper":
        keyboard = [
            [InlineKeyboardButton("▶️ Start", callback_data="action_paperstart")],
            [InlineKeyboardButton("📋 Journal", callback_data="action_paperjournal")],
            [InlineKeyboardButton("📡 Scan", callback_data="action_paperscan")],
        ]
        await update.message.reply_text(
            "📝 *PAPER TRADING*\n\nForward test tanpa risiko.\n\nPilih:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "📐 Risk":
        await update.message.reply_text(
            "📐 *RISK MANAGEMENT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Balance: `${risk_manager.balance:,.2f}`\n"
            f"⚠️ Risk: `{risk_manager.risk_pct}%` = "
            f"`${risk_manager.balance * risk_manager.risk_pct / 100:.2f}`/trade\n"
            f"⚡ Leverage: `{risk_manager.leverage}x`\n\n"
            "*Set:* `/setrisk 1000 1`\n"
            "*Calc:* `/calcsize BTCUSDT long 67000 66000 69000`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "🧪 Backtest":
        keyboard = [
            [
                InlineKeyboardButton("BTC 30d", callback_data="bt_BTCUSDT_30"),
                InlineKeyboardButton("ETH 30d", callback_data="bt_ETHUSDT_30"),
            ],
            [
                InlineKeyboardButton("XAU 60d", callback_data="bt_XAUUSD_60"),
                InlineKeyboardButton("EUR 60d", callback_data="bt_EURUSD_60"),
            ],
        ]
        await update.message.reply_text(
            "🧪 *BACKTEST* — Pilih atau ketik `/backtest PAIR DAYS`:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "📖 Tutorial":
        keyboard = [
            [InlineKeyboardButton("1️⃣ Baca Signal", callback_data="tut_signal")],
            [InlineKeyboardButton("2️⃣ Pasang Alert", callback_data="tut_alert")],
            [InlineKeyboardButton("3️⃣ Paper Trading", callback_data="tut_paper")],
            [InlineKeyboardButton("4️⃣ Risk Mgmt", callback_data="tut_risk")],
            [InlineKeyboardButton("5️⃣ Auto-Scan", callback_data="tut_scan")],
            [InlineKeyboardButton("6️⃣ Backtest", callback_data="tut_backtest")],
        ]
        await update.message.reply_text(
            "📖 *TUTORIAL* — Pilih topik:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )


# ========== LIFECYCLE ==========

async def send_paper_notification(chat_id: int, message: str):
    """Send paper trading notification to a chat."""
    if not app_instance:
        return
    try:
        await app_instance.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Paper notify error: {e}")


async def post_init(application: Application):
    """Called after the application is initialized. Start price monitor."""
    global alert_manager, price_monitor, paper_trader, app_instance

    app_instance = application

    # Initialize alert manager FIRST (other commands depend on it)
    alert_manager = AlertManager(notify_callback=send_alert_notification)

    # Initialize price monitor
    try:
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

        await price_monitor.start()
    except Exception as e:
        logger.error(f"Price monitor init error: {e}")

    # Initialize paper trader (non-critical — don't crash bot if this fails)
    try:
        paper_trader = PaperTrader(notify_callback=send_paper_notification)
        await paper_trader.start()
    except Exception as e:
        logger.error(f"Paper trader init error: {e}")

    # Initialize daily scanner
    try:
        daily_scanner = DailyScanner(notify_callback=send_paper_notification)
        await daily_scanner.start()
    except Exception as e:
        logger.error(f"Daily scanner init error: {e}")

    active_count = alert_manager.get_active_count()
    paper_subs = len(paper_trader.subscribers) if paper_trader else 0
    logger.info(f"✅ Bot initialized | {active_count} alerts | {paper_subs} paper subs")


async def post_shutdown(application: Application):
    """Called when application is shutting down."""
    if price_monitor:
        await price_monitor.stop()
    if paper_trader:
        await paper_trader.stop()
    if daily_scanner:
        await daily_scanner.stop()
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
    app.add_handler(CommandHandler("backtest", backtest_command))
    app.add_handler(CommandHandler("paperstart", paperstart_command))
    app.add_handler(CommandHandler("paperstop", paperstop_command))
    app.add_handler(CommandHandler("paperjournal", paperjournal_command))
    app.add_handler(CommandHandler("paperscan", paperscan_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("setrisk", setrisk_command))
    app.add_handler(CommandHandler("calcsize", calcsize_command))
    app.add_handler(CommandHandler("tutorial", tutorial_command))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(
            r"^(📊 Crypto|💱 Forex|📡 Scan|💰 Price|"
            r"🔔 Alert|📝 Paper|📐 Risk|🧪 Backtest|📖 Tutorial)$"
        ),
        handle_keyboard_buttons
    ))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Error handler
    app.add_error_handler(error_handler)

    # Start polling
    print("🚀 Quantum Trading Agent is running!")
    print("📡 Real-time price monitor: ACTIVE")
    print("🔔 Alert system: ACTIVE")
    print("📝 Paper trading: ACTIVE")
    print("Press Ctrl+C to stop.")

    asyncio.run(_run_bot(app))


async def _run_bot(app: Application):
    """Run the bot using asyncio.run() for Python 3.12+ compatibility."""
    global alert_manager, price_monitor, paper_trader, app_instance

    # Manually initialize if post_init wasn't called
    try:
        async with app:
            # Ensure post_init ran (check alert_manager)
            if not alert_manager:
                logger.info("⚠️ post_init didn't run, initializing manually...")
                await post_init(app)

            await app.start()
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

            # Keep running until interrupted
            stop_event = asyncio.Event()

            import signal as sig
            import sys

            def _stop(*args):
                stop_event.set()

            if sys.platform != "win32":
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig.SIGINT, _stop)
                loop.add_signal_handler(sig.SIGTERM, _stop)
            else:
                # Windows: signal handling via thread
                sig.signal(sig.SIGINT, _stop)
                sig.signal(sig.SIGTERM, _stop)

            try:
                await stop_event.wait()
            except (KeyboardInterrupt, SystemExit):
                pass
            finally:
                print("\n👋 Shutting down...")
                await app.updater.stop()
                await app.stop()
    except Exception as e:
        logger.error(f"Bot run error: {e}")
        raise


if __name__ == "__main__":
    main()
