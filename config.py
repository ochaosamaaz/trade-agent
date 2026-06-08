"""
Configuration for the Trading Agent
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
