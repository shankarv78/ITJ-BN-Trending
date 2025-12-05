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

            orders = result.get('data', [])
            for order in orders:
                if str(order.get('orderid')) == str(order_id):
                    logger.debug(f"Order {order_id} status: {order.get('status')}")
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
            return []
    
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

    def get_quote(self, symbol: str, exchange: str = "NFO") -> Dict:
        """
        Get live quote for symbol

        Args:
            symbol: Trading symbol (e.g., BANKNIFTY25DEC2552000CE)
            exchange: Exchange code (NFO, NSE, MCX, etc.)

        Returns:
            Quote dict with ltp, bid, ask, etc.
        """
        url = f"{self.base_url}/api/v1/quotes"
        try:
            payload = {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": exchange
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            quote = result.get('data', {})
            logger.debug(f"Quote for {symbol}: LTP={quote.get('ltp')}")
            return quote
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return {}
    
    def modify_order(self, order_id: str, new_price: float,
                     new_quantity: int = None, new_trigger_price: float = None) -> Dict:
        """
        Modify an existing order

        Args:
            order_id: Order ID to modify
            new_price: New limit price
            new_quantity: New quantity (optional)
            new_trigger_price: New trigger price (optional)

        Returns:
            Response dict with status
        """
        url = f"{self.base_url}/api/v1/modifyorder"
        try:
            payload = {
                "apikey": self.api_key,
                "orderid": str(order_id),
                "newprice": str(new_price)
            }
            if new_quantity is not None:
                payload["newquantity"] = str(new_quantity)
            if new_trigger_price is not None:
                payload["newtrigger_price"] = str(new_trigger_price)

            response = self.session.post(url, json=payload, timeout=10)
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


