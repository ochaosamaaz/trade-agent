"""
Pivot Point Calculator
Calculates Standard (Floor) Pivot Points with Support and Resistance levels.
Used for determining entry zones in the Quantum Physics Trading Theory.
"""


def calculate_pivot_points(high: float, low: float, close: float) -> dict:
    """
    Calculate Standard Pivot Points from previous day's High, Low, Close.
    
    Returns:
        dict with keys: PP, R1, R2, R3, S1, S2, S3
    """
    pp = (high + low + close) / 3
    
    r1 = (2 * pp) - low
    r2 = pp + (high - low)
    r3 = high + 2 * (pp - low)
    
    s1 = (2 * pp) - high
    s2 = pp - (high - low)
    s3 = low - 2 * (high - pp)
    
    return {
        "PP": round(pp, 5),
        "R1": round(r1, 5),
        "R2": round(r2, 5),
        "R3": round(r3, 5),
        "S1": round(s1, 5),
        "S2": round(s2, 5),
        "S3": round(s3, 5),
    }


def get_pivot_zone(price: float, pivots: dict) -> str:
    """
    Determine which pivot zone the current price is in.
    
    Returns a string describing the zone (e.g., 'Above R1', 'Between PP and S1', etc.)
    """
    if price >= pivots["R3"]:
        return "Above R3"
    elif price >= pivots["R2"]:
        return "Between R2 and R3"
    elif price >= pivots["R1"]:
        return "Between R1 and R2"
    elif price >= pivots["PP"]:
        return "Between PP and R1"
    elif price >= pivots["S1"]:
        return "Between S1 and PP"
    elif price >= pivots["S2"]:
        return "Between S2 and S1"
    elif price >= pivots["S3"]:
        return "Between S3 and S2"
    else:
        return "Below S3"


def format_pivot_table(pivots: dict, symbol: str) -> str:
    """
    Format pivot points into a readable string for Telegram messages.
    """
    lines = [
        f"📊 *Pivot Points — {symbol}*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🔴 R3: `{pivots['R3']}`",
        f"🔴 R2: `{pivots['R2']}`",
        f"🟠 R1: `{pivots['R1']}`",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"⚪ PP: `{pivots['PP']}`",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🟢 S1: `{pivots['S1']}`",
        f"🟢 S2: `{pivots['S2']}`",
        f"🟢 S3: `{pivots['S3']}`",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)
