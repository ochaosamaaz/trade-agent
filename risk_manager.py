"""
Risk Management Module for Ciel Agent

Features:
- Position sizing based on % risk per trade
- Lot/quantity calculation for forex and crypto
- Risk:Reward ratio validation
- Max drawdown tracking
- Account balance management

Usage:
    rm = RiskManager(balance=1000, risk_pct=1.0)
    size = rm.calculate_position_size(
        entry=67000, stop_loss=66000, symbol="BTCUSDT", is_crypto=True
    )
    # Returns: {"size": 0.01, "risk_amount": 10.0, "rr_ratio": 2.0, ...}
"""

from dataclasses import dataclass
from typing import Optional
from config import (
    RISK_PER_TRADE_PCT, DEFAULT_ACCOUNT_BALANCE,
    MAX_POSITION_SIZE, DEFAULT_LEVERAGE
)


@dataclass
class PositionSize:
    """Calculated position size result."""
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pips: float
    reward_pips: float
    rr_ratio: float
    risk_amount: float  # Dollar amount risked
    position_size: float  # Lots (forex) or quantity (crypto)
    potential_profit: float
    potential_loss: float
    leverage: int
    account_balance: float
    risk_pct: float


class RiskManager:
    """
    Position sizing and risk management calculator.
    Ensures no single trade risks more than X% of account.
    """

    # Standard forex lot sizes
    FOREX_LOT_SIZES = {
        "standard": 100000,  # 1 lot = 100,000 units
        "mini": 10000,       # 0.1 lot = 10,000 units
        "micro": 1000,       # 0.01 lot = 1,000 units
    }

    # Pip values for common pairs (per standard lot)
    FOREX_PIP_VALUES = {
        "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
        "NZDUSD": 10.0, "USDCAD": 10.0, "USDCHF": 10.0,
        "USDJPY": 1000.0 / 100,  # ~$6.67 per pip per lot (varies)
        "EURJPY": 1000.0 / 100, "GBPJPY": 1000.0 / 100,
        "EURGBP": 10.0,
        "XAUUSD": 1.0,  # $1 per 0.01 lot per pip (special)
    }

    def __init__(self, balance: float = None, risk_pct: float = None,
                 leverage: int = None):
        """
        Args:
            balance: Account balance in USD
            risk_pct: Risk percentage per trade (e.g., 1.0 = 1%)
            leverage: Trading leverage
        """
        self.balance = balance or DEFAULT_ACCOUNT_BALANCE
        self.risk_pct = risk_pct or RISK_PER_TRADE_PCT
        self.leverage = leverage or DEFAULT_LEVERAGE
        self.max_position = MAX_POSITION_SIZE

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        symbol: str,
        direction: str = "long",
        is_crypto: bool = True
    ) -> PositionSize:
        """
        Calculate optimal position size based on risk management rules.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            symbol: Trading pair
            direction: "long" or "short"
            is_crypto: True for crypto, False for forex

        Returns:
            PositionSize object with all calculations
        """
        # Calculate risk and reward in price terms
        if direction == "long":
            risk_pips = abs(entry_price - stop_loss)
            reward_pips = abs(take_profit - entry_price)
        else:
            risk_pips = abs(stop_loss - entry_price)
            reward_pips = abs(entry_price - take_profit)

        # Risk:Reward ratio
        rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0

        # Dollar amount we're willing to risk
        risk_amount = self.balance * (self.risk_pct / 100)

        # Calculate position size
        if is_crypto:
            position_size = self._calc_crypto_size(
                risk_amount, risk_pips, entry_price
            )
        else:
            position_size = self._calc_forex_size(
                risk_amount, risk_pips, entry_price, symbol
            )

        # Cap at max position size
        position_size = min(position_size, self.max_position)

        # Calculate potential profit/loss
        if is_crypto:
            potential_profit = position_size * reward_pips
            potential_loss = position_size * risk_pips
        else:
            pip_value = self._get_pip_value(symbol)
            potential_profit = position_size * reward_pips * pip_value * 10
            potential_loss = risk_amount

        return PositionSize(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_pips=risk_pips,
            reward_pips=reward_pips,
            rr_ratio=round(rr_ratio, 2),
            risk_amount=round(risk_amount, 2),
            position_size=round(position_size, 6),
            potential_profit=round(potential_profit, 2),
            potential_loss=round(potential_loss, 2),
            leverage=self.leverage,
            account_balance=self.balance,
            risk_pct=self.risk_pct
        )

    def _calc_crypto_size(self, risk_amount: float, risk_distance: float,
                           entry_price: float) -> float:
        """
        Calculate crypto position size.
        Size = Risk Amount / Risk Distance (in asset terms)
        With leverage: Size = (Risk Amount * Leverage) / Risk Distance
        """
        if risk_distance == 0:
            return 0

        # Position size in base asset (e.g., BTC)
        size = risk_amount / risk_distance

        return size

    def _calc_forex_size(self, risk_amount: float, risk_pips: float,
                          entry_price: float, symbol: str) -> float:
        """
        Calculate forex position size in lots.
        Size (lots) = Risk Amount / (Pips × Pip Value)
        """
        if risk_pips == 0:
            return 0

        pip_value = self._get_pip_value(symbol)

        # Convert price distance to pips
        if "JPY" in symbol:
            pips = risk_pips * 100  # JPY pairs: 1 pip = 0.01
        elif symbol == "XAUUSD":
            pips = risk_pips * 10  # Gold: 1 pip = 0.1
        else:
            pips = risk_pips * 10000  # Standard: 1 pip = 0.0001

        # Lots = Risk / (Pips × Pip Value per lot)
        if pips * pip_value > 0:
            lots = risk_amount / (pips * pip_value)
        else:
            lots = 0.01

        return lots

    def _get_pip_value(self, symbol: str) -> float:
        """Get pip value per standard lot for a symbol."""
        return self.FOREX_PIP_VALUES.get(symbol, 10.0)

    # ========== FORMATTING ==========

    @staticmethod
    def format_position_size(ps: PositionSize, is_crypto: bool = True) -> str:
        """Format position size calculation for Telegram."""
        dir_emoji = "📗 LONG" if ps.direction == "long" else "📕 SHORT"
        size_label = "Quantity" if is_crypto else "Lots"

        lines = [
            f"📐 *POSITION SIZE — {ps.symbol}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"🎯 {dir_emoji}",
            f"📍 Entry: `{ps.entry_price}`",
            f"🛑 SL: `{ps.stop_loss}`",
            f"🎯 TP: `{ps.take_profit}`",
            f"",
            f"━━━ *RISK CALCULATION* ━━━",
            f"💰 Account: `${ps.account_balance:,.2f}`",
            f"⚠️ Risk: `{ps.risk_pct}%` = `${ps.risk_amount:.2f}`",
            f"📊 R:R = `1:{ps.rr_ratio}`",
            f"⚡ Leverage: `{ps.leverage}x`",
            f"",
            f"━━━ *POSITION SIZE* ━━━",
            f"📦 {size_label}: `{ps.position_size}`",
            f"📈 Potential Profit: `+${ps.potential_profit:.2f}`",
            f"📉 Potential Loss: `-${ps.potential_loss:.2f}`",
            f"",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Warnings
        if ps.rr_ratio < 1.5:
            lines.append("⚠️ _R:R di bawah 1.5 — kurang ideal!_")
        if ps.risk_pct > 2:
            lines.append("🚨 _Risk > 2% — terlalu besar!_")

        return "\n".join(lines)

    def update_balance(self, new_balance: float):
        """Update account balance."""
        self.balance = new_balance

    def update_risk(self, new_risk_pct: float):
        """Update risk percentage."""
        self.risk_pct = max(0.1, min(new_risk_pct, 5.0))  # Clamp 0.1-5%
