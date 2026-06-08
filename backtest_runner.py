"""
Backtest Runner - CLI Script
Run backtests from command line and display results.

Usage:
    python backtest_runner.py BTCUSDT 90
    python backtest_runner.py EURUSD 60 --forex
    python backtest_runner.py --all 30
"""

import asyncio
import sys
import argparse
from backtester import Backtester
from config import CRYPTO_PAIRS, FOREX_PAIRS


def print_divider():
    print("━" * 55)


def print_result(result):
    """Print backtest result in a nice CLI format."""
    print()
    print_divider()
    print(f"  📊 BACKTEST RESULT — {result.symbol}")
    print_divider()
    print()

    # Grade
    if result.win_rate >= 60:
        grade = "🟢 EXCELLENT"
    elif result.win_rate >= 50:
        grade = "🟡 GOOD"
    elif result.win_rate >= 40:
        grade = "🟠 AVERAGE"
    else:
        grade = "🔴 POOR"

    print(f"  ⏱️  Period:         {result.total_days} days")
    print(f"  📐 Strategy:       Quantum Physics Theory")
    print()
    print(f"  ━━━ PERFORMANCE ━━━")
    print(f"  🎯 Win Rate:       {result.win_rate:.1f}%  {grade}")
    print(f"  📊 Total Trades:   {result.total_trades}")
    print(f"  ✅ Wins:           {result.wins}")
    print(f"  ❌ Losses:         {result.losses}")
    print(f"  ⏭️  No Entry:       {result.no_entry}")
    print(f"  ⚖️  Neutral Days:   {result.neutral_days}")
    print()
    print(f"  ━━━ P&L ━━━")
    pnl_sign = "+" if result.total_pnl_pct >= 0 else ""
    print(f"  💰 Total PnL:      {pnl_sign}{result.total_pnl_pct:.2f}%")
    print(f"  ✅ Avg Win:        +{result.avg_win_pct:.2f}%")
    print(f"  ❌ Avg Loss:       {result.avg_loss_pct:.2f}%")
    print(f"  📊 Profit Factor:  {result.profit_factor:.2f}")
    print(f"  📐 Avg R:R:        1:{result.avg_rr:.1f}")
    print()
    print(f"  ━━━ RISK ━━━")
    print(f"  📉 Max Drawdown:   {result.max_drawdown_pct:.2f}%")
    print(f"  🔥 Max Consec W:   {result.max_consecutive_wins}")
    print(f"  ❄️  Max Consec L:   {result.max_consecutive_losses}")
    print()
    print_divider()

    # Trade log
    if result.trades:
        actual_trades = [t for t in result.trades if t.result in ("WIN", "LOSS")]
        if actual_trades:
            print()
            print(f"  📋 TRADE LOG (last 10):")
            print(f"  {'Date':<12} {'Bias':<5} {'Entry':<6} {'PnL':>8}  Result")
            print(f"  {'-'*45}")
            for t in actual_trades[-10:]:
                emoji = "✅" if t.result == "WIN" else "❌"
                print(f"  {t.date:<12} {t.bias:<5} {t.entry_type:<6} "
                      f"{t.pnl_pct:>+7.2f}%  {emoji}")
            print()

    print_divider()
    print("  ⚠️  Past performance ≠ future results!")
    print_divider()
    print()


async def run_single(symbol: str, days: int, is_crypto: bool):
    """Run backtest for a single pair."""
    bt = Backtester()
    market_type = "Crypto" if is_crypto else "Forex"
    print(f"\n⏳ Running backtest: {symbol} ({market_type}) | {days} days...")

    result = await bt.run_backtest(symbol, days, is_crypto)

    if result:
        print_result(result)
    else:
        print(f"❌ Failed to fetch data for {symbol}. Check if pair is valid.")


