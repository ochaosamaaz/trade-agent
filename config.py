"""
Configuration for Ciel Agent — AI Trading Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Supported pairs
FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "NZDUSD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP",
    "XAUUSD"
]

CRYPTO_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"
]

# Timeframes
DEFAULT_TIMEFRAME = "1d"  # Daily for pivot calculations

# ========== PRICE MONITOR SETTINGS ==========

# How often to check crypto prices (seconds) - via REST polling fallback
CRYPTO_POLL_INTERVAL = 5

# How often to check forex prices (seconds) - rate limited API
FOREX_POLL_INTERVAL = 15

# Maximum alerts per user
MAX_ALERTS_PER_USER = 10

# Alert expiry time (hours) - alerts auto-expire after this
ALERT_EXPIRY_HOURS = 72  # 3 days

# ========== DAILY AUTO-SCAN SETTINGS ==========

# Time to run daily scan (UTC). Default: 00:05 UTC = 07:05 WIB
DAILY_SCAN_HOUR = int(os.getenv("DAILY_SCAN_HOUR", "0"))
DAILY_SCAN_MINUTE = int(os.getenv("DAILY_SCAN_MINUTE", "5"))

# Channel/Group ID for broadcast (optional)
# Get by forwarding a message from channel to @userinfobot
BROADCAST_CHAT_ID = os.getenv("BROADCAST_CHAT_ID", "")

# ========== RISK MANAGEMENT SETTINGS ==========

# Default risk per trade (% of account balance)
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))

# Default account balance (for position sizing calculation)
DEFAULT_ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", "1000.0"))

# Maximum position size (lots for forex, quantity for crypto)
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "1.0"))

# Leverage (for crypto futures / forex)
DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "10"))
