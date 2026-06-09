"""
Data Fetcher Module
Fetches OHLC data for Forex and Crypto pairs from free APIs.

- Crypto: Binance Public API (with fallback mirrors)
- Forex: Twelve Data API (with API key support)
- Real-time: Multiple sources with fallback
"""

import aiohttp
import ssl
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


def _get_ssl_context():
    """Create an SSL context that works with various network configurations."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get_connector():
    """Create aiohttp connector with SSL bypass for restricted networks."""
    return aiohttp.TCPConnector(ssl=False)


class DataFetcher:
    """Fetches market data from public APIs with fallback support."""
    
    # Primary and fallback Binance endpoints
    # Includes mirrors that work in regions where Binance is blocked
    BINANCE_ENDPOINTS = [
        "https://api4.binance.com/api/v3",
        "https://api3.binance.com/api/v3",
        "https://api2.binance.com/api/v3",
        "https://api1.binance.com/api/v3",
        "https://api.binance.com/api/v3",
        "https://data-api.binance.vision/api/v3",
    ]
    
    # TwelveData API
    TWELVE_DATA_BASE = "https://api.twelvedata.com"
    
    def __init__(self, twelve_data_key: str = None):
        """
        Args:
            twelve_data_key: TwelveData API key. Uses 'demo' if not provided.
        """
        import os
        self.twelve_data_key = twelve_data_key or os.getenv("TWELVE_DATA_API_KEY", "demo")
        self._working_binance = None  # Cache the working endpoint
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Create a session with SSL bypass for restricted networks."""
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=15)
        )
    
    async def _binance_request(self, path: str, params: dict = None) -> Optional[dict]:
        """
        Make a Binance API request with automatic endpoint fallback.
        Tries multiple endpoints if primary fails.
        """
        endpoints = self.BINANCE_ENDPOINTS
        
        # Try cached working endpoint first
        if self._working_binance:
            endpoints = [self._working_binance] + [
                e for e in self.BINANCE_ENDPOINTS if e != self._working_binance
            ]
        
        async with await self._get_session() as session:
            for base_url in endpoints:
                url = f"{base_url}{path}"
                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            self._working_binance = base_url
                            return await resp.json()
                except Exception as e:
                    continue
        
        return None
    
    async def fetch_crypto_klines(self, symbol: str, interval: str = "1d", 
                                   limit: int = 2) -> Optional[list]:
        """
        Fetch crypto OHLC data from Binance.
        """
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit
        }
        
        data = await self._binance_request("/klines", params)
        
        if data:
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
        return None
    
    async def fetch_forex_data(self, symbol: str) -> Optional[list]:
        """
        Fetch forex OHLC data from TwelveData.
        Handles special symbols like XAUUSD properly.
        """
        formatted = self._format_forex_symbol(symbol)
        
        url = f"{self.TWELVE_DATA_BASE}/time_series"
        params = {
            "symbol": formatted,
            "interval": "1day",
            "outputsize": 3,
            "apikey": self.twelve_data_key
        }
        
        try:
            async with await self._get_session() as session:
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
                        elif "message" in data:
                            print(f"TwelveData error for {symbol}: {data['message']}")
                        return None
                    else:
                        return None
        except Exception as e:
            print(f"Error fetching forex data: {e}")
            return None
    
    def _format_forex_symbol(self, symbol: str) -> str:
        """
        Format symbol for TwelveData API.
        XAUUSD → XAU/USD
        EURUSD → EUR/USD
        """
        if "/" in symbol:
            return symbol
        
        # Known commodity/metal pairs (3+3 format but not standard forex)
        special_pairs = {
            "XAUUSD": "XAU/USD",
            "XAGUSD": "XAG/USD",
            "XAUEUR": "XAU/EUR",
            "WTIUSD": "WTI/USD",
        }
        
        if symbol.upper() in special_pairs:
            return special_pairs[symbol.upper()]
        
        # Standard forex: first 3 chars / last 3 chars
        if len(symbol) == 6:
            return f"{symbol[:3]}/{symbol[3:]}"
        
        # Fallback
        return symbol
    
    async def get_analysis_data(self, symbol: str, is_crypto: bool = True) -> Optional[dict]:
        """
        Get all data needed for Quantum analysis.
        """
        if is_crypto:
            candles = await self.fetch_crypto_klines(symbol, "1d", 3)
        else:
            candles = await self.fetch_forex_data(symbol)
        
        if not candles or len(candles) < 2:
            return None
        
        current = candles[-1]
        previous = candles[-2]
        
        return {
            "current_open": current.open,
            "previous_open": previous.open,
            "prev_high": previous.high,
            "prev_low": previous.low,
            "prev_close": previous.close,
            "pdh": previous.high,
            "pdl": previous.low,
        }

    # ========== REAL-TIME PRICE METHODS ==========

    async def get_realtime_price_crypto(self, symbol: str) -> Optional[float]:
        """Get real-time crypto price from Binance with fallback."""
        data = await self._binance_request("/ticker/price", {"symbol": symbol.upper()})
        if data and "price" in data:
            return float(data["price"])
        return None

    async def get_realtime_price_forex(self, symbol: str) -> Optional[float]:
        """Get real-time forex/commodity price from TwelveData."""
        formatted = self._format_forex_symbol(symbol)
        
        url = f"{self.TWELVE_DATA_BASE}/price"
        params = {"symbol": formatted, "apikey": self.twelve_data_key}
        
        try:
            async with await self._get_session() as session:
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
        """Get real-time price for any symbol."""
        if is_crypto:
            return await self.get_realtime_price_crypto(symbol)
        else:
            return await self.get_realtime_price_forex(symbol)

    async def get_crypto_24h_stats(self, symbol: str) -> Optional[dict]:
        """Get 24h statistics for a crypto pair from Binance."""
        data = await self._binance_request("/ticker/24hr", {"symbol": symbol.upper()})
        
        if data and "lastPrice" in data:
            return {
                "price": float(data["lastPrice"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "change_pct": float(data["priceChangePercent"]),
                "volume": float(data["volume"]),
                "open": float(data["openPrice"]),
            }
        return None

    async def get_multi_crypto_prices(self, symbols: list) -> dict:
        """Get real-time prices for multiple crypto pairs."""
        data = await self._binance_request("/ticker/price")
        
        if data and isinstance(data, list):
            prices = {}
            symbols_upper = {s.upper() for s in symbols}
            for item in data:
                if item["symbol"] in symbols_upper:
                    prices[item["symbol"]] = float(item["price"])
            return prices
        return {}
