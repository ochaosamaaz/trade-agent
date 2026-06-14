"""
Daily Auto-Scanner & Broadcaster for Ciel Agent

Features:
- Automatically scans all pairs at configurable time (default: 00:05 UTC / 07:05 WIB)
- Generates signals for pairs that pass SMC filter
- Broadcasts to subscribed chats/channels
- Includes position sizing recommendation per signal
- Sends daily summary at end of day

Usage:
    scanner = DailyScanner(bot_app, notify_func)
    await scanner.start()
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable, Optional

from config import (
    CRYPTO_PAIRS, FOREX_PAIRS,
    DAILY_SCAN_HOUR, DAILY_SCAN_MINUTE, BROADCAST_CHAT_ID,
    RISK_PER_TRADE_PCT, DEFAULT_ACCOUNT_BALANCE
)
from quantum_engine import QuantumEngine
from data_fetcher import DataFetcher
from pivot_calculator import calculate_pivot_points
from risk_manager import RiskManager

logger = logging.getLogger(__name__)


class DailyScanner:
    """
    Daily auto-scanner that broadcasts signals at market open.
    Scans all pairs, filters by SMC, calculates position size, broadcasts.
    """

    def __init__(self, notify_callback: Callable[..., Awaitable] = None):
        """
        Args:
            notify_callback: Async function(chat_id, message) to send messages
        """
        self.notify_callback = notify_callback
        self.engine = QuantumEngine()
        self.fetcher = DataFetcher()
        self.risk_manager = RiskManager()

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._subscribers: set = set()  # chat_ids to broadcast to
        self._last_scan_date: str = ""

        # Add broadcast chat if configured
        if BROADCAST_CHAT_ID:
            try:
                self._subscribers.add(int(BROADCAST_CHAT_ID))
            except ValueError:
                pass

    # ========== LIFECYCLE ==========

    async def start(self):
        """Start the daily scanner."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"📡 Daily Scanner started (scan at {DAILY_SCAN_HOUR:02d}:{DAILY_SCAN_MINUTE:02d} UTC)")

    async def stop(self):
        """Stop the daily scanner."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("📡 Daily Scanner stopped")

    def add_subscriber(self, chat_id: int):
        """Add a chat to daily broadcast list."""
        self._subscribers.add(chat_id)

    def remove_subscriber(self, chat_id: int):
        """Remove a chat from daily broadcast list."""
        self._subscribers.discard(chat_id)

    def get_subscriber_count(self) -> int:
        return len(self._subscribers)

    # ========== SCHEDULER ==========

    async def _scheduler_loop(self):
        """Background loop that triggers scan at the configured time."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")

                # Check if it's time to scan (and we haven't scanned today)
                if (now.hour == DAILY_SCAN_HOUR and
                    now.minute >= DAILY_SCAN_MINUTE and
                    now.minute < DAILY_SCAN_MINUTE + 5 and
                    self._last_scan_date != today_str):

                    logger.info("📡 Daily scan triggered!")
                    self._last_scan_date = today_str
                    await self.run_daily_scan()

                # Check every 60 seconds
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scanner loop error: {e}")
                await asyncio.sleep(120)

    # ========== SCAN ==========

    async def run_daily_scan(self) -> str:
        """
        Run full daily scan on all pairs.
        Returns formatted message with all signals.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        signals_buy = []
        signals_sell = []
        skipped = []

        # Scan crypto pairs
        for symbol in CRYPTO_PAIRS:
            result = await self._scan_pair(symbol, is_crypto=True)
            if result:
                if result["filtered"]:
                    skipped.append(result)
                elif result["bias"] == "UP":
                    signals_buy.append(result)
                else:
                    signals_sell.append(result)
            await asyncio.sleep(0.3)

        # Scan forex pairs
        for symbol in FOREX_PAIRS:
            result = await self._scan_pair(symbol, is_crypto=False)
            if result:
                if result["filtered"]:
                    skipped.append(result)
                elif result["bias"] == "UP":
                    signals_buy.append(result)
                else:
                    signals_sell.append(result)
            await asyncio.sleep(0.5)

        # Format broadcast message
        message = self._format_daily_broadcast(
            today, signals_buy, signals_sell, skipped
        )

        # Send to all subscribers
        if self._subscribers and self.notify_callback:
            for chat_id in list(self._subscribers):
                try:
                    await self.notify_callback(chat_id, message)
                except Exception as e:
                    logger.error(f"Broadcast error to {chat_id}: {e}")

        return message

    async def _scan_pair(self, symbol: str, is_crypto: bool) -> Optional[dict]:
        """Scan a single pair and return signal data."""
        try:
            data = await self.fetcher.get_analysis_data(symbol, is_crypto=is_crypto)
            if not data:
                return None

            candles = data.get("candles", [])

            signal = self.engine.analyze(
                symbol=symbol,
                current_open=data["current_open"],
                previous_open=data["previous_open"],
                prev_high=data["prev_high"],
                prev_low=data["prev_low"],
                prev_close=data["prev_close"],
                prev_day_high=data["pdh"],
                prev_day_low=data["pdl"],
                candles=candles
            )

            if signal.bias == "NEUTRAL":
                return None

            if not signal.entry_levels:
                return None

            # Get entry info
            entry_name, entry_price = signal.entry_levels[0]

            # Pivot levels for SL/TP
            pivots = calculate_pivot_points(
                data["prev_high"], data["prev_low"], data["prev_close"]
            )

            if signal.bias == "UP":
                sl = pivots["S2"]
                tp = data["pdh"]
                direction = "long"
            else:
                sl = pivots["R2"]
                tp = data["pdl"]
                direction = "short"

            # SMC score
            smc_score = 0
            if signal.smc_analysis:
                smc_score = signal.smc_analysis.confluence_score

            # Position sizing
            pos = self.risk_manager.calculate_position_size(
                entry_price=entry_price,
                stop_loss=sl,
                take_profit=tp,
                symbol=symbol,
                direction=direction,
                is_crypto=is_crypto
            )

            return {
                "symbol": symbol,
                "bias": signal.bias,
                "direction": direction,
                "entry_price": entry_price,
                "entry_type": entry_name,
                "stop_loss": sl,
                "take_profit": tp,
                "smc_score": smc_score,
                "rr_ratio": pos.rr_ratio,
                "position_size": pos.position_size,
                "risk_amount": pos.risk_amount,
                "potential_profit": pos.potential_profit,
                "filtered": signal.smc_filtered,
                "is_crypto": is_crypto,
            }

        except Exception as e:
            logger.error(f"Scan error for {symbol}: {e}")
            return None

    # ========== FORMATTING ==========

    def _format_daily_broadcast(self, timestamp: str, buys: list,
                                 sells: list, skipped: list) -> str:
        """Format the daily scan into a broadcast message."""
        total_signals = len(buys) + len(sells)

        lines = [
            f"🤖 *CIEL AGENT — Daily Scan*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📅 `{timestamp}`",
            f"📊 Signals: `{total_signals}` valid | `{len(skipped)}` filtered",
            f"💰 Risk: `{self.risk_manager.risk_pct}%` per trade (${self.risk_manager.balance:,.0f})",
            f"",
        ]

        # BUY signals
        if buys:
            lines.append("━━━ 📗 *BUY SIGNALS* ━━━")
            lines.append("")
            for s in buys:
                market = "🪙" if s["is_crypto"] else "💱"
                lines.append(
                    f"{market} *{s['symbol']}* — 📗 BUY\n"
                    f"   📍 Entry: `{s['entry_price']}`\n"
                    f"   🎯 TP: `{s['take_profit']}` | 🛑 SL: `{s['stop_loss']}`\n"
                    f"   📊 R:R `1:{s['rr_ratio']}` | SMC: `{s['smc_score']}/100`\n"
                    f"   📦 Size: `{s['position_size']}` | Risk: `${s['risk_amount']:.2f}`"
                )
                lines.append("")

        # SELL signals
        if sells:
            lines.append("━━━ 📕 *SELL SIGNALS* ━━━")
            lines.append("")
            for s in sells:
                market = "🪙" if s["is_crypto"] else "💱"
                lines.append(
                    f"{market} *{s['symbol']}* — 📕 SELL\n"
                    f"   📍 Entry: `{s['entry_price']}`\n"
                    f"   🎯 TP: `{s['take_profit']}` | 🛑 SL: `{s['stop_loss']}`\n"
                    f"   📊 R:R `1:{s['rr_ratio']}` | SMC: `{s['smc_score']}/100`\n"
                    f"   📦 Size: `{s['position_size']}` | Risk: `${s['risk_amount']:.2f}`"
                )
                lines.append("")

        if not buys and not sells:
            lines.append("📭 *Tidak ada signal yang memenuhi kriteria hari ini.*")
            lines.append("SMC filter aktif — hanya signal high-quality yang ditampilkan.")
            lines.append("")

        # Filtered summary
        if skipped:
            filtered_pairs = ", ".join([s["symbol"] for s in skipped[:5]])
            lines.append(f"🚫 _Filtered (low SMC): {filtered_pairs}{'...' if len(skipped) > 5 else ''}_")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚠️ _Bukan financial advice. DYOR & manage risk!_",
            "_Powered by Ciel Agent v2.0_",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_single_signal(s: dict) -> str:
        """Format a single signal for quick display."""
        if s["bias"] == "UP":
            emoji = "📗 BUY"
        else:
            emoji = "📕 SELL"

        return (
            f"{emoji} *{s['symbol']}*\n"
            f"Entry: `{s['entry_price']}` | TP: `{s['take_profit']}` | SL: `{s['stop_loss']}`\n"
            f"R:R `1:{s['rr_ratio']}` | Size: `{s['position_size']}` | SMC: `{s['smc_score']}`"
        )
