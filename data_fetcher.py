"""
Data Fetcher Module
Fetches OHLC data for Forex and Crypto pairs from free APIs.

- Crypto: Binance Public API (no key needed)
- Forex: Twelve Data API or fallback to manual input
- Real-time: Binance ticker for instant price checks
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
    BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
    BINANCE_24H = "https://api.binance.com/api/v3/ticker/24hr"
    
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

    # ========== REAL-TIME PRICE METHODS ==========

    async def get_realtime_price_crypto(self, symbol: str) -> Optional[float]:
        """
        Get real-time price for a crypto pair from Binance ticker.
        
        Args:
            symbol: e.g., 'BTCUSDT'
            
        Returns:
            Current price as float, or None on error
        """
        url = self.BINANCE_TICKER
        params = {"symbol": symbol.upper()}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data["price"])
                    return None
        except Exception as e:
            print(f"Error fetching real-time crypto price: {e}")
            return None

    async def get_realtime_price_forex(self, symbol: str) -> Optional[float]:
        """
        Get real-time price for a forex pair from TwelveData.
        
        Args:
            symbol: e.g., 'EURUSD'
            
        Returns:
            Current price as float, or None on error
        """
        if "/" not in symbol and len(symbol) == 6:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        elif "/" not in symbol and len(symbol) > 6:
            # Handle XAUUSD style
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        else:
            formatted = symbol
        
        url = "https://api.twelvedata.com/price"
        params = {"symbol": formatted, "apikey": "demo"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "price" in data:
                            return float(data["price"])
                    return None
        except Exception as e:
            print(f"Error fetching real-time forex price: {e}")
            return None

    async def get_realtime_price(self, symbol: str, is_crypto: bool = True) -> Optional[float]:
        """
        Get real-time price for any symbol.
        
        Args:
            symbol: Trading pair
            is_crypto: True for crypto (Binance), False for forex (TwelveData)
            
        Returns:
            Current price as float, or None
        """
        if is_crypto:
            return await self.get_realtime_price_crypto(symbol)
        else:
            return await self.get_realtime_price_forex(symbol)

    async def get_crypto_24h_stats(self, symbol: str) -> Optional[dict]:
        """
        Get 24h statistics for a crypto pair.
        
        Returns dict with:
        - price: current price
        - high_24h: 24h high
        - low_24h: 24h low
        - change_pct: 24h change percentage
        - volume: 24h volume
        """
        url = self.BINANCE_24H
        params = {"symbol": symbol.upper()}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "price": float(data["lastPrice"]),
                            "high_24h": float(data["highPrice"]),
                            "low_24h": float(data["lowPrice"]),
                            "change_pct": float(data["priceChangePercent"]),
                            "volume": float(data["volume"]),
                            "open": float(data["openPrice"]),
                        }
                    return None
        except Exception as e:
            print(f"Error fetching 24h stats: {e}")
            return None

    async def get_multi_crypto_prices(self, symbols: list) -> dict:
        """
        Get real-time prices for multiple crypto pairs in one call.
        
        Args:
            symbols: List of symbols, e.g., ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            Dict of symbol -> price
        """
        url = self.BINANCE_TICKER
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch all tickers at once
                async with session.get(url) as resp:
                    if resp.status == 200:
                        all_data = await resp.json()
                        prices = {}
                        symbols_upper = {s.upper() for s in symbols}
                        for item in all_data:
                            if item["symbol"] in symbols_upper:
                                prices[item["symbol"]] = float(item["price"])
                        return prices
                    return {}
        except Exception as e:
            print(f"Error fetching multi prices: {e}")
            return {}
