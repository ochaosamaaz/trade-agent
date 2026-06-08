"""
Data Fetcher Module
Fetches OHLC data for Forex and Crypto pairs from free APIs.

- Crypto: Binance Public API (no key needed)
- Forex: Twelve Data API or fallback to manual input
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional


class MarketData:
    """Represents OHLC data for a single candle."""
    
    def __init__(self, open_price: float, high: float, low: float, 
                 close: float, timestamp: str = ""):
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp


class DataFetcher:
    """Fetches market data from public APIs."""
    
    BINANCE_BASE = "https://api.binance.com/api/v3"
    
    async def fetch_crypto_klines(self, symbol: str, interval: str = "1d", 
                                   limit: int = 2) -> Optional[list]:
        """
        Fetch crypto OHLC data from Binance.
        
        Args:
            symbol: e.g., 'BTCUSDT'
            interval: '1d', '4h', '1h', etc.
            limit: number of candles to fetch
            
        Returns:
            List of MarketData objects (most recent last)
        """
        url = f"{self.BINANCE_BASE}/klines"
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = []
                        for candle in data:
                            result.append(MarketData(
                                open_price=float(candle[1]),
                                high=float(candle[2]),
                                low=float(candle[3]),
                                close=float(candle[4]),
                                timestamp=str(candle[0])
                            ))
                        return result
                    else:
                        return None
        except Exception as e:
            print(f"Error fetching crypto data: {e}")
            return None
    
    async def fetch_forex_data(self, symbol: str) -> Optional[list]:
        """
        Fetch forex OHLC data.
        Uses Twelve Data free tier API.
        Falls back to None if unavailable (user can input manually).
        
        Args:
            symbol: e.g., 'EUR/USD' or 'EURUSD'
            
        Returns:
            List of MarketData objects or None
        """
        # Format symbol for API
        if "/" not in symbol and len(symbol) == 6:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        else:
            formatted = symbol
        
        # Try Twelve Data (free tier - 8 req/min, 800/day)
        api_key = "demo"  # Using demo key - limited but functional
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": formatted,
            "interval": "1day",
            "outputsize": 3,
            "apikey": api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "values" in data:
                            result = []
                            for candle in reversed(data["values"]):
                                result.append(MarketData(
                                    open_price=float(candle["open"]),
                                    high=float(candle["high"]),
                                    low=float(candle["low"]),
                                    close=float(candle["close"]),
                                    timestamp=candle["datetime"]
                                ))
                            return result
                        else:
                            return None
                    else:
                        return None
        except Exception as e:
            print(f"Error fetching forex data: {e}")
            return None
    
    async def get_analysis_data(self, symbol: str, is_crypto: bool = True) -> Optional[dict]:
        """
        Get all data needed for Quantum analysis.
        
        Returns dict with:
        - current_open: Today's open
        - previous_open: Yesterday's open
        - prev_high: Yesterday's high
        - prev_low: Yesterday's low
        - prev_close: Yesterday's close
        - pdh: Previous Day High
        - pdl: Previous Day Low
        """
        if is_crypto:
            candles = await self.fetch_crypto_klines(symbol, "1d", 3)
        else:
            candles = await self.fetch_forex_data(symbol)
        
        if not candles or len(candles) < 2:
            return None
        
        # Latest candle = current day (or most recent)
        current = candles[-1]
        previous = candles[-2]
        
        return {
            "current_open": current.open,
            "previous_open": previous.open,
            "prev_high": previous.high,
            "prev_low": previous.low,
            "prev_close": previous.close,
            "pdh": previous.high,  # Previous Day High
            "pdl": previous.low,   # Previous Day Low
        }
