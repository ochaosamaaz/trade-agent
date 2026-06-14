"""
Price Monitor Module
Background engine that monitors real-time prices.
- Crypto: Binance REST polling (with SSL bypass for restricted networks)
- Forex: TwelveData polling

Checks active alerts (SL/TP) and triggers notifications.
"""

import asyncio
import logging
from typing import Callable, Optional
import aiohttp

logger = logging.getLogger(__name__)


class PriceMonitor:
    """
    Real-time price monitoring engine using REST polling.
    Compatible with restricted networks (SSL bypass).
    """

    BINANCE_ENDPOINTS = [
        "https://api4.binance.com/api/v3",
        "https://api3.binance.com/api/v3",
        "https://api2.binance.com/api/v3",
        "https://api1.binance.com/api/v3",
        "https://api.binance.com/api/v3",
        "https://data-api.binance.vision/api/v3",
    ]

    TWELVE_DATA_BASE = "https://api.twelvedata.com"

    def __init__(self, on_price_update: Callable, check_interval: int = 10):
        """
        Args:
            on_price_update: Async callback(symbol, price) called on each price update
            check_interval: Seconds between polling cycles
        """
        self.on_price_update = on_price_update
        self.check_interval = check_interval
        self._running = False
        self._crypto_task: Optional[asyncio.Task] = None
        self._forex_task: Optional[asyncio.Task] = None
        self._crypto_symbols: set = set()
        self._forex_symbols: set = set()
        self._latest_prices: dict = {}
        self._working_binance = None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get cached latest price for a symbol."""
        return self._latest_prices.get(symbol.upper())

    def add_crypto_symbol(self, symbol: str):
        self._crypto_symbols.add(symbol.upper())

    def add_forex_symbol(self, symbol: str):
        self._forex_symbols.add(symbol.upper())

    def remove_symbol(self, symbol: str):
        symbol = symbol.upper()
        self._crypto_symbols.discard(symbol)
        self._forex_symbols.discard(symbol)

    async def start(self):
        """Start the price monitoring engine."""
        if self._running:
            return
        self._running = True
        logger.info("🟢 Price Monitor started")

        self._crypto_task = asyncio.create_task(self._crypto_poll_loop())
        self._forex_task = asyncio.create_task(self._forex_poll_loop())

    async def stop(self):
        """Stop the price monitoring engine."""
        self._running = False
        if self._crypto_task:
            self._crypto_task.cancel()
        if self._forex_task:
            self._forex_task.cancel()
        logger.info("🔴 Price Monitor stopped")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Create session with SSL bypass."""
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=15)
        )

    # ========== CRYPTO POLLING ==========

    async def _crypto_poll_loop(self):
        """Poll Binance for crypto prices with endpoint fallback."""
        while self._running:
            try:
                if not self._crypto_symbols:
                    await asyncio.sleep(self.check_interval)
                    continue

                async with await self._get_session() as session:
                    for symbol in list(self._crypto_symbols):
                        if not self._running:
                            break
                        try:
                            price = await self._fetch_binance_price(session, symbol)
                            if price:
                                self._latest_prices[symbol] = price
                                await self.on_price_update(symbol, price)
                        except Exception as e:
                            logger.debug(f"Crypto poll error for {symbol}: {e}")

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Crypto poll loop error: {e}")
                await asyncio.sleep(self.check_interval * 2)

    async def _fetch_binance_price(self, session: aiohttp.ClientSession,
                                    symbol: str) -> Optional[float]:
        """Fetch single crypto price with endpoint fallback."""
        endpoints = self.BINANCE_ENDPOINTS
        if self._working_binance:
            endpoints = [self._working_binance] + [
                e for e in self.BINANCE_ENDPOINTS if e != self._working_binance
            ]

        for base_url in endpoints:
            try:
                url = f"{base_url}/ticker/price?symbol={symbol}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._working_binance = base_url
                        return float(data["price"])
            except Exception:
                continue
        return None

    # ========== FOREX POLLING ==========

    async def _forex_poll_loop(self):
        """Poll TwelveData for forex prices."""
        while self._running:
            try:
                if not self._forex_symbols:
                    await asyncio.sleep(self.check_interval * 3)
                    continue

                async with await self._get_session() as session:
                    for symbol in list(self._forex_symbols):
                        if not self._running:
                            break
                        try:
                            price = await self._fetch_forex_price(session, symbol)
                            if price:
                                self._latest_prices[symbol] = price
                                await self.on_price_update(symbol, price)
                        except Exception as e:
                            logger.debug(f"Forex poll error for {symbol}: {e}")

                # Longer interval for forex (rate limited)
                await asyncio.sleep(max(self.check_interval * 3, 20))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Forex poll loop error: {e}")
                await asyncio.sleep(30)

    async def _fetch_forex_price(self, session: aiohttp.ClientSession,
                                  symbol: str) -> Optional[float]:
        """Fetch forex price from TwelveData."""
        import os
        api_key = os.getenv("TWELVE_DATA_API_KEY", "demo")

        # Format symbol
        special = {"XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD"}
        if symbol.upper() in special:
            formatted = special[symbol.upper()]
        elif len(symbol) == 6 and "/" not in symbol:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        else:
            formatted = symbol

        url = f"{self.TWELVE_DATA_BASE}/price"
        params = {"symbol": formatted, "apikey": api_key}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "price" in data:
                        return float(data["price"])
        except Exception:
            pass
        return None

    # ========== UTILITY ==========

    async def fetch_single_price(self, symbol: str, is_crypto: bool = True) -> Optional[float]:
        """One-shot price fetch."""
        async with await self._get_session() as session:
            if is_crypto:
                return await self._fetch_binance_price(session, symbol)
            else:
                return await self._fetch_forex_price(session, symbol)
