# 🔮 Quantum Trading Agent — Telegram Bot

Trading signal bot berbasis **Quantum Physics Trading Theory** untuk Forex & Crypto.

## 📐 Teori

### Quantum Physics Theory:
- **Open Price < Previous Open** → Market akan Sweep PDL (Previous Day Low) → Bias **DOWN**
- **Open Price > Previous Open** → Market akan Sweep PDH (Previous Day High) → Bias **UP**

### Setelah Sweep:
Setelah misi selesai (mengambil PDL/PDH), harga akan mengikuti struktur dan trend.
- DOWN **tidak harus** bearish — bisa rebound setelah sweep PDL
- UP **tidak harus** bullish — bisa pullback setelah sweep PDH

### Entry Setup:
| Bias | Entry Zone | Action |
|------|-----------|--------|
| UP | Pivot (PP) & S1 | BUY |
| DOWN | Pivot (PP) & R1 | SELL |

### Invalidation Rules:
- Jika **DOWN** dan Open sudah **di bawah** Pivot → Entry di Pivot **INVALID**
- Jika **UP** dan Open sudah **di atas** Pivot → Entry di Pivot **INVALID**

## 🚀 Setup

### 1. Clone Repository
```bash
git clone https://github.com/ochaosamaaz/trade-agent.git
cd trade-agent
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment
```bash
cp .env.example .env
# Edit .env dan masukkan Telegram Bot Token
```

### 4. Dapatkan Bot Token
1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot`
3. Ikuti instruksi, copy token yang diberikan
4. Paste ke `.env`

### 5. Jalankan Bot
```bash
python bot.py
```

## 🎮 Commands

| Command | Keterangan |
|---------|-----------|
| `/start` | Welcome message |
| `/crypto BTCUSDT` | Analisis crypto pair |
| `/forex EURUSD` | Analisis forex pair |
| `/pivot H L C` | Hitung pivot manual |
| `/manual PAIR OPEN PREV_OPEN H L C` | Input data manual |
| `/quick` | Quick analysis buttons |
| `/list` | Daftar pair tersedia |
| `/help` | Bantuan lengkap |

## 📊 Supported Pairs

### Crypto (via Binance):
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, AVAXUSDT, DOTUSDT, MATICUSDT

### Forex:
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, USDCHF, EURJPY, GBPJPY, EURGBP, XAUUSD

## 📁 Project Structure

```
trade-agent/
├── bot.py              # Main Telegram bot
├── quantum_engine.py   # Quantum Physics Theory logic
├── pivot_calculator.py # Pivot Point calculations
├── data_fetcher.py     # Market data API fetcher
├── config.py           # Configuration & settings
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## ⚠️ Disclaimer

Bot ini **BUKAN** financial advice. Selalu lakukan riset sendiri (DYOR) sebelum melakukan trading. Gunakan risk management yang baik dan hanya trade dengan uang yang siap Anda kehilangan.

## 📝 License

MIT License
