"""
Smart Money Concepts (SMC) Engine
Detects institutional trading patterns to filter and confirm signals.

Key Concepts:
1. Break of Structure (BOS) — Trend confirmation
2. Change of Character (ChoCH) — Trend reversal signal
3. Order Blocks (OB) — Institutional supply/demand zones
4. Fair Value Gaps (FVG) — Imbalance zones (magnets for price)
5. Liquidity Sweeps — Stop hunts before real moves
6. Premium/Discount Zones — OTE (Optimal Trade Entry) areas

Usage:
    smc = SMCEngine()
    analysis = smc.analyze(candles)  # list of {open, high, low, close}
    # Returns SMCAnalysis with confluence score and details
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderBlock:
    """Represents an Order Block (institutional S/D zone)."""
    type: str  # "bullish" or "bearish"
    high: float
    low: float
    index: int  # candle index where it formed
    mitigated: bool = False

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class FairValueGap:
    """Represents a Fair Value Gap (imbalance)."""
    type: str  # "bullish" or "bearish"
    high: float  # top of gap
    low: float   # bottom of gap
    index: int
    filled: bool = False

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class StructureBreak:
    """Represents a Break of Structure or Change of Character."""
    type: str  # "bos_bullish", "bos_bearish", "choch_bullish", "choch_bearish"
    level: float
    index: int


@dataclass
class SMCAnalysis:
    """Complete SMC analysis result."""
    # Structure
    market_structure: str  # "bullish", "bearish", "ranging"
    latest_break: Optional[StructureBreak] = None

    # Order Blocks
    bullish_obs: list = field(default_factory=list)
    bearish_obs: list = field(default_factory=list)
    nearest_ob: Optional[OrderBlock] = None

    # Fair Value Gaps
    bullish_fvgs: list = field(default_factory=list)
    bearish_fvgs: list = field(default_factory=list)
    nearest_fvg: Optional[FairValueGap] = None

    # Liquidity
    liquidity_swept: bool = False
    sweep_direction: str = ""  # "buy_side" or "sell_side"

    # Premium/Discount
    zone: str = ""  # "premium", "discount", "equilibrium"

    # Confluence Score (0-100)
    confluence_score: int = 0
    confluence_details: list = field(default_factory=list)


class SMCEngine:
    """
    Smart Money Concepts analysis engine.
    Analyzes price action for institutional patterns.
    """

    def analyze(self, candles: list, current_price: float = None,
                bias: str = "NEUTRAL") -> SMCAnalysis:
        """
        Full SMC analysis on historical candles.

        Args:
            candles: List of dicts with keys: open, high, low, close
                     (oldest first, newest last). Need minimum 10 candles.
            current_price: Current price for zone calculation
            bias: "UP" or "DOWN" from Quantum Theory (for confluence scoring)

        Returns:
            SMCAnalysis with all detected patterns and confluence score
        """
        if not candles or len(candles) < 5:
            return SMCAnalysis(market_structure="unknown", confluence_score=0)

        # Use last candle's close if no current price
        if current_price is None:
            current_price = candles[-1]["close"]

        # Step 1: Detect swing highs and lows
        swing_highs, swing_lows = self._find_swing_points(candles)

        # Step 2: Determine market structure (BOS / ChoCH)
        structure, latest_break = self._analyze_structure(
            candles, swing_highs, swing_lows
        )

        # Step 3: Find Order Blocks
        bullish_obs, bearish_obs = self._find_order_blocks(candles)

        # Step 4: Find Fair Value Gaps
        bullish_fvgs, bearish_fvgs = self._find_fvgs(candles)

        # Step 5: Detect liquidity sweeps
        liquidity_swept, sweep_direction = self._detect_liquidity_sweep(
            candles, swing_highs, swing_lows
        )

        # Step 6: Determine Premium/Discount zone
        zone = self._get_price_zone(candles, current_price)

        # Step 7: Find nearest relevant OB and FVG
        nearest_ob = self._find_nearest_ob(
            bullish_obs, bearish_obs, current_price, bias
        )
        nearest_fvg = self._find_nearest_fvg(
            bullish_fvgs, bearish_fvgs, current_price, bias
        )

        # Step 8: Calculate confluence score
        confluence_score, details = self._calculate_confluence(
            bias=bias,
            structure=structure,
            latest_break=latest_break,
            nearest_ob=nearest_ob,
            nearest_fvg=nearest_fvg,
            liquidity_swept=liquidity_swept,
            sweep_direction=sweep_direction,
            zone=zone,
            current_price=current_price
        )

        return SMCAnalysis(
            market_structure=structure,
            latest_break=latest_break,
            bullish_obs=bullish_obs,
            bearish_obs=bearish_obs,
            nearest_ob=nearest_ob,
            bullish_fvgs=bullish_fvgs,
            bearish_fvgs=bearish_fvgs,
            nearest_fvg=nearest_fvg,
            liquidity_swept=liquidity_swept,
            sweep_direction=sweep_direction,
            zone=zone,
            confluence_score=confluence_score,
            confluence_details=details
        )

    # ========== SWING POINTS ==========

    def _find_swing_points(self, candles: list) -> tuple:
        """
        Find swing highs and swing lows.
        A swing high: candle high > both neighbors' highs
        A swing low: candle low < both neighbors' lows
        """
        swing_highs = []  # (index, price)
        swing_lows = []   # (index, price)

        for i in range(1, len(candles) - 1):
            # Swing High
            if (candles[i]["high"] > candles[i-1]["high"] and
                candles[i]["high"] > candles[i+1]["high"]):
                swing_highs.append((i, candles[i]["high"]))

            # Swing Low
            if (candles[i]["low"] < candles[i-1]["low"] and
                candles[i]["low"] < candles[i+1]["low"]):
                swing_lows.append((i, candles[i]["low"]))

        return swing_highs, swing_lows

    # ========== MARKET STRUCTURE ==========

    def _analyze_structure(self, candles: list, swing_highs: list,
                           swing_lows: list) -> tuple:
        """
        Determine market structure based on swing points.

        Bullish: Higher Highs (HH) + Higher Lows (HL)
        Bearish: Lower Highs (LH) + Lower Lows (LL)

        BOS = Break of Structure (continuation)
        ChoCH = Change of Character (reversal)
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "ranging", None

        # Check last 2 swing highs and lows
        last_sh = swing_highs[-1][1]
        prev_sh = swing_highs[-2][1]
        last_sl = swing_lows[-1][1]
        prev_sl = swing_lows[-2][1]

        latest_break = None

        # Higher High + Higher Low = Bullish
        if last_sh > prev_sh and last_sl > prev_sl:
            structure = "bullish"
            latest_break = StructureBreak(
                type="bos_bullish",
                level=prev_sh,
                index=swing_highs[-1][0]
            )
        # Lower High + Lower Low = Bearish
        elif last_sh < prev_sh and last_sl < prev_sl:
            structure = "bearish"
            latest_break = StructureBreak(
                type="bos_bearish",
                level=prev_sl,
                index=swing_lows[-1][0]
            )
        # Mixed signals — check for ChoCH
        elif last_sh > prev_sh and last_sl < prev_sl:
            # Was bearish, now making HH = potential ChoCH bullish
            structure = "bullish"
            latest_break = StructureBreak(
                type="choch_bullish",
                level=prev_sh,
                index=swing_highs[-1][0]
            )
        elif last_sh < prev_sh and last_sl > prev_sl:
            # Was bullish, now making LH = potential ChoCH bearish
            structure = "bearish"
            latest_break = StructureBreak(
                type="choch_bearish",
                level=prev_sl,
                index=swing_lows[-1][0]
            )
        else:
            structure = "ranging"

        return structure, latest_break

    # ========== ORDER BLOCKS ==========

    def _find_order_blocks(self, candles: list) -> tuple:
        """
        Detect Order Blocks.

        Bullish OB: Last bearish candle before a strong bullish move
        Bearish OB: Last bullish candle before a strong bearish move

        "Strong move" = candle body > 1.5x average body size
        """
        bullish_obs = []
        bearish_obs = []

        if len(candles) < 3:
            return bullish_obs, bearish_obs

        # Calculate average body size
        bodies = [abs(c["close"] - c["open"]) for c in candles]
        avg_body = sum(bodies) / len(bodies) if bodies else 0

        for i in range(1, len(candles) - 1):
            curr = candles[i]
            next_c = candles[i + 1]

            curr_body = abs(curr["close"] - curr["open"])
            next_body = abs(next_c["close"] - next_c["open"])

            # Bullish OB: current is bearish, next is strong bullish
            if (curr["close"] < curr["open"] and  # current bearish
                next_c["close"] > next_c["open"] and  # next bullish
                next_body > avg_body * 1.5):  # strong move
                bullish_obs.append(OrderBlock(
                    type="bullish",
                    high=curr["open"],  # OB high = open of bearish candle
                    low=curr["low"],
                    index=i
                ))

            # Bearish OB: current is bullish, next is strong bearish
            if (curr["close"] > curr["open"] and  # current bullish
                next_c["close"] < next_c["open"] and  # next bearish
                next_body > avg_body * 1.5):  # strong move
                bearish_obs.append(OrderBlock(
                    type="bearish",
                    high=curr["high"],
                    low=curr["open"],  # OB low = open of bullish candle
                    index=i
                ))

        # Mark mitigated OBs (price has returned to the OB)
        if candles:
            last_price = candles[-1]["close"]
            for ob in bullish_obs:
                if last_price < ob.low:
                    ob.mitigated = True
            for ob in bearish_obs:
                if last_price > ob.high:
                    ob.mitigated = True

        # Keep only unmitigated (active) OBs, last 3
        bullish_obs = [ob for ob in bullish_obs if not ob.mitigated][-3:]
        bearish_obs = [ob for ob in bearish_obs if not ob.mitigated][-3:]

        return bullish_obs, bearish_obs

    # ========== FAIR VALUE GAPS ==========

    def _find_fvgs(self, candles: list) -> tuple:
        """
        Detect Fair Value Gaps (imbalances).

        Bullish FVG: candle[i-1].high < candle[i+1].low (gap up)
        Bearish FVG: candle[i-1].low > candle[i+1].high (gap down)
        """
        bullish_fvgs = []
        bearish_fvgs = []

        if len(candles) < 3:
            return bullish_fvgs, bearish_fvgs

        for i in range(1, len(candles) - 1):
            prev = candles[i - 1]
            curr = candles[i]
            next_c = candles[i + 1]

            # Bullish FVG: gap between prev high and next low
            if prev["high"] < next_c["low"]:
                bullish_fvgs.append(FairValueGap(
                    type="bullish",
                    high=next_c["low"],   # top of gap
                    low=prev["high"],     # bottom of gap
                    index=i
                ))

            # Bearish FVG: gap between next high and prev low
            if prev["low"] > next_c["high"]:
                bearish_fvgs.append(FairValueGap(
                    type="bearish",
                    high=prev["low"],     # top of gap
                    low=next_c["high"],   # bottom of gap
                    index=i
                ))

        # Check if FVGs are filled
        if candles:
            last_price = candles[-1]["close"]
            for fvg in bullish_fvgs:
                if last_price < fvg.low:
                    fvg.filled = True
            for fvg in bearish_fvgs:
                if last_price > fvg.high:
                    fvg.filled = True

        # Keep only unfilled, last 3
        bullish_fvgs = [f for f in bullish_fvgs if not f.filled][-3:]
        bearish_fvgs = [f for f in bearish_fvgs if not f.filled][-3:]

        return bullish_fvgs, bearish_fvgs

    # ========== LIQUIDITY SWEEPS ==========

    def _detect_liquidity_sweep(self, candles: list, swing_highs: list,
                                 swing_lows: list) -> tuple:
        """
        Detect if recent price action swept liquidity.

        Buy-side liquidity sweep: price spiked above recent swing high then closed below
        Sell-side liquidity sweep: price spiked below recent swing low then closed above
        """
        if len(candles) < 2 or (not swing_highs and not swing_lows):
            return False, ""

        last = candles[-1]
        prev = candles[-2]

        # Check sell-side sweep (swept lows = bearish liquidity grab → bullish)
        if swing_lows:
            recent_low = swing_lows[-1][1]
            if (last["low"] <= recent_low and last["close"] > recent_low):
                return True, "sell_side"
            if (prev["low"] <= recent_low and prev["close"] > recent_low):
                return True, "sell_side"

        # Check buy-side sweep (swept highs = bullish liquidity grab → bearish)
        if swing_highs:
            recent_high = swing_highs[-1][1]
            if (last["high"] >= recent_high and last["close"] < recent_high):
                return True, "buy_side"
            if (prev["high"] >= recent_high and prev["close"] < recent_high):
                return True, "buy_side"

        return False, ""

    # ========== PREMIUM/DISCOUNT ZONES ==========

    def _get_price_zone(self, candles: list, current_price: float) -> str:
        """
        Determine if price is in premium, discount, or equilibrium zone.

        Uses the range of recent swing high to swing low.
        - Premium: top 30% of range (sell zone)
        - Discount: bottom 30% of range (buy zone)
        - Equilibrium: middle 40%
        """
        # Use last 20 candles for range
        recent = candles[-20:] if len(candles) >= 20 else candles
        range_high = max(c["high"] for c in recent)
        range_low = min(c["low"] for c in recent)
        range_size = range_high - range_low

        if range_size == 0:
            return "equilibrium"

        position = (current_price - range_low) / range_size

        if position >= 0.7:
            return "premium"
        elif position <= 0.3:
            return "discount"
        else:
            return "equilibrium"

    # ========== NEAREST PATTERNS ==========

    def _find_nearest_ob(self, bullish_obs: list, bearish_obs: list,
                          current_price: float, bias: str) -> Optional[OrderBlock]:
        """Find nearest relevant Order Block based on bias."""
        if bias == "UP":
            # For longs, look for bullish OB below price
            candidates = [ob for ob in bullish_obs if ob.high <= current_price]
            if candidates:
                return min(candidates, key=lambda ob: current_price - ob.high)
        elif bias == "DOWN":
            # For shorts, look for bearish OB above price
            candidates = [ob for ob in bearish_obs if ob.low >= current_price]
            if candidates:
                return min(candidates, key=lambda ob: ob.low - current_price)
        return None

    def _find_nearest_fvg(self, bullish_fvgs: list, bearish_fvgs: list,
                           current_price: float, bias: str) -> Optional[FairValueGap]:
        """Find nearest relevant FVG based on bias."""
        if bias == "UP":
            # For longs, bullish FVG below price = support
            candidates = [f for f in bullish_fvgs if f.high <= current_price]
            if candidates:
                return min(candidates, key=lambda f: current_price - f.high)
        elif bias == "DOWN":
            # For shorts, bearish FVG above price = resistance
            candidates = [f for f in bearish_fvgs if f.low >= current_price]
            if candidates:
                return min(candidates, key=lambda f: f.low - current_price)
        return None

    # ========== CONFLUENCE SCORING ==========

    def _calculate_confluence(self, bias: str, structure: str,
                               latest_break: Optional[StructureBreak],
                               nearest_ob: Optional[OrderBlock],
                               nearest_fvg: Optional[FairValueGap],
                               liquidity_swept: bool, sweep_direction: str,
                               zone: str, current_price: float) -> tuple:
        """
        Calculate confluence score (0-100) based on how many SMC factors align.

        Scoring:
        - Market structure alignment: +25
        - Order Block present: +20
        - Fair Value Gap present: +15
        - Liquidity sweep confirmation: +20
        - Premium/Discount zone alignment: +20

        Minimum 50 = tradeable signal
        """
        score = 0
        details = []

        # 1. Market Structure alignment (+25)
        if bias == "UP" and structure == "bullish":
            score += 25
            details.append("✅ Structure: Bullish (HH + HL) +25")
        elif bias == "DOWN" and structure == "bearish":
            score += 25
            details.append("✅ Structure: Bearish (LH + LL) +25")
        elif structure == "ranging":
            score += 5
            details.append("⚠️ Structure: Ranging +5")
        else:
            # Counter-trend
            score += 0
            details.append(f"❌ Structure: {structure} vs bias {bias} +0")

        # 2. Order Block present (+20)
        if nearest_ob:
            score += 20
            details.append(f"✅ Order Block: {nearest_ob.type} @ {nearest_ob.low:.5g}-{nearest_ob.high:.5g} +20")
        else:
            details.append("❌ No relevant Order Block nearby +0")

        # 3. Fair Value Gap present (+15)
        if nearest_fvg:
            score += 15
            details.append(f"✅ FVG: {nearest_fvg.type} @ {nearest_fvg.low:.5g}-{nearest_fvg.high:.5g} +15")
        else:
            details.append("❌ No relevant FVG nearby +0")

        # 4. Liquidity sweep confirmation (+20)
        if liquidity_swept:
            if (bias == "UP" and sweep_direction == "sell_side"):
                # Swept sell-side liquidity → expecting bullish reversal
                score += 20
                details.append("✅ Liquidity: Sell-side swept (bullish) +20")
            elif (bias == "DOWN" and sweep_direction == "buy_side"):
                # Swept buy-side liquidity → expecting bearish reversal
                score += 20
                details.append("✅ Liquidity: Buy-side swept (bearish) +20")
            else:
                score += 5
                details.append(f"⚠️ Liquidity swept ({sweep_direction}) but not aligned +5")
        else:
            details.append("❌ No liquidity sweep detected +0")

        # 5. Premium/Discount zone alignment (+20)
        if bias == "UP" and zone == "discount":
            score += 20
            details.append("✅ Zone: Discount (buy zone) +20")
        elif bias == "DOWN" and zone == "premium":
            score += 20
            details.append("✅ Zone: Premium (sell zone) +20")
        elif zone == "equilibrium":
            score += 10
            details.append("⚠️ Zone: Equilibrium +10")
        else:
            score += 0
            details.append(f"❌ Zone: {zone} vs bias {bias} +0")

        return min(score, 100), details

    # ========== FORMATTING ==========

    @staticmethod
    def format_smc_analysis(analysis: SMCAnalysis) -> str:
        """Format SMC analysis for Telegram message."""
        # Grade
        if analysis.confluence_score >= 70:
            grade = "🟢 HIGH"
            emoji = "🔥"
        elif analysis.confluence_score >= 50:
            grade = "🟡 MEDIUM"
            emoji = "⚡"
        elif analysis.confluence_score >= 30:
            grade = "🟠 LOW"
            emoji = "⚠️"
        else:
            grade = "🔴 VERY LOW"
            emoji = "❌"

        lines = [
            f"{emoji} *SMC Confluence: {analysis.confluence_score}/100* ({grade})",
            f"",
            f"📐 *Market Structure:* `{analysis.market_structure.upper()}`",
        ]

        if analysis.latest_break:
            brk = analysis.latest_break
            brk_type = brk.type.replace("_", " ").upper()
            lines.append(f"  → {brk_type} @ `{brk.level:.5g}`")

        lines.append(f"📍 *Zone:* `{analysis.zone.upper()}`")

        if analysis.nearest_ob:
            ob = analysis.nearest_ob
            lines.append(
                f"🧱 *Order Block:* {ob.type} `{ob.low:.5g} - {ob.high:.5g}`"
            )

        if analysis.nearest_fvg:
            fvg = analysis.nearest_fvg
            lines.append(
                f"📊 *FVG:* {fvg.type} `{fvg.low:.5g} - {fvg.high:.5g}`"
            )

        if analysis.liquidity_swept:
            lines.append(f"💧 *Liquidity:* {analysis.sweep_direction} swept ✅")

        lines.append(f"")
        lines.append(f"📝 *Details:*")
        for detail in analysis.confluence_details:
            lines.append(f"  {detail}")

        return "\n".join(lines)

    @staticmethod
    def get_signal_recommendation(score: int) -> str:
        """Get trading recommendation based on confluence score."""
        if score >= 70:
            return "🟢 STRONG SIGNAL — High confluence, good R:R expected"
        elif score >= 50:
            return "🟡 VALID SIGNAL — Moderate confluence, manage risk"
        elif score >= 30:
            return "🟠 WEAK SIGNAL — Low confluence, consider skipping"
        else:
            return "🔴 NO TRADE — Insufficient confluence, wait for better setup"