async def run_all(days: int):
    """Run backtest for all supported pairs."""
    bt = Backtester()
    results = []

    print(f"\n⏳ Running backtest for ALL pairs | {days} days...")
    print(f"   Crypto: {len(CRYPTO_PAIRS)} pairs | Forex: {len(FOREX_PAIRS)} pairs")
    print()

    # Crypto
    for symbol in CRYPTO_PAIRS:
        print(f"  📡 {symbol}...", end="", flush=True)
        result = await bt.run_backtest(symbol, days, is_crypto=True)
        if result:
            results.append(result)
            emoji = "✅" if result.win_rate >= 50 else "❌"
            print(f" {emoji} WR: {result.win_rate:.1f}% | PnL: {result.total_pnl_pct:+.2f}%")
        else:
            print(" ❌ Failed")
        await asyncio.sleep(0.5)  # Rate limit respect

    # Forex
    for symbol in FOREX_PAIRS:
        print(f"  📡 {symbol}...", end="", flush=True)
        result = await bt.run_backtest(symbol, days, is_crypto=False)
        if result:
            results.append(result)
            emoji = "✅" if result.win_rate >= 50 else "❌"
            print(f" {emoji} WR: {result.win_rate:.1f}% | PnL: {result.total_pnl_pct:+.2f}%")
        else:
            print(" ❌ Failed (demo API limit)")
        await asyncio.sleep(1)  # Forex API slower rate limit

    # Summary
    if results:
        print()
        print_divider()
        print(f"  📊 SUMMARY — ALL PAIRS ({days} days)")
        print_divider()
        print()
        print(f"  {'Pair':<10} {'WR':>6} {'PnL':>8} {'Trades':>7} {'W/L':>7} {'PF':>5}")
        print(f"  {'-'*50}")

        total_wins = 0
        total_losses = 0
        total_pnl = 0

        for r in sorted(results, key=lambda x: x.win_rate, reverse=True):
            emoji = "🟢" if r.win_rate >= 50 else "🔴"
            pf_str = f"{r.profit_factor:.1f}" if r.profit_factor < 100 else "∞"
            print(f"  {emoji} {r.symbol:<8} {r.win_rate:>5.1f}% "
                  f"{r.total_pnl_pct:>+7.2f}% {r.total_trades:>5} "
                  f"{r.wins:>3}/{r.losses:<3} {pf_str:>5}")
            total_wins += r.wins
            total_losses += r.losses
            total_pnl += r.total_pnl_pct

        total_trades = total_wins + total_losses
        overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

        print(f"  {'-'*50}")
        print(f"  📊 Overall: WR {overall_wr:.1f}% | "
              f"PnL {total_pnl:+.2f}% | "
              f"{total_trades} trades ({total_wins}W/{total_losses}L)")
        print()
        print_divider()


def main():
    parser = argparse.ArgumentParser(
        description="Backtest Quantum Physics Trading Theory"
    )
    parser.add_argument("symbol", nargs="?", default=None,
                        help="Trading pair (e.g., BTCUSDT, EURUSD)")
    parser.add_argument("days", nargs="?", type=int, default=30,
                        help="Number of days to backtest (default: 30)")
    parser.add_argument("--forex", action="store_true",
                        help="Treat symbol as forex pair")
    parser.add_argument("--all", action="store_true",
                        help="Backtest all supported pairs")

    args = parser.parse_args()

    if args.all:
        days = args.days if args.symbol is None else int(args.symbol) if args.symbol.isdigit() else args.days
        asyncio.run(run_all(days))
    elif args.symbol:
        symbol = args.symbol.upper()
        is_crypto = not args.forex

        # Auto-detect
        if symbol in FOREX_PAIRS:
            is_crypto = False
        elif symbol in CRYPTO_PAIRS:
            is_crypto = True

        asyncio.run(run_single(symbol, args.days, is_crypto))
    else:
        # Default: backtest BTCUSDT 30 days
        print("No symbol specified. Running default: BTCUSDT 30 days")
        asyncio.run(run_single("BTCUSDT", 30, True))


if __name__ == "__main__":
    main()
