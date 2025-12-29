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

    def check_connection(self) -> Dict:
        """
        Check if broker is reachable and authenticated.

        Uses the funds endpoint as a lightweight connectivity test.
        Also detects if OpenAlgo is in 'analyze' mode (not connected to real broker).

        Returns:
            Dict with 'connected' (bool), 'status' (str), and optional 'error' (str)
        """
        try:
            # Make direct API call to get full response including 'mode' field
            url = f"{self.base_url}/api/v1/funds"
            payload = {"apikey": self.api_key}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            # Check if OpenAlgo is in analyze mode (not connected to real broker)
            mode = result.get('mode')
            if mode == 'analyze':
                return {
                    'connected': False,
                    'status': 'analyzer_mode',
                    'error': 'OpenAlgo is in ANALYZER MODE - not connected to real broker'
                }

            funds = result.get('data', {})
            if funds and 'availablecash' in funds:
                return {
                    'connected': True,
                    'status': 'connected',
                    'available_cash': float(funds.get('availablecash', 0))
                }
            else:
                # API returned but no valid data - possibly auth issue
                return {
                    'connected': False,
                    'status': 'auth_error',
                    'error': 'Invalid response from broker API'
                }
        except requests.exceptions.ConnectionError as e:
            return {
                'connected': False,
                'status': 'unreachable',
                'error': f'Cannot connect to broker: {e}'
            }
        except requests.exceptions.Timeout:
            return {
                'connected': False,
                'status': 'timeout',
                'error': 'Broker connection timed out'
            }
        except Exception as e:
            return {
                'connected': False,
                'status': 'error',
                'error': str(e)
            }

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

        logger.info(f"Placing order: {action} {quantity} {symbol} @ {exchange}")
        logger.debug(f"Order payload: {payload}")

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('status') == 'success':
                logger.info(f"Order placed successfully: {result.get('orderid')}")
            else:
                logger.error(f"Order failed: {result}")

            return result
        except requests.exceptions.HTTPError as e:
            # Log full response body for debugging
            try:
                error_body = e.response.text if e.response else "No response body"
                logger.error(f"Order request failed [{e.response.status_code}]: {error_body}")
            except Exception:
                logger.error(f"Order request failed: {e}")
            return {"status": "error", "message": str(e)}
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

    def get_orderbook(self) -> List[Dict]:
        """
        Get full orderbook (all orders for today)

        Returns:
            List of order dicts or empty list on failure
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

            logger.debug(f"Retrieved {len(orders)} orders from orderbook")
            return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.error(f"Failed to get orderbook: {e}")
            return []

    def find_recent_filled_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        max_age_seconds: int = 120
    ) -> Optional[Dict]:
        """
        Find a recently filled order matching criteria.

        This is used to detect orders that were placed but the response was lost
        (e.g., due to HTTP timeout). When order placement times out, the order
        might have actually been executed at the broker.

        Args:
            symbol: Trading symbol to match (e.g., SILVERM27FEB26FUT)
            action: BUY or SELL
            quantity: Expected quantity
            max_age_seconds: Only consider orders placed within this window

        Returns:
            Order dict if found and filled, None otherwise
        """
        from datetime import datetime, timedelta

        orders = self.get_orderbook()
        if not orders:
            return None

        now = datetime.now()
        cutoff = now - timedelta(seconds=max_age_seconds)

        for order in orders:
            if not isinstance(order, dict):
                continue

            # Check symbol and action match
            order_symbol = order.get('symbol', '')
            order_action = order.get('action', '').upper()
            order_qty = int(order.get('quantity', 0) or order.get('filledshares', 0) or 0)

            if order_symbol != symbol or order_action != action.upper():
                continue

            # Check quantity matches (for partial fills, check filledshares)
            filled_qty = int(order.get('filledshares', 0) or 0)
            if order_qty != quantity and filled_qty != quantity:
                continue

            # Check if order is filled/complete
            status = (order.get('order_status') or order.get('status') or '').upper()
            if status not in ['COMPLETE', 'FILLED']:
                continue

            # Check order timestamp if available
            timestamp_str = order.get('timestamp') or order.get('order_timestamp') or ''
            if timestamp_str:
                try:
                    # Parse various timestamp formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            order_time = datetime.strptime(timestamp_str[:19], fmt)
                            if order_time < cutoff:
                                continue  # Order too old
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass  # Can't parse timestamp, include order anyway

            # Found a matching filled order
            logger.info(
                f"[RECOVERY] Found filled order matching criteria: "
                f"{order_symbol} {order_action} {filled_qty} lots, "
                f"order_id={order.get('orderid')}"
            )
            return order

        return None

    def get_trade_fill_price(self, order_id: str) -> Optional[float]:
        """
        Get actual fill price from tradebook for a completed order.

        The orderbook may not have accurate fill prices - tradebook has actual execution prices.

        Args:
            order_id: Order ID to look up

        Returns:
            Average fill price if found, None otherwise
        """
        url = f"{self.base_url}/api/v1/tradebook"
        try:
            payload = {"apikey": self.api_key}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            # Handle response format
            data = result.get('data', [])
            if isinstance(data, dict):
                trades = data.get('trades', [])
            else:
                trades = data if isinstance(data, list) else []

            # Find trades for this order and calculate average price
            order_trades = []
            for trade in trades:
                if isinstance(trade, dict) and str(trade.get('orderid')) == str(order_id):
                    order_trades.append(trade)

            if not order_trades:
                logger.debug(f"No trades found for order {order_id}")
                return None

            # Calculate weighted average price
            total_qty = 0
            total_value = 0.0
            for trade in order_trades:
                qty = float(trade.get('quantity', 0) or trade.get('filledqty', 0) or 0)
                price = float(trade.get('averageprice', 0) or trade.get('price', 0) or trade.get('tradeprice', 0) or 0)
                if qty > 0 and price > 0:
                    total_qty += qty
                    total_value += qty * price

            if total_qty > 0:
                avg_price = total_value / total_qty
                logger.info(f"Tradebook fill price for {order_id}: ₹{avg_price:.2f} ({len(order_trades)} trades, {total_qty} qty)")
                return avg_price

            return None
        except Exception as e:
            logger.warning(f"Failed to get tradebook fill price for {order_id}: {e}")
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
        elif symbol == "COPPER":
            # Copper futures: COPPER{DD}{MMM}{YY}FUT (e.g., COPPER31DEC25FUT)
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("COPPER", date.today())
                # Format: COPPER{DD}{MMM}{YY}FUT
                actual_symbol = f"COPPER{expiry.strftime('%d%b%y').upper()}FUT"
                actual_exchange = "MCX"
            except Exception as e:
                logger.warning(f"Could not calculate Copper expiry, using fallback: {e}")
                actual_symbol = "COPPER31DEC25FUT"  # Fallback for Dec 2025
                actual_exchange = "MCX"
        elif symbol == "SILVER_MINI":
            # Silver Mini futures: SILVERM{DD}{MMM}{YY}FUT (e.g., SILVERM27FEB26FUT)
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("SILVER_MINI", date.today())
                # Format: SILVERM{DD}{MMM}{YY}FUT
                actual_symbol = f"SILVERM{expiry.strftime('%d%b%y').upper()}FUT"
                actual_exchange = "MCX"
            except Exception as e:
                logger.warning(f"Could not calculate Silver Mini expiry, using fallback: {e}")
                actual_symbol = "SILVERM27FEB26FUT"  # Fallback for Feb 2026
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
