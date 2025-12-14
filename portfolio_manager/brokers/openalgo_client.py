"""
OpenAlgo API Client for order execution and data retrieval

OpenAlgo API uses POST requests with apikey in the request body.
See: https://docs.openalgo.in/api-documentation/v1/
"""
import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class OpenAlgoClient:
    """Client for OpenAlgo REST API"""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize OpenAlgo client

        Args:
            base_url: OpenAlgo server URL (e.g., http://127.0.0.1:5000)
            api_key: API key from OpenAlgo settings
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
        logger.info(f"OpenAlgo client initialized: {self.base_url}")

    def place_order(self, symbol: str, action: str, quantity: int,
                    order_type: str = "MARKET", product: str = "NRML",
                    price: float = 0.0, exchange: str = "NFO",
                    strategy: str = "PortfolioManager") -> Dict:
        """
        Place order via OpenAlgo

        Args:
            symbol: Option symbol (e.g., BANKNIFTY25DEC2552000PE)
            action: BUY or SELL
            quantity: Number of units
            order_type: MARKET or LIMIT (maps to pricetype)
            product: NRML (normal) or MIS (intraday)
            price: Limit price (required for LIMIT orders)
            exchange: NFO, NSE, MCX, etc.
            strategy: Strategy identifier for tracking

        Returns:
            Response dict with status and orderid
        """
        url = f"{self.base_url}/api/v1/placeorder"
        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "product": product,
            "pricetype": order_type,
            "quantity": str(quantity),
            "price": str(price) if price > 0 else "0",
            "trigger_price": "0",
            "disclosed_quantity": "0"
        }

        logger.info(f"Placing order: {action} {quantity} {symbol}")

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('status') == 'success':
                logger.info(f"Order placed successfully: {result.get('orderid')}")
            else:
                logger.error(f"Order failed: {result}")

            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Order request failed: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error placing order: {e}")
            return {"status": "error", "message": str(e)}

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        Get order status by order ID

        Args:
            order_id: Order ID from place_order response

        Returns:
            Order dict with status, price, etc. or None if not found
        """
        url = f"{self.base_url}/api/v1/orderbook"
        try:
            payload = {"apikey": self.api_key}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            # Handle both formats: {"data": [...]} and {"data": {"orders": [...]}}
            data = result.get('data', [])
            if isinstance(data, dict):
                orders = data.get('orders', [])
            else:
                orders = data if isinstance(data, list) else []

            for order in orders:
                if isinstance(order, dict) and str(order.get('orderid')) == str(order_id):
                    # Normalize status field (OpenAlgo uses 'order_status')
                    status = order.get('order_status') or order.get('status')
                    logger.debug(f"Order {order_id} status: {status}")
                    return order

            logger.warning(f"Order {order_id} not found in orderbook")
            return None
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return None

    def get_positions(self) -> List[Dict]:
        """
        Get current open positions from OpenAlgo

        Returns:
            List of position dicts
        """
        url = f"{self.base_url}/api/v1/positionbook"
        try:
            payload = {"apikey": self.api_key}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            positions = result.get('data', [])
            logger.debug(f"Retrieved {len(positions)} positions")
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            # Return None to signal upstream that broker fetch failed (avoid false discrepancies)
            return None

    def get_funds(self) -> Dict:
        """
        Get available margin/funds

        Returns:
            Funds dict with availablecash, collateral, etc.
        """
        url = f"{self.base_url}/api/v1/funds"
        try:
            payload = {"apikey": self.api_key}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            funds = result.get('data', {})
            available = funds.get('availablecash', '0')
            logger.debug(f"Available cash: ₹{float(available):,.2f}")
            return funds
        except Exception as e:
            logger.error(f"Failed to get funds: {e}")
            return {}

    def get_quote(self, symbol: str, exchange: str = None) -> Dict:
        """
        Get live quote for symbol

        Args:
            symbol: Trading symbol or internal name (e.g., BANK_NIFTY, GOLD_MINI, or actual symbol)
            exchange: Exchange code (NFO, NSE, MCX, etc.) - auto-detected if not provided

        Returns:
            Quote dict with ltp, bid, ask, etc.
        """
        # Translate internal instrument names to OpenAlgo symbols
        # IMPORTANT: Use FUTURES price for divergence check (Pine Script runs on futures chart)
        actual_symbol = symbol
        actual_exchange = exchange or "NFO"

        if symbol == "BANK_NIFTY":
            # Bank Nifty futures: BANKNIFTY{DD}{MMM}{YY}FUT (e.g., BANKNIFTY30DEC25FUT)
            # Use current month expiry date
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_bank_nifty_expiry(date.today())
                # Format: BANKNIFTY{DD}{MMM}{YY}FUT
                actual_symbol = f"BANKNIFTY{expiry.strftime('%d%b%y').upper()}FUT"
                actual_exchange = "NFO"
            except Exception as e:
                logger.warning(f"Could not calculate BN futures expiry, using fallback: {e}")
                actual_symbol = "BANKNIFTY30DEC25FUT"  # Fallback for Dec 2025
                actual_exchange = "NFO"
        elif symbol == "NIFTY":
            # Similar logic for Nifty futures
            actual_symbol = "NIFTY"  # TODO: implement dynamic expiry
            actual_exchange = "NFO"
        elif symbol == "GOLD_MINI":
            # Gold Mini futures: GOLDM{DD}{MMM}{YY}FUT (e.g., GOLDM05JAN26FUT)
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("GOLD_MINI", date.today())
                # Format: GOLDM{DD}{MMM}{YY}FUT
                actual_symbol = f"GOLDM{expiry.strftime('%d%b%y').upper()}FUT"
                actual_exchange = "MCX"
            except Exception as e:
                logger.warning(f"Could not calculate Gold Mini expiry, using fallback: {e}")
                actual_symbol = "GOLDM05JAN26FUT"  # Fallback for Jan 2026
                actual_exchange = "MCX"

        url = f"{self.base_url}/api/v1/quotes"
        try:
            payload = {
                "apikey": self.api_key,
                "symbol": actual_symbol,
                "exchange": actual_exchange
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            quote = result.get('data', {})
            logger.debug(f"Quote for {actual_symbol}: LTP={quote.get('ltp')}")
            return quote
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol} ({actual_symbol}@{actual_exchange}): {e}")
            return {}

    def modify_order(self, order_id: str, new_price: float,
                     symbol: str = None, action: str = None, exchange: str = None,
                     quantity: int = None, product: str = None,
                     new_trigger_price: float = None) -> Dict:
        """
        Modify an existing order.

        OpenAlgo requires ALL order details to modify, not just the new price.

        Args:
            order_id: Order ID to modify
            new_price: New limit price
            symbol: Trading symbol (required by OpenAlgo)
            action: BUY or SELL (required by OpenAlgo)
            exchange: Exchange code NFO/MCX (required by OpenAlgo)
            quantity: Order quantity (required by OpenAlgo)
            product: Product type NRML/MIS (required by OpenAlgo)
            new_trigger_price: New trigger price for SL orders (optional)

        Returns:
            Response dict with status
        """
        url = f"{self.base_url}/api/v1/modifyorder"
        try:
            payload = {
                "apikey": self.api_key,
                "strategy": "Portfolio Manager",
                "orderid": str(order_id),
                "symbol": symbol or "",
                "action": action or "BUY",
                "exchange": exchange or "NFO",
                "product": product or "NRML",
                "pricetype": "LIMIT",
                "quantity": str(quantity) if quantity else "0",
                "price": str(new_price),
                "trigger_price": str(new_trigger_price) if new_trigger_price else "0",
                "disclosed_quantity": "0"
            }

            # Log at INFO level for debugging modify issues
            logger.info(f"Modify order request: orderid={order_id}, symbol={symbol}, action={action}, price={new_price}, qty={quantity}")

            response = self.session.post(url, json=payload, timeout=10)

            # Log response even if it fails
            if response.status_code != 200:
                logger.error(
                    f"Modify order {order_id} failed: HTTP {response.status_code}, "
                    f"Response: {response.text}"
                )

            response.raise_for_status()
            result = response.json()
            logger.info(f"Order {order_id} modified to price {new_price}: {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return {"status": "error", "message": str(e)}

    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel an open order

        Args:
            order_id: Order ID to cancel

        Returns:
            Response dict with status
        """
        url = f"{self.base_url}/api/v1/cancelorder"
        try:
            payload = {
                "apikey": self.api_key,
                "orderid": str(order_id)
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Order {order_id} cancellation: {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return {"status": "error", "message": str(e)}

    def close_position(self, symbol: str, quantity: int, product: str = "NRML",
                       exchange: str = "NFO") -> Dict:
        """
        Close position (convenience method)

        Args:
            symbol: Symbol to close
            quantity: Quantity to close
            product: Product type (NRML, MIS)
            exchange: Exchange code

        Returns:
            Response dict
        """
        url = f"{self.base_url}/api/v1/closeposition"
        payload = {
            "apikey": self.api_key,
            "symbol": symbol,
            "exchange": exchange,
            "product": product
        }

        logger.info(f"Closing position: {symbol} qty={quantity}")

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return {"status": "error", "message": str(e)}
