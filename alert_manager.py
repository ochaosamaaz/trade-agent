"""
Alert Manager Module
Manages active trading alerts (Stop Loss / Take Profit).

Features:
- Create alerts with SL and TP levels
- Check current price against alert levels
- Trigger notifications when SL or TP is hit
- Per-user alert management
- Persistent storage via JSON file (survives restarts)
"""

import json
import os
import time
import asyncio
import logging
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

ALERTS_FILE = "alerts.json"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AlertDirection(str, Enum):
    LONG = "long"   # Buy - TP above entry, SL below entry
    SHORT = "short"  # Sell - TP below entry, SL above entry


@dataclass
class TradeAlert:
    """Represents a single trade alert with SL/TP levels."""
    alert_id: str
    user_id: int
    chat_id: int
    symbol: str
    direction: str          # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    status: str = AlertStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    triggered_at: Optional[float] = None
    triggered_price: Optional[float] = None
    is_crypto: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TradeAlert":
        return cls(**data)


class AlertManager:
    """
    Manages all active trade alerts.
    Checks prices against SL/TP levels and triggers notifications.
    """

    def __init__(self, notify_callback: Callable[..., Awaitable] = None):
        """
        Args:
            notify_callback: Async function(alert, trigger_type, current_price)
                             Called when an alert is triggered.
        """
        self.alerts: dict[str, TradeAlert] = {}  # alert_id -> TradeAlert
        self.notify_callback = notify_callback
        self._counter = 0
        self._load_alerts()

    def _generate_id(self) -> str:
        """Generate unique alert ID."""
        self._counter += 1
        return f"A{int(time.time())}{self._counter:04d}"

    # ========== CRUD OPERATIONS ==========

    def create_alert(
        self,
        user_id: int,
        chat_id: int,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        is_crypto: bool = True,
        notes: str = ""
    ) -> TradeAlert:
        """
        Create a new trade alert.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID for notifications
            symbol: Trading pair (e.g., BTCUSDT, EURUSD)
            direction: "long" or "short"
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            is_crypto: True for crypto, False for forex
            notes: Optional notes

        Returns:
            Created TradeAlert object
        """
        alert_id = self._generate_id()

        alert = TradeAlert(
            alert_id=alert_id,
            user_id=user_id,
            chat_id=chat_id,
            symbol=symbol.upper(),
            direction=direction.lower(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            is_crypto=is_crypto,
            notes=notes
        )

        self.alerts[alert_id] = alert
        self._save_alerts()

        logger.info(f"✅ Alert created: {alert_id} | {symbol} {direction} | "
                    f"Entry: {entry_price} | SL: {stop_loss} | TP: {take_profit}")

        return alert

    def remove_alert(self, alert_id: str, user_id: int) -> bool:
        """Remove an alert (only owner can remove)."""
        if alert_id in self.alerts:
            alert = self.alerts[alert_id]
            if alert.user_id == user_id:
                alert.status = AlertStatus.CANCELLED
                del self.alerts[alert_id]
                self._save_alerts()
                return True
        return False

    def get_user_alerts(self, user_id: int, active_only: bool = True) -> list[TradeAlert]:
        """Get all alerts for a specific user."""
        alerts = []
        for alert in self.alerts.values():
            if alert.user_id == user_id:
                if active_only and alert.status != AlertStatus.ACTIVE:
                    continue
                alerts.append(alert)
        return alerts

    def get_alert(self, alert_id: str) -> Optional[TradeAlert]:
        """Get a specific alert by ID."""
        return self.alerts.get(alert_id)

    def get_all_active_symbols(self) -> tuple[set, set]:
        """Get all symbols being monitored (crypto_set, forex_set)."""
        crypto = set()
        forex = set()
        for alert in self.alerts.values():
            if alert.status == AlertStatus.ACTIVE:
                if alert.is_crypto:
                    crypto.add(alert.symbol)
                else:
                    forex.add(alert.symbol)
        return crypto, forex

    def get_active_count(self) -> int:
        """Get number of active alerts."""
        return sum(1 for a in self.alerts.values() if a.status == AlertStatus.ACTIVE)

    # ========== PRICE CHECKING ==========

    async def check_price(self, symbol: str, current_price: float):
        """
        Check current price against all active alerts for a symbol.
        Triggers notifications if SL or TP is hit.

        Args:
            symbol: Trading pair
            current_price: Current market price
        """
        triggered_alerts = []

        for alert_id, alert in list(self.alerts.items()):
            if alert.symbol != symbol.upper():
                continue
            if alert.status != AlertStatus.ACTIVE:
                continue

            trigger_type = self._check_trigger(alert, current_price)

            if trigger_type:
                alert.status = trigger_type
                alert.triggered_at = time.time()
                alert.triggered_price = current_price
                triggered_alerts.append((alert, trigger_type, current_price))
                logger.info(
                    f"🚨 Alert triggered: {alert_id} | {symbol} | "
                    f"{trigger_type} at {current_price}"
                )

        # Send notifications for triggered alerts
        for alert, trigger_type, price in triggered_alerts:
            if self.notify_callback:
                try:
                    await self.notify_callback(alert, trigger_type, price)
                except Exception as e:
                    logger.error(f"Notification error: {e}")

        # Clean up triggered alerts (move to history)
        for alert, _, _ in triggered_alerts:
            if alert.alert_id in self.alerts:
                del self.alerts[alert.alert_id]

        if triggered_alerts:
            self._save_alerts()

    def _check_trigger(self, alert: TradeAlert, price: float) -> Optional[str]:
        """
        Check if price has hit SL or TP.

        For LONG:
          - TP hit if price >= take_profit
          - SL hit if price <= stop_loss

        For SHORT:
          - TP hit if price <= take_profit
          - SL hit if price >= stop_loss
        """
        if alert.direction == AlertDirection.LONG:
            if price >= alert.take_profit:
                return AlertStatus.TP_HIT
            elif price <= alert.stop_loss:
                return AlertStatus.SL_HIT

        elif alert.direction == AlertDirection.SHORT:
            if price <= alert.take_profit:
                return AlertStatus.TP_HIT
            elif price >= alert.stop_loss:
                return AlertStatus.SL_HIT

        return None

    # ========== PERSISTENCE ==========

    def _save_alerts(self):
        """Save active alerts to JSON file."""
        try:
            data = {
                alert_id: alert.to_dict()
                for alert_id, alert in self.alerts.items()
            }
            with open(ALERTS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving alerts: {e}")

    def _load_alerts(self):
        """Load alerts from JSON file."""
        if not os.path.exists(ALERTS_FILE):
            return

        try:
            with open(ALERTS_FILE, "r") as f:
                data = json.load(f)

            for alert_id, alert_data in data.items():
                self.alerts[alert_id] = TradeAlert.from_dict(alert_data)

            logger.info(f"📂 Loaded {len(self.alerts)} alerts from file")
        except Exception as e:
            logger.error(f"Error loading alerts: {e}")

    # ========== FORMATTING ==========

    def format_alert(self, alert: TradeAlert) -> str:
        """Format a single alert for display."""
        direction_emoji = "🟢 LONG" if alert.direction == "long" else "🔴 SHORT"
        market = "🪙" if alert.is_crypto else "💱"

        pnl_tp = abs(alert.take_profit - alert.entry_price) / alert.entry_price * 100
        pnl_sl = abs(alert.stop_loss - alert.entry_price) / alert.entry_price * 100
        rr = pnl_tp / pnl_sl if pnl_sl > 0 else 0

        lines = [
            f"{market} *{alert.symbol}* — {direction_emoji}",
            f"  📍 Entry: `{alert.entry_price}`",
            f"  🎯 TP: `{alert.take_profit}` (+{pnl_tp:.2f}%)",
            f"  🛑 SL: `{alert.stop_loss}` (-{pnl_sl:.2f}%)",
            f"  📊 R:R = `1:{rr:.1f}`",
            f"  🆔 ID: `{alert.alert_id}`",
        ]

        if alert.notes:
            lines.append(f"  📝 {alert.notes}")

        return "\n".join(lines)

    def format_alert_list(self, alerts: list[TradeAlert]) -> str:
        """Format multiple alerts for display."""
        if not alerts:
            return "📭 Tidak ada alert aktif."

        lines = [
            "📋 *ACTIVE ALERTS*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]

        for i, alert in enumerate(alerts, 1):
            lines.append(f"*#{i}*")
            lines.append(self.format_alert(alert))
            lines.append("")

        lines.append(f"Total: {len(alerts)} alert aktif")
        return "\n".join(lines)

    @staticmethod
    def format_trigger_notification(alert: TradeAlert, trigger_type: str, 
                                     current_price: float) -> str:
        """Format a trigger notification message."""
        if trigger_type == AlertStatus.TP_HIT:
            emoji = "🎯✅"
            title = "TAKE PROFIT HIT!"
            result = "PROFIT"
            pnl = abs(current_price - alert.entry_price) / alert.entry_price * 100
            pnl_str = f"+{pnl:.2f}%"
        else:
            emoji = "🛑❌"
            title = "STOP LOSS HIT!"
            result = "LOSS"
            pnl = abs(current_price - alert.entry_price) / alert.entry_price * 100
            pnl_str = f"-{pnl:.2f}%"

        direction = "LONG" if alert.direction == "long" else "SHORT"

        lines = [
            f"{emoji} *{title}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"📊 *{alert.symbol}* | {direction}",
            f"",
            f"  📍 Entry: `{alert.entry_price}`",
            f"  💰 Exit: `{current_price}`",
            f"  📈 Result: *{result}* ({pnl_str})",
            f"",
            f"  🎯 TP was: `{alert.take_profit}`",
            f"  🛑 SL was: `{alert.stop_loss}`",
            f"",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if trigger_type == AlertStatus.TP_HIT:
            lines.append("🎉 Selamat! Target tercapai!")
        else:
            lines.append("💪 Tetap disiplin. Risk management is key!")

        return "\n".join(lines)
