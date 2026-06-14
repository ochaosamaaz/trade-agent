"""
Paper Trading / Forward Test Engine

Automatically tracks Quantum + SMC signals each day:
1. At market open (configurable time), scans all pairs and records signals
2. Next day, checks if TP or SL was hit during the session
3. Maintains a performance journal with running stats
4. Sends daily summary to user via Telegram

This is the REAL validation — no hindsight bias, no cherry-picking.
"""

import json
import os
import time
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Awaitable
from datetime import datetime, timezone

from pivot_calculator import calculate_pivot_points
from quantum_engine import QuantumEngine
from data_fetcher import DataFetcher
from smc_engine import SMCEngine
from config import CRYPTO_PAIRS, FOREX_PAIRS

logger = logging.getLogger(__name__)

PAPER_TRADES_FILE = "paper_trades.json"
PAPER_CONFIG_FILE = "paper_config.json"


@dataclass
class PaperTrade:
    """A single paper trade record."""
    trade_id: str
    symbol: str
    is_crypto: bool
    date_opened: str  # YYYY-MM-DD
    bias: str  # UP or DOWN
    entry_price: float
    entry_type: str  # PP, S1, R1
    stop_loss: float
    take_profit: float
    smc_score: int
    smc_structure: str
    status: str = "open"  # open, win, loss, expired, no_hit
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    date_closed: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperTrade":
        return cls(**data)


@dataclass
class PaperStats:
    """Running paper trading statistics."""
    total_signals: int = 0
    total_trades: int = 0  # Signals that passed SMC filter
    wins: int = 0
    losses: int = 0
    no_hit: int = 0  # Neither TP nor SL hit in the day
    smc_filtered: int = 0
    total_pnl_pct: float = 0.0
    win_pnls: list = field(default_factory=list)
    loss_pnls: list = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return (self.wins / total * 100) if total > 0 else 0

    @property
    def avg_win(self) -> float:
        return sum(self.win_pnls) / len(self.win_pnls) if self.win_pnls else 0

    @property
    def avg_loss(self) -> float:
        return sum(self.loss_pnls) / len(self.loss_pnls) if self.loss_pnls else 0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(self.win_pnls) if self.win_pnls else 0
        gross_loss = abs(sum(self.loss_pnls)) if self.loss_pnls else 0
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')


