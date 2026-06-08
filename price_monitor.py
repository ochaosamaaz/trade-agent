"""
Price Monitor Module
Background engine that monitors real-time prices via:
- Binance WebSocket for Crypto (real-time, no rate limit)
- Polling for Forex (interval-based)

Checks active alerts (SL/TP) and triggers notifications.
"""

import asyncio
import json
import logging
from typing import Callable, Optional
import aiohttp

logger = logging.getLogger(__name__)


class PriceMonitor:
    """
    Real-time price monitoring engine.
    - Crypto: Binance WebSocket streams
    - Forex: Periodic HTTP polling (TwelveData)
    """

    BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"
    BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"

    def __init__(self, on_price_update: Callable, check_interval: int = 5):
        """
        Args:
            on_price_update: Async callback(symbol, price) called on each price update
            check_interval: Seconds between forex polling cycles
        """
        self.on_price_update = on_price_update
        self.check_interval = check_interval
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._forex_task: Optional[asyncio.Task] = None
        self._crypto_symbols: set = set()
        self._forex_symbols: set = set()
        self._ws_connection = None
        self._latest_prices: dict = {}  # symbol -> price cache

    @property
    def is_running(self) -> bool:
        return self._running

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get cached latest price for a symbol."""
        return self._latest_prices.get(symbol.upper())

    def add_crypto_symbol(self, symbol: str):
        """Add a crypto symbol to monitor."""
        self._crypto_symbols.add(symbol.upper())

    def add_forex_symbol(self, symbol: str):
        """Add a forex symbol to monitor."""
        self._forex_symbols.add(symbol.upper())

    def remove_symbol(self, symbol: str):
        """Remove a symbol from monitoring."""
        symbol = symbol.upper()
        self._crypto_symbols.discard(symbol)
        self._forex_symbols.discard(symbol)

    async def start(self):
        """Start the price monitoring engine."""
        if self._running:
            return
        self._running = True
        logger.info("🟢 Price Monitor started")

        # Start crypto WebSocket monitoring
        if self._crypto_symbols:
            self._ws_task = asyncio.create_task(self._crypto_ws_loop())

        # Start forex polling
        if self._forex_symbols:
            self._forex_task = asyncio.create_task(self._forex_poll_loop())

        # Start a general crypto polling as fallback (covers all symbols)
        self._crypto_poll_task = asyncio.create_task(self._crypto_poll_loop())

    async def stop(self):
        """Stop the price monitoring engine."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._forex_task:
            self._forex_task.cancel()
        if hasattr(self, '_crypto_poll_task') and self._crypto_poll_task:
            self._crypto_poll_task.cancel()
        logger.info("🔴 Price Monitor stopped")

    async def restart_with_symbols(self, crypto_symbols: set, forex_symbols: set):
        """Restart monitoring with updated symbol sets."""
        await self.stop()
        await asyncio.sleep(1)
        self._crypto_symbols = crypto_symbols
        self._forex_symbols = forex_symbols
        await self.start()

    # ========== CRYPTO WEBSOCKET ==========

    async def _crypto_ws_loop(self):
        """Connect to Binance WebSocket for real-time crypto prices."""
        while self._running:
            try:
                if not self._crypto_symbols:
                    await asyncio.sleep(5)
                    continue

                # Build stream URL for multiple symbols
                streams = [f"{s.lower()}@trade" for s in self._crypto_symbols]
                stream_url = f"{self.BINANCE_WS_BASE}/{'/'.join(streams)}"

                if len(self._crypto_symbols) > 1:
                    # Use combined stream
                    streams_param = "/".join(
                        [f"{s.lower()}@trade" for s in self._crypto_symbols]
                    )
                    stream_url = f"wss://stream.binance.com:9443/stream?streams={streams_param}"

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(stream_url) as ws:
                        logger.info(f"📡 WebSocket connected for {self._crypto_symbols}")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                # Handle combined stream format
                                if "stream" in data:
                                    data = data["data"]
                                if "s" in data and "p" in data:
                                    symbol = data["s"].upper()
                                    price = float(data["p"])
                                    self._latest_prices[symbol] = price
                                    await self.on_price_update(symbol, price)
                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)  # Reconnect after 5s

    # ========== CRYPTO POLLING (FALLBACK) ==========

    async def _crypto_poll_loop(self):
        """Fallback: Poll Binance REST API for crypto prices."""
        while self._running:
            try:
                if not self._crypto_symbols:
                    await asyncio.sleep(self.check_interval)
                    continue

                async with aiohttp.ClientSession() as session:
                    for symbol in list(self._crypto_symbols):
                        if not self._running:
                            break
                        try:
                            url = f"{self.BINANCE_TICKER_URL}?symbol={symbol}"
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    price = float(data["price"])
                                    self._latest_prices[symbol] = price
                                    await self.on_price_update(symbol, price)
                        except Exception as e:
                            logger.error(f"Crypto poll error for {symbol}: {e}")

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Crypto poll loop error: {e}")
                await asyncio.sleep(self.check_interval)

    # ========== FOREX POLLING ==========

    async def _forex_poll_loop(self):
        """Poll forex prices from TwelveData (or alternative free API)."""
        while self._running:
            try:
                if not self._forex_symbols:
                    await asyncio.sleep(self.check_interval * 2)
                    continue

                async with aiohttp.ClientSession() as session:
                    for symbol in list(self._forex_symbols):
                        if not self._running:
                            break
                        try:
                            price = await self._fetch_forex_price(session, symbol)
                            if price:
                                self._latest_prices[symbol] = price
                                await self.on_price_update(symbol, price)
                        except Exception as e:
                            logger.error(f"Forex poll error for {symbol}: {e}")

                # Forex polling interval is longer to respect rate limits
                await asyncio.sleep(max(self.check_interval * 3, 15))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Forex poll loop error: {e}")
                await asyncio.sleep(30)

    async def _fetch_forex_price(self, session: aiohttp.ClientSession, 
                                  symbol: str) -> Optional[float]:
        """Fetch a single forex pair price."""
        # Format for TwelveData
        if len(symbol) == 6 and "/" not in symbol:
            formatted = f"{symbol[:3]}/{symbol[3:]}"
        else:
            formatted = symbol

        url = "https://api.twelvedata.com/price"
        params = {"symbol": formatted, "apikey": "demo"}

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
        """One-shot price fetch for a symbol."""
        if is_crypto:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{self.BINANCE_TICKER_URL}?symbol={symbol.upper()}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = float(data["price"])
                            self._latest_prices[symbol.upper()] = price
                            return price
            except Exception as e:
                logger.error(f"Single fetch error: {e}")
                return None
        else:
            async with aiohttp.ClientSession() as session:
                return await self._fetch_forex_price(session, symbol)
