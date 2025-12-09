# Zerodha Kite Connect API Integration Guide

This document provides all the information needed to integrate directly with Zerodha Kite API, bypassing OpenAlgo.

## Table of Contents

1. [API Documentation Links](#api-documentation-links)
2. [Getting API Credentials](#getting-api-credentials)
3. [Authentication Flow](#authentication-flow)
4. [Python SDK Setup](#python-sdk-setup)
5. [Symbol Mapping](#symbol-mapping)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [WebSocket (KiteTicker)](#websocket-kiteticker)
8. [Rate Limits](#rate-limits)
9. [Error Handling](#error-handling)
10. [Daily Token Refresh](#daily-token-refresh)

---

## API Documentation Links

Share these official documentation links with Lovable AI:

| Resource | URL |
|----------|-----|
| Kite Connect API v3 Docs | https://kite.trade/docs/connect/v3/ |
| Python SDK (pykiteconnect) | https://github.com/zerodha/pykiteconnect |
| KiteTicker WebSocket Docs | https://kite.trade/docs/connect/v3/websocket/ |
| Developer Portal | https://developers.kite.trade/ |
| API Response Codes | https://kite.trade/docs/connect/v3/#response-structure |

---

## Getting API Credentials

### Step 1: Create Kite Connect App

1. Go to https://developers.kite.trade/
2. Login with your Zerodha credentials
3. Click "Create new app"
4. Fill in app details:
   - App Name: "Portfolio Manager"
   - Redirect URL: `http://localhost:5002/api/auth/zerodha/callback` (or your production URL)
5. Note down:
   - **API Key** (public, used in login URL)
   - **API Secret** (private, used to generate session)

### Step 2: Configure Redirect URL

For development:
```
http://localhost:5002/api/auth/zerodha/callback
```

For production:
```
https://your-domain.com/api/auth/zerodha/callback
```

### Step 3: Subscription

- Kite Connect costs ₹2,000/month
- Includes 1 app with unlimited API calls (within rate limits)
- WebSocket streaming included

---

## Authentication Flow

### OAuth 2.0 Flow Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  User    │     │ Your App │     │  Kite    │     │  Zerodha │
│ Browser  │     │ Backend  │     │  Server  │     │  Login   │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ 1. Click Login │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │ 2. Redirect to Kite Login URL   │                │
     │<───────────────│                │                │
     │                │                │                │
     │ 3. User logs in at Zerodha      │                │
     │────────────────────────────────────────────────>│
     │                │                │                │
     │ 4. Redirect back with request_token              │
     │<────────────────────────────────│                │
     │                │                │                │
     │ 5. Send request_token to backend│                │
     │───────────────>│                │                │
     │                │                │                │
     │                │ 6. Exchange for access_token    │
     │                │───────────────>│                │
     │                │                │                │
     │                │ 7. Return access_token          │
     │                │<───────────────│                │
     │                │                │                │
     │ 8. Login success│                │                │
     │<───────────────│                │                │
     │                │                │                │
```

### Implementation Code

```python
from kiteconnect import KiteConnect

# Initialize
kite = KiteConnect(api_key="your_api_key")

# Step 1: Generate login URL
login_url = kite.login_url()
# Returns: https://kite.zerodha.com/connect/login?v=3&api_key=xxx

# Step 2: User visits login_url, logs in, gets redirected back with request_token
# Your callback URL receives: ?request_token=xxx&action=login&status=success

# Step 3: Exchange request_token for access_token
request_token = "received_from_callback"
data = kite.generate_session(request_token, api_secret="your_api_secret")

# Response contains:
{
    "access_token": "xxx",
    "public_token": "xxx",
    "user_id": "AB1234",
    "user_name": "John Doe",
    "user_shortname": "John",
    "email": "john@example.com",
    "user_type": "individual",
    "broker": "ZERODHA",
    "exchanges": ["NSE", "BSE", "NFO", "CDS", "BCD", "MCX"],
    "products": ["CNC", "NRML", "MIS", "BO", "CO"],
    "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
    "avatar_url": "https://...",
    "api_key": "xxx",
    "login_time": "2024-01-15 09:15:00"
}

# Step 4: Store and set access token
access_token = data["access_token"]
kite.set_access_token(access_token)

# Now you can make API calls
```

---

## Python SDK Setup

### Installation

```bash
pip install kiteconnect
```

### Requirements.txt Addition

```
kiteconnect>=5.0.0
```

### Complete ZerodhaClient Implementation

```python
"""
Zerodha Kite Connect Client for Portfolio Manager
Replaces OpenAlgo integration with direct Zerodha API access
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from kiteconnect import KiteConnect, KiteTicker

logger = logging.getLogger(__name__)


class ZerodhaClient:
    """
    Client for Zerodha Kite Connect API

    Drop-in replacement for OpenAlgoClient with same interface
    """

    def __init__(self, api_key: str, api_secret: str, access_token: str = None):
        """
        Initialize Zerodha client

        Args:
            api_key: Kite Connect API key
            api_secret: Kite Connect API secret
            access_token: Optional pre-existing access token
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.kite = KiteConnect(api_key=api_key)

        if access_token:
            self.kite.set_access_token(access_token)

        self._instrument_cache = {}  # Cache for instrument tokens
        self._session_expiry: Optional[datetime] = None

        logger.info(f"Zerodha client initialized: api_key={api_key[:8]}...")

    # ==================== Authentication ====================

    def get_login_url(self) -> str:
        """Generate Kite login URL for OAuth flow"""
        return self.kite.login_url()

    def generate_session(self, request_token: str) -> Dict:
        """
        Exchange request_token for access_token

        Args:
            request_token: Token received from OAuth callback

        Returns:
            Session data including access_token, user_id, etc.
        """
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.kite.set_access_token(data["access_token"])

            # Session expires at 3:30 AM IST next day
            now = datetime.now()
            if now.hour >= 3 and now.minute >= 30:
                # Expires tomorrow
                self._session_expiry = datetime(now.year, now.month, now.day, 3, 30) + timedelta(days=1)
            else:
                # Expires today
                self._session_expiry = datetime(now.year, now.month, now.day, 3, 30)

            logger.info(f"Session generated for user: {data.get('user_id')}")
            return data

        except Exception as e:
            logger.error(f"Failed to generate session: {e}")
            raise

    def set_access_token(self, access_token: str):
        """Set access token directly (for restored sessions)"""
        self.kite.set_access_token(access_token)
        logger.info("Access token set")

    def is_session_valid(self) -> bool:
        """Check if current session is valid"""
        if self._session_expiry and datetime.now() >= self._session_expiry:
            return False
        try:
            # Try a lightweight API call to verify
            self.kite.profile()
            return True
        except:
            return False

    # ==================== Order Management ====================

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "NRML",
        price: float = 0.0,
        exchange: str = "NFO",
        strategy: str = "PortfolioManager"
    ) -> Dict:
        """
        Place order via Kite API

        Args:
            symbol: Trading symbol (e.g., BANKNIFTY2412552000CE)
            action: BUY or SELL
            quantity: Number of units (NOT lots)
            order_type: MARKET, LIMIT, SL, SL-M
            product: NRML (overnight), MIS (intraday)
            price: Limit price (required for LIMIT/SL orders)
            exchange: NFO, MCX, NSE, etc.
            strategy: Tag for order identification

        Returns:
            Response dict with order_id
        """
        try:
            # Map action to Kite transaction type
            transaction_type = self.kite.TRANSACTION_TYPE_BUY if action.upper() == "BUY" else self.kite.TRANSACTION_TYPE_SELL

            # Map order type
            order_type_map = {
                "MARKET": self.kite.ORDER_TYPE_MARKET,
                "LIMIT": self.kite.ORDER_TYPE_LIMIT,
                "SL": self.kite.ORDER_TYPE_SL,
                "SL-M": self.kite.ORDER_TYPE_SLM
            }
            kite_order_type = order_type_map.get(order_type.upper(), self.kite.ORDER_TYPE_MARKET)

            # Map product
            product_map = {
                "NRML": self.kite.PRODUCT_NRML,
                "MIS": self.kite.PRODUCT_MIS,
                "CNC": self.kite.PRODUCT_CNC
            }
            kite_product = product_map.get(product.upper(), self.kite.PRODUCT_NRML)

            # Place order
            order_params = {
                "variety": self.kite.VARIETY_REGULAR,
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "product": kite_product,
                "order_type": kite_order_type,
                "tag": strategy[:20]  # Max 20 chars
            }

            if price > 0 and order_type.upper() in ["LIMIT", "SL"]:
                order_params["price"] = price

            order_id = self.kite.place_order(**order_params)

            logger.info(f"Order placed: {action} {quantity} {symbol} @ {order_type}, order_id={order_id}")

            return {
                "status": "success",
                "orderid": str(order_id),
                "message": f"Order {order_id} placed successfully"
            }

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def modify_order(self, order_id: str, new_price: float, new_quantity: int = None) -> Dict:
        """Modify an existing order"""
        try:
            params = {
                "variety": self.kite.VARIETY_REGULAR,
                "order_id": order_id,
                "price": new_price
            }
            if new_quantity:
                params["quantity"] = new_quantity

            self.kite.modify_order(**params)

            logger.info(f"Order {order_id} modified: price={new_price}")
            return {"status": "success", "message": "Order modified"}

        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            return {"status": "error", "message": str(e)}

    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order"""
        try:
            self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id
            )

            logger.info(f"Order {order_id} cancelled")
            return {"status": "success", "message": "Order cancelled"}

        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        Get order status

        Returns:
            Order dict with status, price, filled quantity, etc.
        """
        try:
            orders = self.kite.orders()
            for order in orders:
                if str(order.get("order_id")) == str(order_id):
                    # Map to OpenAlgo-compatible format
                    return {
                        "orderid": order.get("order_id"),
                        "status": order.get("status"),  # COMPLETE, OPEN, REJECTED, CANCELLED
                        "filledqty": order.get("filled_quantity", 0),
                        "price": order.get("average_price", 0),
                        "quantity": order.get("quantity"),
                        "tradingsymbol": order.get("tradingsymbol"),
                        "transaction_type": order.get("transaction_type"),
                        "exchange": order.get("exchange"),
                        "order_type": order.get("order_type"),
                        "status_message": order.get("status_message")
                    }
            return None

        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return None

    def get_orderbook(self) -> Dict:
        """Get all orders for the day"""
        try:
            orders = self.kite.orders()
            return {"status": "success", "data": orders}
        except Exception as e:
            logger.error(f"Failed to get orderbook: {e}")
            return {"status": "error", "data": [], "message": str(e)}

    # ==================== Position & Portfolio ====================

    def get_positions(self) -> Dict:
        """Get current positions"""
        try:
            positions = self.kite.positions()
            # Returns {"net": [...], "day": [...]}
            return {"status": "success", "data": positions.get("net", [])}
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {"status": "error", "data": [], "message": str(e)}

    def get_holdings(self) -> List[Dict]:
        """Get holdings (equity delivery)"""
        try:
            return self.kite.holdings()
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            return []

    def get_funds(self) -> Dict:
        """
        Get available margin/funds

        Returns:
            Funds dict with availablecash, margin, etc.
        """
        try:
            margins = self.kite.margins()
            # Kite returns {"equity": {...}, "commodity": {...}}

            equity = margins.get("equity", {})
            commodity = margins.get("commodity", {})

            # Map to OpenAlgo-compatible format
            return {
                "availablecash": equity.get("available", {}).get("cash", 0),
                "collateral": equity.get("available", {}).get("collateral", 0),
                "m2munrealized": equity.get("utilised", {}).get("m2m_unrealised", 0),
                "m2mrealized": equity.get("utilised", {}).get("m2m_realised", 0),
                "utiliseddebits": equity.get("utilised", {}).get("debits", 0),
                "utilisedspan": equity.get("utilised", {}).get("span", 0),
                "utilisedexposure": equity.get("utilised", {}).get("exposure", 0),
                "net": equity.get("net", 0),
                # Commodity segment
                "commodity_available": commodity.get("available", {}).get("cash", 0)
            }

        except Exception as e:
            logger.error(f"Failed to get funds: {e}")
            return {"availablecash": 0}

    # ==================== Market Data ====================

    def get_quote(self, symbol: str, exchange: str = "NFO") -> Dict:
        """
        Get quote for symbol

        Args:
            symbol: Trading symbol
            exchange: Exchange code

        Returns:
            Quote dict with ltp, bid, ask, volume, etc.
        """
        try:
            instrument_key = f"{exchange}:{symbol}"
            quotes = self.kite.quote([instrument_key])

            quote = quotes.get(instrument_key, {})

            return {
                "ltp": quote.get("last_price", 0),
                "bid": quote.get("depth", {}).get("buy", [{}])[0].get("price", 0),
                "ask": quote.get("depth", {}).get("sell", [{}])[0].get("price", 0),
                "open": quote.get("ohlc", {}).get("open", 0),
                "high": quote.get("ohlc", {}).get("high", 0),
                "low": quote.get("ohlc", {}).get("low", 0),
                "close": quote.get("ohlc", {}).get("close", 0),
                "volume": quote.get("volume", 0),
                "oi": quote.get("oi", 0),
                "instrument_token": quote.get("instrument_token")
            }

        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return {"ltp": 0}

    def get_ltp(self, instruments: List[str]) -> Dict:
        """
        Get only LTP for multiple instruments

        Args:
            instruments: List of "EXCHANGE:SYMBOL" strings

        Returns:
            Dict mapping instrument to LTP
        """
        try:
            return self.kite.ltp(instruments)
        except Exception as e:
            logger.error(f"Failed to get LTP: {e}")
            return {}

    # ==================== Instruments ====================

    def get_instruments(self, exchange: str = None) -> List[Dict]:
        """
        Get instrument list for symbol mapping

        Args:
            exchange: Optional exchange filter (NFO, MCX, etc.)

        Returns:
            List of instrument dicts
        """
        try:
            return self.kite.instruments(exchange)
        except Exception as e:
            logger.error(f"Failed to get instruments: {e}")
            return []

    def get_instrument_token(self, symbol: str, exchange: str = "NFO") -> Optional[int]:
        """
        Get instrument token for a symbol (needed for WebSocket)

        Args:
            symbol: Trading symbol
            exchange: Exchange code

        Returns:
            Instrument token or None
        """
        cache_key = f"{exchange}:{symbol}"

        if cache_key in self._instrument_cache:
            return self._instrument_cache[cache_key]

        try:
            instruments = self.get_instruments(exchange)
            for inst in instruments:
                if inst.get("tradingsymbol") == symbol:
                    token = inst.get("instrument_token")
                    self._instrument_cache[cache_key] = token
                    return token
            return None

        except Exception as e:
            logger.error(f"Failed to get instrument token: {e}")
            return None

    # ==================== Position Close (Convenience) ====================

    def close_position(
        self,
        symbol: str,
        quantity: int,
        product: str = "NRML",
        exchange: str = "NFO",
        current_action: str = "BUY"  # Current position direction
    ) -> Dict:
        """
        Close a position (convenience method)

        Args:
            symbol: Symbol to close
            quantity: Quantity to close
            product: Product type
            exchange: Exchange code
            current_action: Current position direction (BUY = long, SELL = short)

        Returns:
            Order response
        """
        # To close a long position, we sell; to close short, we buy
        close_action = "SELL" if current_action.upper() == "BUY" else "BUY"

        return self.place_order(
            symbol=symbol,
            action=close_action,
            quantity=quantity,
            order_type="MARKET",
            product=product,
            exchange=exchange,
            strategy="PositionClose"
        )
```

---

## Symbol Mapping

### TradingView to Zerodha Symbol Format

| Instrument | TradingView | Zerodha Format | Example |
|------------|-------------|----------------|---------|
| Bank Nifty Options | BANK_NIFTY | BANKNIFTY{YYMM}{DD}{STRIKE}{CE/PE} | BANKNIFTY2412552000CE |
| Bank Nifty Futures | BANK_NIFTY | BANKNIFTY{YY}{MMM}FUT | BANKNIFTY24DECFUT |
| Gold Mini Futures | GOLD_MINI | GOLDM{YY}{MMM}FUT | GOLDM25JANFUT |

### Symbol Mapping JSON

```json
{
  "BANK_NIFTY": {
    "exchange": "NFO",
    "underlying": "BANKNIFTY",
    "lot_size": 35,
    "tick_size": 0.05,
    "option_format": "BANKNIFTY{YYMMDD}{STRIKE}{CE|PE}",
    "futures_format": "BANKNIFTY{YY}{MMM}FUT",
    "expiry_day": "Wednesday",
    "weekly_expiry": true
  },
  "GOLD_MINI": {
    "exchange": "MCX",
    "underlying": "GOLDM",
    "lot_size": 100,
    "tick_size": 1.0,
    "futures_format": "GOLDM{YY}{MMM}FUT",
    "expiry_day": "5th of month",
    "monthly_expiry": true
  }
}
```

### Symbol Builder Function

```python
from datetime import datetime, timedelta

def build_banknifty_option_symbol(strike: int, option_type: str, expiry_date: datetime) -> str:
    """
    Build Bank Nifty option symbol

    Args:
        strike: Strike price (e.g., 52000)
        option_type: 'CE' or 'PE'
        expiry_date: Expiry date

    Returns:
        Trading symbol (e.g., BANKNIFTY2412552000CE)
    """
    # Format: BANKNIFTY{YYMMDD}{STRIKE}{CE/PE}
    date_str = expiry_date.strftime("%y%m%d")  # 241225
    return f"BANKNIFTY{date_str}{strike}{option_type}"


def build_banknifty_futures_symbol(expiry_month: datetime) -> str:
    """
    Build Bank Nifty futures symbol

    Args:
        expiry_month: Month of expiry

    Returns:
        Trading symbol (e.g., BANKNIFTY24DECFUT)
    """
    year = expiry_month.strftime("%y")  # 24
    month = expiry_month.strftime("%b").upper()  # DEC
    return f"BANKNIFTY{year}{month}FUT"


def build_goldmini_futures_symbol(expiry_month: datetime) -> str:
    """
    Build Gold Mini futures symbol

    Args:
        expiry_month: Month of expiry

    Returns:
        Trading symbol (e.g., GOLDM25JANFUT)
    """
    year = expiry_month.strftime("%y")  # 25
    month = expiry_month.strftime("%b").upper()  # JAN
    return f"GOLDM{year}{month}FUT"


def get_next_weekly_expiry(from_date: datetime = None) -> datetime:
    """
    Get next Bank Nifty weekly expiry (Wednesday)

    Args:
        from_date: Start date (default: today)

    Returns:
        Next Wednesday expiry date
    """
    if from_date is None:
        from_date = datetime.now()

    # Wednesday is weekday 2
    days_until_wednesday = (2 - from_date.weekday()) % 7
    if days_until_wednesday == 0 and from_date.hour >= 15:
        # If it's Wednesday after market close, get next week
        days_until_wednesday = 7

    return from_date + timedelta(days=days_until_wednesday)
```

---

## API Endpoints Reference

### Kite Connect API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/token` | POST | Generate access token |
| `/user/profile` | GET | Get user profile |
| `/user/margins` | GET | Get available margins |
| `/user/margins/{segment}` | GET | Get segment-specific margins |
| `/orders/regular` | POST | Place regular order |
| `/orders/regular/{order_id}` | PUT | Modify order |
| `/orders/regular/{order_id}` | DELETE | Cancel order |
| `/orders` | GET | Get all orders |
| `/orders/{order_id}` | GET | Get order history |
| `/trades` | GET | Get all trades |
| `/portfolio/positions` | GET | Get positions |
| `/portfolio/holdings` | GET | Get holdings |
| `/quote` | GET | Get full quote |
| `/quote/ltp` | GET | Get LTP only |
| `/quote/ohlc` | GET | Get OHLC |
| `/instruments` | GET | Get instrument list |
| `/instruments/{exchange}` | GET | Get exchange instruments |

### Response Structure

All Kite API responses follow this structure:

```json
{
  "status": "success",
  "data": { ... }
}
```

Or on error:

```json
{
  "status": "error",
  "message": "Error description",
  "error_type": "TokenException"
}
```

---

## WebSocket (KiteTicker)

### Setup KiteTicker for Real-time Data

```python
from kiteconnect import KiteTicker

class MarketDataStreamer:
    def __init__(self, api_key: str, access_token: str):
        self.ticker = KiteTicker(api_key, access_token)
        self._callbacks = []

        # Assign callbacks
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = self._on_connect
        self.ticker.on_close = self._on_close
        self.ticker.on_error = self._on_error
        self.ticker.on_reconnect = self._on_reconnect

    def _on_ticks(self, ws, ticks):
        """Called when tick data is received"""
        for tick in ticks:
            # Tick structure:
            # {
            #     "instrument_token": 12345,
            #     "last_price": 52000.50,
            #     "last_quantity": 35,
            #     "average_price": 52010.00,
            #     "volume": 123456,
            #     "buy_quantity": 10000,
            #     "sell_quantity": 8000,
            #     "ohlc": {"open": 52100, "high": 52200, "low": 51900, "close": 52050},
            #     "change": -0.5,
            #     "last_trade_time": datetime(...),
            #     "oi": 50000,  # Open interest
            #     "depth": {"buy": [...], "sell": [...]}  # Market depth
            # }
            for callback in self._callbacks:
                callback(tick)

    def _on_connect(self, ws, response):
        """Called on successful connection"""
        logger.info("KiteTicker connected")

    def _on_close(self, ws, code, reason):
        """Called when connection is closed"""
        logger.warning(f"KiteTicker closed: {code} - {reason}")

    def _on_error(self, ws, code, reason):
        """Called on error"""
        logger.error(f"KiteTicker error: {code} - {reason}")

    def _on_reconnect(self, ws, attempts_count):
        """Called on reconnection attempts"""
        logger.info(f"KiteTicker reconnecting: attempt {attempts_count}")

    def subscribe(self, instrument_tokens: list, mode: str = "ltp"):
        """
        Subscribe to instruments

        Args:
            instrument_tokens: List of instrument tokens
            mode: 'ltp', 'quote', or 'full'
        """
        self.ticker.subscribe(instrument_tokens)

        mode_map = {
            "ltp": self.ticker.MODE_LTP,
            "quote": self.ticker.MODE_QUOTE,
            "full": self.ticker.MODE_FULL
        }
        self.ticker.set_mode(mode_map.get(mode, self.ticker.MODE_LTP), instrument_tokens)

    def unsubscribe(self, instrument_tokens: list):
        """Unsubscribe from instruments"""
        self.ticker.unsubscribe(instrument_tokens)

    def add_callback(self, callback):
        """Add tick callback function"""
        self._callbacks.append(callback)

    def start(self, threaded: bool = True):
        """Start the ticker"""
        self.ticker.connect(threaded=threaded)

    def stop(self):
        """Stop the ticker"""
        self.ticker.close()
```

### Subscription Modes

| Mode | Data Included |
|------|---------------|
| `MODE_LTP` | Last price only |
| `MODE_QUOTE` | Last price, OHLC, volume, OI |
| `MODE_FULL` | All data including market depth |

---

## Rate Limits

| API Type | Rate Limit |
|----------|------------|
| Orders | 10 requests/second |
| Other APIs | 3 requests/second |
| WebSocket | 3000 instruments per connection |

### Handling Rate Limits

```python
import time
from functools import wraps

def rate_limited(max_per_second: float):
    """Decorator to rate limit API calls"""
    min_interval = 1.0 / max_per_second
    last_called = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait_time = min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator

# Usage
@rate_limited(3.0)  # 3 requests per second
def get_quote(self, symbol):
    return self.kite.quote([symbol])
```

---

## Error Handling

### Kite Exception Types

| Exception | Description | HTTP Code |
|-----------|-------------|-----------|
| `TokenException` | Invalid/expired token | 403 |
| `PermissionException` | Permission denied | 403 |
| `OrderException` | Order placement error | 400 |
| `InputException` | Invalid input | 400 |
| `DataException` | Data not available | 502 |
| `NetworkException` | Network error | 503 |
| `GeneralException` | Other errors | 500 |

### Error Handling Example

```python
from kiteconnect import exceptions as kite_exceptions

def safe_place_order(self, **params):
    try:
        return self.kite.place_order(**params)

    except kite_exceptions.TokenException as e:
        logger.error(f"Token error - need re-login: {e}")
        # Trigger re-authentication flow
        raise AuthenticationRequired()

    except kite_exceptions.OrderException as e:
        logger.error(f"Order error: {e}")
        return {"status": "error", "message": str(e)}

    except kite_exceptions.InputException as e:
        logger.error(f"Invalid input: {e}")
        return {"status": "error", "message": f"Invalid input: {e}"}

    except kite_exceptions.NetworkException as e:
        logger.error(f"Network error: {e}")
        # Implement retry logic
        return {"status": "error", "message": "Network error, please retry"}

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return {"status": "error", "message": str(e)}
```

---

## Daily Token Refresh

Access tokens expire at **3:30 AM IST** every day. You need to implement automatic re-authentication.

### Token Refresh Strategy

```python
from datetime import datetime, time
import threading
import schedule

class TokenManager:
    def __init__(self, zerodha_client: ZerodhaClient, db_manager):
        self.client = zerodha_client
        self.db = db_manager
        self._check_thread = None
        self._running = False

    def start_token_monitor(self):
        """Start background thread to monitor token expiry"""
        self._running = True
        self._check_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._check_thread.start()

    def stop_token_monitor(self):
        """Stop the token monitor"""
        self._running = False

    def _monitor_loop(self):
        """Check token validity periodically"""
        while self._running:
            now = datetime.now()

            # Check every 5 minutes
            if not self.client.is_session_valid():
                self._notify_session_expired()

            # Special check at 3:00 AM - warn about upcoming expiry
            if now.hour == 3 and now.minute == 0:
                self._notify_session_expiring_soon()

            time.sleep(300)  # Check every 5 minutes

    def _notify_session_expired(self):
        """Send notification that session has expired"""
        logger.warning("Zerodha session expired - re-authentication required")
        # Send notification via WebSocket to frontend
        # Or send email/SMS alert

    def _notify_session_expiring_soon(self):
        """Warn that session will expire soon"""
        logger.info("Zerodha session will expire at 3:30 AM")
```

### Frontend Token Status Display

```typescript
interface SessionStatus {
  valid: boolean;
  expiresAt: string;  // ISO timestamp
  minutesRemaining: number;
  userId: string;
}

// Show warning banner when < 30 minutes remaining
// Show critical alert when expired
// Provide "Re-authenticate" button that redirects to Kite login
```

---

## Checklist for Lovable AI

When sharing this document with Lovable AI, make sure to:

1. [ ] Share the Kite Connect API documentation URL
2. [ ] Share the pykiteconnect SDK GitHub URL
3. [ ] Provide your redirect URL for OAuth configuration
4. [ ] Share the symbol mapping JSON
5. [ ] Share the existing `openalgo_client.py` as a reference pattern
6. [ ] Share the database schema for session storage
7. [ ] Specify which features need WebSocket (real-time prices, notifications)

---

## Quick Start Commands

```bash
# Install Kite Connect SDK
pip install kiteconnect

# Test connection
python -c "
from kiteconnect import KiteConnect
kite = KiteConnect(api_key='your_api_key')
print(kite.login_url())
"
```
