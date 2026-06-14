"""
Backtesting Engine for Quantum Physics Trading Theory + Smart Money Concepts

Logic:
1. For each day, compare Open vs Previous Open to determine bias (UP/DOWN)
2. Calculate Pivot Points from previous day's H/L/C
3. Run SMC analysis on recent candles for confluence scoring
4. Determine entry zones based on bias + validation
5. FILTER: Skip trade if SMC confluence < 50 (configurable)
6. Check if price hit TP (PDH/PDL sweep) or SL during that day
7. Collect stats: win rate, avg profit, avg loss, R:R, drawdown, etc.

Entry Rules:
- UP bias → Buy at PP or S1 (whichever is valid)
- DOWN bias → Sell at PP or R1 (whichever is valid)

SMC Filter:
- Score >= 50: Take the trade
- Score < 50: Skip (marked as SMC_FILTERED)

TP Target:
- UP → PDH (Previous Day High)
- DOWN → PDL (Previous Day Low)

SL:
- UP → S2 (below S1)
- DOWN → R2 (above R1)

Win Condition:
- Price reaches TP level during the session (intraday check using H/L)

Loss Condition:
- Price reaches SL level during the session before hitting TP
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from pivot_calculator import calculate_pivot_points
from smc_engine import SMCEngine
from data_fetcher import DataFetcher

# Minimum SMC confluence score to take a trade
SMC_MIN_SCORE = 50


@dataclass
class BacktestTrade:
    """Represents a single backtested trade."""
    day: int
    date: str
    symbol: str
    bias: str  # UP or DOWN
    entry_price: float
    entry_type: str  # "PP", "S1", "R1"
    stop_loss: float
    take_profit: float
    result: str  # "WIN", "LOSS", "NO_ENTRY", "NEUTRAL", "SMC_FILTERED"
    pnl_pct: float = 0.0
    rr_ratio: float = 0.0
    smc_score: int = 0
    notes: str = ""


@dataclass
class BacktestResult:
    """Complete backtest result summary."""
    symbol: str
    total_days: int
    total_trades: int
    wins: int
    losses: int
    no_entry: int
    neutral_days: int
    smc_filtered: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    total_pnl_pct: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_drawdown_pct: float
    profit_factor: float
    avg_rr: float
    avg_smc_score: float
    trades: list = field(default_factory=list)


class Backtester:
    """
    Backtesting engine for Quantum Physics Trading Theory + SMC.
    Uses historical daily candles to simulate the strategy.
    """

    def __init__(self):
        self.fetcher = DataFetcher()
        self.smc = SMCEngine()

    async def run_backtest(self, symbol: str, days: int = 30,
                           is_crypto: bool = True,
                           use_smc_filter: bool = True) -> Optional[BacktestResult]:
        """
        Run a backtest on historical data.

        Args:
            symbol: Trading pair (e.g., BTCUSDT, EURUSD)
            days: Number of days to backtest (max depends on API limits)
            is_crypto: True for crypto (Binance), False for forex (TwelveData)
            use_smc_filter: If True, skip trades with SMC score < 50

        Returns:
            BacktestResult with all statistics
        """
        # Fetch historical candles
        candles = await self._fetch_historical(symbol, days + 2, is_crypto)

        if not candles or len(candles) < 3:
            return None

        trades = []
        wins = 0
        losses = 0
        no_entry = 0
        neutral_days = 0
        smc_filtered_count = 0
        win_pnls = []
        loss_pnls = []
        all_pnls = []
        all_smc_scores = []
        consecutive_wins = 0
        consecutive_losses = 0
        max_consec_wins = 0
        max_consec_losses = 0

        # Iterate through candles (need at least 2 previous days)
        for i in range(2, len(candles)):
            prev_prev = candles[i - 2]  # Day before yesterday
            prev = candles[i - 1]       # Yesterday
            current = candles[i]         # Today (the day we trade)

            # ---- QUANTUM THEORY: Determine Bias ----
            current_open = current["open"]
            previous_open = prev["open"]

            if current_open < previous_open:
                bias = "DOWN"
            elif current_open > previous_open:
                bias = "UP"
            else:
                # Neutral - no trade
                neutral_days += 1
                trades.append(BacktestTrade(
                    day=i - 1,
                    date=current.get("date", f"Day {i-1}"),
                    symbol=symbol,
                    bias="NEUTRAL",
                    entry_price=0,
                    entry_type="NONE",
                    stop_loss=0,
                    take_profit=0,
                    result="NEUTRAL",
                    notes="Open = Prev Open → No bias"
                ))
                continue

            # ---- PIVOT POINTS from yesterday ----
            pivots = calculate_pivot_points(prev["high"], prev["low"], prev["close"])

            # ---- PDH / PDL (Yesterday's High & Low) ----
            pdh = prev["high"]
            pdl = prev["low"]

            # ---- DETERMINE ENTRY ----
            entry_price = None
            entry_type = ""
            stop_loss = None
            take_profit = None

            if bias == "UP":
                # Entry at PP or S1 (buy zone)
                take_profit = pdh

                # Validation: If Open > PP, PP entry invalid
                if current_open > pivots["PP"]:
                    # Only S1 valid
                    if current_open > pivots["S1"]:
                        # Check if price came down to S1 during the day
                        if current["low"] <= pivots["S1"]:
                            entry_price = pivots["S1"]
                            entry_type = "S1"
                        else:
                            # Price never reached S1
                            no_entry += 1
                            trades.append(BacktestTrade(
                                day=i - 1,
                                date=current.get("date", f"Day {i-1}"),
                                symbol=symbol,
                                bias=bias,
                                entry_price=0,
                                entry_type="NONE",
                                stop_loss=0,
                                take_profit=pdh,
                                result="NO_ENTRY",
                                notes="Open > PP, price never reached S1"
                            ))
                            continue
                    else:
                        # Open between S1 and PP → entry at open (already at S1 zone)
                        entry_price = pivots["S1"]
                        entry_type = "S1"
                else:
                    # PP is valid entry
                    # Check if price came down to PP during the day
                    if current["low"] <= pivots["PP"]:
                        entry_price = pivots["PP"]
                        entry_type = "PP"
                    elif current_open <= pivots["PP"]:
                        # Open at or below PP — entry at PP
                        entry_price = pivots["PP"]
                        entry_type = "PP"
                    else:
                        # Price opened above but came down to PP?
                        # Already handled above (low <= PP)
                        no_entry += 1
                        trades.append(BacktestTrade(
                            day=i - 1,
                            date=current.get("date", f"Day {i-1}"),
                            symbol=symbol,
                            bias=bias,
                            entry_price=0,
                            entry_type="NONE",
                            stop_loss=0,
                            take_profit=pdh,
                            result="NO_ENTRY",
                            notes="Price never reached PP entry"
                        ))
                        continue

                stop_loss = pivots["S2"]

            elif bias == "DOWN":
                # Entry at PP or R1 (sell zone)
                take_profit = pdl

                # Validation: If Open < PP, PP entry invalid
                if current_open < pivots["PP"]:
                    # Only R1 valid
                    if current_open < pivots["R1"]:
                        # Check if price came up to R1 during the day
                        if current["high"] >= pivots["R1"]:
                            entry_price = pivots["R1"]
                            entry_type = "R1"
                        else:
                            no_entry += 1
                            trades.append(BacktestTrade(
                                day=i - 1,
                                date=current.get("date", f"Day {i-1}"),
                                symbol=symbol,
                                bias=bias,
                                entry_price=0,
                                entry_type="NONE",
                                stop_loss=0,
                                take_profit=pdl,
                                result="NO_ENTRY",
                                notes="Open < PP, price never reached R1"
                            ))
                            continue
                    else:
                        # Open between PP and R1 → entry at R1
                        entry_price = pivots["R1"]
                        entry_type = "R1"
                else:
                    # PP is valid entry
                    if current["high"] >= pivots["PP"]:
                        entry_price = pivots["PP"]
                        entry_type = "PP"
                    elif current_open >= pivots["PP"]:
                        entry_price = pivots["PP"]
                        entry_type = "PP"
                    else:
                        no_entry += 1
                        trades.append(BacktestTrade(
                            day=i - 1,
                            date=current.get("date", f"Day {i-1}"),
                            symbol=symbol,
                            bias=bias,
                            entry_price=0,
                            entry_type="NONE",
                            stop_loss=0,
                            take_profit=pdl,
                            result="NO_ENTRY",
                            notes="Price never reached PP entry"
                        ))
                        continue

                stop_loss = pivots["R2"]

            # ---- SMC CONFLUENCE FILTER ----
            # Use candles up to (but not including) current day for SMC analysis
            lookback = min(i, 15)  # Use up to 15 previous candles
            smc_candles = candles[max(0, i - lookback):i]
            
            smc_score = 0
            if len(smc_candles) >= 5:
                smc_analysis = self.smc.analyze(
                    candles=smc_candles,
                    current_price=current_open,
                    bias=bias
                )
                smc_score = smc_analysis.confluence_score
                all_smc_scores.append(smc_score)
            
            # Filter: Skip trade if SMC score too low
            if use_smc_filter and smc_score < SMC_MIN_SCORE:
                smc_filtered_count += 1
                trades.append(BacktestTrade(
                    day=i - 1,
                    date=current.get("date", f"Day {i-1}"),
                    symbol=symbol,
                    bias=bias,
                    entry_price=entry_price,
                    entry_type=entry_type,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    result="SMC_FILTERED",
                    smc_score=smc_score,
                    notes=f"SMC score {smc_score} < {SMC_MIN_SCORE} → skipped"
                ))
                continue

            # ---- CHECK WIN/LOSS ----
            # Simulate: Did price hit TP or SL first?
            result, pnl_pct = self._check_trade_outcome(
                bias=bias,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                day_high=current["high"],
                day_low=current["low"]
            )

            # Calculate R:R
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr = reward / risk if risk > 0 else 0

            if result == "WIN":
                wins += 1
                win_pnls.append(pnl_pct)
                consecutive_wins += 1
                consecutive_losses = 0
                max_consec_wins = max(max_consec_wins, consecutive_wins)
            elif result == "LOSS":
                losses += 1
                loss_pnls.append(pnl_pct)
                consecutive_losses += 1
                consecutive_wins = 0
                max_consec_losses = max(max_consec_losses, consecutive_losses)

            all_pnls.append(pnl_pct)

            trades.append(BacktestTrade(
                day=i - 1,
                date=current.get("date", f"Day {i-1}"),
                symbol=symbol,
                bias=bias,
                entry_price=entry_price,
                entry_type=entry_type,
                stop_loss=stop_loss,
                take_profit=take_profit,
                result=result,
                pnl_pct=pnl_pct,
                rr_ratio=rr,
                smc_score=smc_score,
                notes=""
            ))

        # ---- CALCULATE STATS ----
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
        total_pnl = sum(all_pnls)
        gross_profit = sum(win_pnls) if win_pnls else 0
        gross_loss = abs(sum(loss_pnls)) if loss_pnls else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Max Drawdown
        max_drawdown = self._calculate_max_drawdown(all_pnls)

        # Average R:R
        rr_values = [t.rr_ratio for t in trades if t.result in ("WIN", "LOSS")]
        avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0

        # Average SMC score
        avg_smc = sum(all_smc_scores) / len(all_smc_scores) if all_smc_scores else 0

        return BacktestResult(
            symbol=symbol,
            total_days=len(candles) - 2,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            no_entry=no_entry,
            neutral_days=neutral_days,
            smc_filtered=smc_filtered_count,
            win_rate=win_rate,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            total_pnl_pct=total_pnl,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            max_drawdown_pct=max_drawdown,
            profit_factor=profit_factor,
            avg_rr=avg_rr,
            avg_smc_score=avg_smc,
            trades=trades
        )

    def _check_trade_outcome(self, bias: str, entry_price: float,
                              stop_loss: float, take_profit: float,
                              day_high: float, day_low: float) -> tuple:
        """
        Determine if trade was a WIN or LOSS based on intraday price action.

        For simplicity, we assume:
        - If both SL and TP are hit in the same candle, the one closer to open gets hit first
        - UP (long): TP hit if high >= TP, SL hit if low <= SL
        - DOWN (short): TP hit if low <= TP, SL hit if high >= SL

        Returns: (result: str, pnl_pct: float)
        """
        if bias == "UP":
            tp_hit = day_high >= take_profit
            sl_hit = day_low <= stop_loss

            if tp_hit and sl_hit:
                # Both hit — conservative: assume SL hit first if entry closer to SL
                # Simple heuristic: if distance to SL < distance to TP, SL first
                dist_tp = abs(take_profit - entry_price)
                dist_sl = abs(entry_price - stop_loss)
                if dist_sl < dist_tp:
                    # Likely SL hit first
                    pnl = -(abs(entry_price - stop_loss) / entry_price) * 100
                    return "LOSS", round(pnl, 4)
                else:
                    pnl = (abs(take_profit - entry_price) / entry_price) * 100
                    return "WIN", round(pnl, 4)
            elif tp_hit:
                pnl = (abs(take_profit - entry_price) / entry_price) * 100
                return "WIN", round(pnl, 4)
            elif sl_hit:
                pnl = -(abs(entry_price - stop_loss) / entry_price) * 100
                return "LOSS", round(pnl, 4)
            else:
                # Neither hit — close at end of day (treat as small loss/gain)
                # For simplicity, mark as loss with 0 PnL (missed)
                return "LOSS", 0.0

        elif bias == "DOWN":
            tp_hit = day_low <= take_profit
            sl_hit = day_high >= stop_loss

            if tp_hit and sl_hit:
                dist_tp = abs(entry_price - take_profit)
                dist_sl = abs(stop_loss - entry_price)
                if dist_sl < dist_tp:
                    pnl = -(abs(stop_loss - entry_price) / entry_price) * 100
                    return "LOSS", round(pnl, 4)
                else:
                    pnl = (abs(entry_price - take_profit) / entry_price) * 100
                    return "WIN", round(pnl, 4)
            elif tp_hit:
                pnl = (abs(entry_price - take_profit) / entry_price) * 100
                return "WIN", round(pnl, 4)
            elif sl_hit:
                pnl = -(abs(stop_loss - entry_price) / entry_price) * 100
                return "LOSS", round(pnl, 4)
            else:
                return "LOSS", 0.0

        return "LOSS", 0.0

    def _calculate_max_drawdown(self, pnls: list) -> float:
        """Calculate maximum drawdown from PnL series."""
        if not pnls:
            return 0.0

        cumulative = 0
        peak = 0
        max_dd = 0

        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_dd:
                max_dd = drawdown

        return round(max_dd, 4)

    async def _fetch_historical(self, symbol: str, days: int,
                                 is_crypto: bool) -> Optional[list]:
        """
        Fetch historical daily candles.

        Returns list of dicts with keys: open, high, low, close, date
        """
        if is_crypto:
            return await self._fetch_crypto_history(symbol, days)
        else:
            return await self._fetch_forex_history(symbol, days)

    async def _fetch_crypto_history(self, symbol: str, days: int) -> Optional[list]:
        """Fetch crypto daily history from Binance with fallback endpoints."""
        import aiohttp

        endpoints = [
            "https://api4.binance.com/api/v3",
            "https://api3.binance.com/api/v3",
            "https://api2.binance.com/api/v3",
            "https://api1.binance.com/api/v3",
            "https://api.binance.com/api/v3",
            "https://data-api.binance.vision/api/v3",
        ]

        params = {
            "symbol": symbol.upper(),
            "interval": "1d",
            "limit": min(days, 500)
        }

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            for base_url in endpoints:
                try:
                    url = f"{base_url}/klines"
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result = []
                            for candle in data:
                                from datetime import datetime
                                ts = int(candle[0]) / 1000
                                dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                                result.append({
                                    "open": float(candle[1]),
                                    "high": float(candle[2]),
                                    "low": float(candle[3]),
                                    "close": float(candle[4]),
                                    "date": dt
                                })
                            return result
                except Exception as e:
                    continue

        print(f"Backtest fetch error: All Binance endpoints failed for {symbol}")
        return None

    async def _fetch_forex_history(self, symbol: str, days: int) -> Optional[list]:
        """Fetch forex daily history from TwelveData."""
        import aiohttp
        import os

        # Format symbol properly
        special = {"XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD"}
        if symbol.upper() in special:
            formatted = special[symbol.upper()]
        elif "/" not in symbol and len(symbol) == 6:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        elif "/" not in symbol:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        else:
            formatted = symbol

        api_key = os.getenv("TWELVE_DATA_API_KEY", "demo")
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": formatted,
            "interval": "1day",
            "outputsize": min(days, 100),
            "apikey": api_key
        }

        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "values" in data:
                            result = []
                            for candle in reversed(data["values"]):
                                result.append({
                                    "open": float(candle["open"]),
                                    "high": float(candle["high"]),
                                    "low": float(candle["low"]),
                                    "close": float(candle["close"]),
                                    "date": candle["datetime"]
                                })
                            return result
                    return None
        except Exception as e:
            print(f"Forex backtest fetch error: {e}")
            return None

    # ========== FORMATTING ==========

    @staticmethod
    def format_result(result: BacktestResult) -> str:
        """Format backtest result for Telegram message."""
        if result.win_rate >= 60:
            grade = "🟢 EXCELLENT"
        elif result.win_rate >= 50:
            grade = "🟡 GOOD"
        elif result.win_rate >= 40:
            grade = "🟠 AVERAGE"
        else:
            grade = "🔴 POOR"

        pnl_emoji = "📈" if result.total_pnl_pct >= 0 else "📉"

        lines = [
            f"📊 *BACKTEST RESULT — {result.symbol}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"⏱️ Period: `{result.total_days} days`",
            f"📐 Strategy: Quantum + SMC Filter",
            f"",
            f"━━━ *PERFORMANCE* ━━━",
            f"🎯 Win Rate: `{result.win_rate:.1f}%` {grade}",
            f"📊 Total Trades: `{result.total_trades}`",
            f"✅ Wins: `{result.wins}` | ❌ Losses: `{result.losses}`",
            f"⏭️ No Entry: `{result.no_entry}` | ⚖️ Neutral: `{result.neutral_days}`",
            f"🏦 SMC Filtered: `{result.smc_filtered}` (skipped low confluence)",
            f"",
            f"━━━ *P&L* ━━━",
            f"{pnl_emoji} Total PnL: `{result.total_pnl_pct:+.2f}%`",
            f"✅ Avg Win: `+{result.avg_win_pct:.2f}%`",
            f"❌ Avg Loss: `{result.avg_loss_pct:.2f}%`",
            f"📊 Profit Factor: `{result.profit_factor:.2f}`",
            f"📐 Avg R:R: `1:{result.avg_rr:.1f}`",
            f"",
            f"━━━ *SMC* ━━━",
            f"🏦 Avg SMC Score: `{result.avg_smc_score:.0f}/100`",
            f"🔍 Trades filtered: `{result.smc_filtered}` (score < {SMC_MIN_SCORE})",
            f"",
            f"━━━ *RISK* ━━━",
            f"📉 Max Drawdown: `{result.max_drawdown_pct:.2f}%`",
            f"🔥 Max Consec Wins: `{result.max_consecutive_wins}`",
            f"❄️ Max Consec Losses: `{result.max_consecutive_losses}`",
            f"",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Trade breakdown
        if result.trades:
            lines.append("")
            lines.append("📋 *Last 5 Trades:*")
            recent = [t for t in result.trades if t.result in ("WIN", "LOSS")][-5:]
            for t in recent:
                emoji = "✅" if t.result == "WIN" else "❌"
                lines.append(
                    f"  {emoji} {t.date} | {t.bias} @ {t.entry_type} | "
                    f"`{t.pnl_pct:+.2f}%` | SMC:{t.smc_score}"
                )

        lines.extend([
            "",
            "⚠️ _Past performance ≠ future results. Always use risk management!_"
        ])

        return "\n".join(lines)

    @staticmethod
    def format_result_short(result: BacktestResult) -> str:
        """Short format for inline display."""
        pnl_emoji = "📈" if result.total_pnl_pct >= 0 else "📉"
        return (
            f"🎯 {result.symbol}: WR `{result.win_rate:.1f}%` | "
            f"{pnl_emoji} `{result.total_pnl_pct:+.2f}%` | "
            f"Trades: {result.total_trades} ({result.wins}W/{result.losses}L) | "
            f"SMC avg: {result.avg_smc_score:.0f} | {result.total_days}d"
        )