class PaperTrader:
    """
    Forward testing engine.
    Runs alongside the bot to validate strategy in real-time.
    """

    def __init__(self, notify_callback: Callable[..., Awaitable] = None):
        """
        Args:
            notify_callback: Async function(chat_id, message) to send Telegram messages
        """
        self.notify_callback = notify_callback
        self.engine = QuantumEngine()
        self.fetcher = DataFetcher()
        self.smc = SMCEngine()

        self.trades: list[PaperTrade] = []
        self.stats = PaperStats()
        self.subscribers: dict[int, list] = {}  # chat_id -> [pairs]
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._load_state()

    # ========== LIFECYCLE ==========

    async def start(self):
        """Start the paper trading scheduler."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._daily_loop())
        logger.info("📝 Paper Trader started")

    async def stop(self):
        """Stop the paper trading scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
        self._save_state()
        logger.info("📝 Paper Trader stopped")

    # ========== SUBSCRIPTION ==========

    def subscribe(self, chat_id: int, pairs: list = None):
        """
        Subscribe a chat to paper trading.
        If pairs is None, subscribes to all pairs.
        """
        if pairs is None:
            pairs = CRYPTO_PAIRS + FOREX_PAIRS
        self.subscribers[chat_id] = [p.upper() for p in pairs]
        self._save_state()
        logger.info(f"📝 Chat {chat_id} subscribed to paper trading: {len(pairs)} pairs")

    def unsubscribe(self, chat_id: int):
        """Unsubscribe a chat from paper trading."""
        if chat_id in self.subscribers:
            del self.subscribers[chat_id]
            self._save_state()

    def is_subscribed(self, chat_id: int) -> bool:
        return chat_id in self.subscribers

    # ========== DAILY SCAN ==========

    async def scan_all_pairs(self) -> list[PaperTrade]:
        """
        Scan all subscribed pairs, generate signals, record paper trades.
        Called once daily at market open.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_trades = []

        # Collect all unique pairs from subscribers
        all_pairs = set()
        for pairs in self.subscribers.values():
            all_pairs.update(pairs)

        for symbol in all_pairs:
            is_crypto = symbol in CRYPTO_PAIRS

            try:
                # Fetch data
                data = await self.fetcher.get_analysis_data(symbol, is_crypto=is_crypto)
                if not data:
                    continue

                candles = data.get("candles", [])

                # Run Quantum + SMC analysis
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

                self.stats.total_signals += 1

                # Skip neutral
                if signal.bias == "NEUTRAL":
                    continue

                # Skip if no entry levels
                if not signal.entry_levels:
                    continue

                # Check SMC filter
                smc_score = 0
                smc_structure = "unknown"
                if signal.smc_analysis:
                    smc_score = signal.smc_analysis.confluence_score
                    smc_structure = signal.smc_analysis.market_structure

                if signal.smc_filtered:
                    self.stats.smc_filtered += 1
                    continue

                # Record the trade
                entry_name, entry_price = signal.entry_levels[0]

                # Determine SL/TP
                pivots = calculate_pivot_points(
                    data["prev_high"], data["prev_low"], data["prev_close"]
                )

                if signal.bias == "UP":
                    stop_loss = pivots["S2"]
                    take_profit = data["pdh"]
                    entry_type = "PP" if "Pivot" in entry_name else "S1"
                else:
                    stop_loss = pivots["R2"]
                    take_profit = data["pdl"]
                    entry_type = "PP" if "Pivot" in entry_name else "R1"

                trade = PaperTrade(
                    trade_id=f"PT_{symbol}_{today}",
                    symbol=symbol,
                    is_crypto=is_crypto,
                    date_opened=today,
                    bias=signal.bias,
                    entry_price=entry_price,
                    entry_type=entry_type,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    smc_score=smc_score,
                    smc_structure=smc_structure,
                    status="open"
                )

                self.trades.append(trade)
                new_trades.append(trade)
                self.stats.total_trades += 1

            except Exception as e:
                logger.error(f"Paper scan error for {symbol}: {e}")
                continue

            # Small delay between pairs
            await asyncio.sleep(0.5)

        self._save_state()
        return new_trades

    async def check_open_trades(self) -> list[PaperTrade]:
        """
        Check all open paper trades against current day's price action.
        Called at end of day to see if TP/SL was hit.
        """
        resolved = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for trade in self.trades:
            if trade.status != "open":
                continue

            # Skip if just opened today (check tomorrow)
            if trade.date_opened == today:
                continue

            try:
                # Fetch today's candle data
                is_crypto = trade.is_crypto
                if is_crypto:
                    candles = await self.fetcher.fetch_crypto_klines(trade.symbol, "1d", 1)
                else:
                    candles = await self.fetcher.fetch_forex_data(trade.symbol)

                if not candles:
                    continue

                latest = candles[-1]
                day_high = latest.high
                day_low = latest.low

                # Check outcome
                result = self._check_outcome(
                    trade.bias, trade.entry_price, trade.stop_loss,
                    trade.take_profit, day_high, day_low
                )

                if result == "WIN":
                    pnl = abs(trade.take_profit - trade.entry_price) / trade.entry_price * 100
                    trade.status = "win"
                    trade.pnl_pct = round(pnl, 4)
                    trade.exit_price = trade.take_profit
                    trade.date_closed = today
                    self.stats.wins += 1
                    self.stats.win_pnls.append(pnl)
                    self.stats.total_pnl_pct += pnl
                    resolved.append(trade)

                elif result == "LOSS":
                    pnl = abs(trade.entry_price - trade.stop_loss) / trade.entry_price * 100
                    trade.status = "loss"
                    trade.pnl_pct = round(-pnl, 4)
                    trade.exit_price = trade.stop_loss
                    trade.date_closed = today
                    self.stats.losses += 1
                    self.stats.loss_pnls.append(-pnl)
                    self.stats.total_pnl_pct -= pnl
                    resolved.append(trade)

                elif result == "NO_HIT":
                    # Check if trade is older than 2 days → expire
                    if trade.date_opened < today:
                        trade.status = "no_hit"
                        trade.date_closed = today
                        trade.notes = "Neither TP nor SL hit"
                        self.stats.no_hit += 1
                        resolved.append(trade)

            except Exception as e:
                logger.error(f"Paper check error for {trade.symbol}: {e}")
                continue

            await asyncio.sleep(0.3)

        self._save_state()
        return resolved

    def _check_outcome(self, bias: str, entry: float, sl: float,
                       tp: float, high: float, low: float) -> str:
        """Check if TP or SL was hit."""
        if bias == "UP":
            tp_hit = high >= tp
            sl_hit = low <= sl
        else:
            tp_hit = low <= tp
            sl_hit = high >= sl

        if tp_hit and sl_hit:
            # Both hit — conservative: assume loss
            return "LOSS"
        elif tp_hit:
            return "WIN"
        elif sl_hit:
            return "LOSS"
        else:
            return "NO_HIT"

    # ========== DAILY LOOP ==========

    async def _daily_loop(self):
        """Background loop that runs scan + check once per cycle."""
        while self._running:
            try:
                if not self.subscribers:
                    await asyncio.sleep(60)
                    continue

                # Check open trades from previous days
                resolved = await self.check_open_trades()

                # Send notifications for resolved trades
                if resolved:
                    await self._notify_resolved(resolved)

                # Scan for new signals
                new_trades = await self.scan_all_pairs()

                # Send new signal notifications
                if new_trades:
                    await self._notify_new_signals(new_trades)

                # Wait until next cycle (every 6 hours)
                await asyncio.sleep(6 * 3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Paper trader loop error: {e}")
                await asyncio.sleep(300)

    # ========== NOTIFICATIONS ==========

    async def _notify_new_signals(self, trades: list[PaperTrade]):
        """Send new paper trade signals to subscribers."""
        if not self.notify_callback:
            return

        for chat_id, pairs in self.subscribers.items():
            relevant = [t for t in trades if t.symbol in pairs]
            if not relevant:
                continue

            lines = [
                "📝 *PAPER TRADE — New Signals*",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📅 {relevant[0].date_opened}",
                ""
            ]

            for t in relevant:
                if t.bias == "UP":
                    emoji = "🟢"
                    action_label = "BUY"
                else:
                    emoji = "🔴"
                    action_label = "SELL"
                lines.append(
                    f"{emoji} *{t.symbol}* | {action_label} ({t.bias}) @ {t.entry_type}\n"
                    f"   Entry: `{t.entry_price}` | TP: `{t.take_profit}` | SL: `{t.stop_loss}`\n"
                    f"   SMC: `{t.smc_score}/100` | Structure: `{t.smc_structure}`"
                )
                lines.append("")

            lines.append(f"📊 Total open trades: {len([t for t in self.trades if t.status == 'open'])}")
            lines.append("_These are paper trades — no real money at risk_")

            message = "\n".join(lines)
            try:
                await self.notify_callback(chat_id, message)
            except Exception as e:
                logger.error(f"Notify error: {e}")

    async def _notify_resolved(self, trades: list[PaperTrade]):
        """Send resolved trade results to subscribers."""
        if not self.notify_callback:
            return

        for chat_id, pairs in self.subscribers.items():
            relevant = [t for t in trades if t.symbol in pairs]
            if not relevant:
                continue

            wins = [t for t in relevant if t.status == "win"]
            losses = [t for t in relevant if t.status == "loss"]

            lines = [
                "📊 *PAPER TRADE — Results*",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━",
                ""
            ]

            for t in relevant:
                if t.status == "win":
                    lines.append(f"✅ *{t.symbol}* | +{t.pnl_pct:.2f}% | SMC:{t.smc_score}")
                elif t.status == "loss":
                    lines.append(f"❌ *{t.symbol}* | {t.pnl_pct:.2f}% | SMC:{t.smc_score}")
                else:
                    lines.append(f"⏭️ *{t.symbol}* | No hit (expired)")

            # Running stats
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📈 *Running Stats:*",
                f"  🎯 Win Rate: `{self.stats.win_rate:.1f}%`",
                f"  💰 Total PnL: `{self.stats.total_pnl_pct:+.2f}%`",
                f"  📊 Trades: {self.stats.wins}W / {self.stats.losses}L",
                f"  📊 PF: `{self.stats.profit_factor:.2f}`",
            ])

            message = "\n".join(lines)
            try:
                await self.notify_callback(chat_id, message)
            except Exception as e:
                logger.error(f"Notify error: {e}")

    # ========== JOURNAL / STATS ==========

    def get_journal(self, last_n: int = 20) -> str:
        """Format the paper trading journal for display."""
        resolved = [t for t in self.trades if t.status != "open"]
        recent = resolved[-last_n:]

        if not recent and not any(t.status == "open" for t in self.trades):
            return "📝 Paper trading belum aktif. Gunakan /paperstart"

        lines = [
            "📝 *PAPER TRADING JOURNAL*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "📈 *Running Performance:*",
            f"  🎯 Win Rate: `{self.stats.win_rate:.1f}%`",
            f"  💰 Total PnL: `{self.stats.total_pnl_pct:+.2f}%`",
            f"  ✅ Wins: `{self.stats.wins}` | ❌ Losses: `{self.stats.losses}`",
            f"  ⏭️ No Hit: `{self.stats.no_hit}`",
            f"  🏦 SMC Filtered: `{self.stats.smc_filtered}`",
            f"  📊 Profit Factor: `{self.stats.profit_factor:.2f}`",
        ]

        if self.stats.win_pnls:
            lines.append(f"  ✅ Avg Win: `+{self.stats.avg_win:.2f}%`")
        if self.stats.loss_pnls:
            lines.append(f"  ❌ Avg Loss: `{self.stats.avg_loss:.2f}%`")

        # Open trades
        open_trades = [t for t in self.trades if t.status == "open"]
        if open_trades:
            lines.extend(["", "🔄 *Open Trades:*"])
            for t in open_trades:
                if t.bias == "UP":
                    emoji = "🟢"
                    action_label = "BUY"
                else:
                    emoji = "🔴"
                    action_label = "SELL"
                lines.append(f"  {emoji} {t.symbol} | {action_label} @ `{t.entry_price}` | SMC:{t.smc_score}")

        # Recent closed
        if recent:
            lines.extend(["", "📋 *Recent Trades:*"])
            for t in recent[-10:]:
                if t.status == "win":
                    lines.append(f"  ✅ {t.date_opened} | {t.symbol} | +{t.pnl_pct:.2f}%")
                elif t.status == "loss":
                    lines.append(f"  ❌ {t.date_opened} | {t.symbol} | {t.pnl_pct:.2f}%")
                else:
                    lines.append(f"  ⏭️ {t.date_opened} | {t.symbol} | no hit")

        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            "_Paper trading — validating strategy with zero risk_",
        ])

        return "\n".join(lines)

    # ========== PERSISTENCE ==========

    def _save_state(self):
        """Save trades and config to disk."""
        try:
            data = {
                "trades": [t.to_dict() for t in self.trades],
                "stats": {
                    "total_signals": self.stats.total_signals,
                    "total_trades": self.stats.total_trades,
                    "wins": self.stats.wins,
                    "losses": self.stats.losses,
                    "no_hit": self.stats.no_hit,
                    "smc_filtered": self.stats.smc_filtered,
                    "total_pnl_pct": self.stats.total_pnl_pct,
                    "win_pnls": self.stats.win_pnls,
                    "loss_pnls": self.stats.loss_pnls,
                },
                "subscribers": {str(k): v for k, v in self.subscribers.items()},
            }
            with open(PAPER_TRADES_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Paper save error: {e}")

    def _load_state(self):
        """Load trades and config from disk."""
        if not os.path.exists(PAPER_TRADES_FILE):
            return

        try:
            with open(PAPER_TRADES_FILE, "r") as f:
                data = json.load(f)

            self.trades = [PaperTrade.from_dict(t) for t in data.get("trades", [])]

            stats_data = data.get("stats", {})
            self.stats = PaperStats(
                total_signals=stats_data.get("total_signals", 0),
                total_trades=stats_data.get("total_trades", 0),
                wins=stats_data.get("wins", 0),
                losses=stats_data.get("losses", 0),
                no_hit=stats_data.get("no_hit", 0),
                smc_filtered=stats_data.get("smc_filtered", 0),
                total_pnl_pct=stats_data.get("total_pnl_pct", 0),
                win_pnls=stats_data.get("win_pnls", []),
                loss_pnls=stats_data.get("loss_pnls", []),
            )

            subs = data.get("subscribers", {})
            self.subscribers = {int(k): v for k, v in subs.items()}

            logger.info(
                f"📝 Paper Trader loaded: {len(self.trades)} trades, "
                f"{len(self.subscribers)} subscribers"
            )
        except Exception as e:
            logger.error(f"Paper load error: {e}")
