"""
Broker Factory

Creates appropriate broker client based on configuration.
Supports execution_mode: 'live' (real orders) or 'analyzer' (dry-run with logging)
"""
import logging
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)


class AnalyzerBrokerWrapper:
    """
    Wrapper that intercepts order placement calls and logs them instead of executing.
    
    This enables true dry-run testing where:
    - Real broker connectivity is verified (get_funds, get_quote work)
    - Order placement is simulated with detailed logging
    - Full pipeline is exercised without real money risk
    """
    
    def __init__(self, real_broker, broker_name: str = "openalgo"):
        """
        Args:
            real_broker: The actual broker client (OpenAlgoClient)
            broker_name: Name for logging purposes
        """
        self.real_broker = real_broker
        self.broker_name = broker_name
        self.simulated_orders = []  # Track what would have been placed
        self._order_counter = 0
        logger.warning("=" * 60)
        logger.warning("⚠️  ANALYZER MODE ACTIVE - NO REAL ORDERS WILL BE PLACED")
        logger.warning("=" * 60)
    
    def place_order(self, symbol: str, action: str, quantity: int,
                    order_type: str = "MARKET", product: str = "NRML",
                    price: float = 0.0, exchange: str = "NFO",
                    strategy: str = "PortfolioManager") -> Dict:
        """
        Simulate order placement - logs but doesn't execute
        """
        self._order_counter += 1
        simulated_order_id = f"ANALYZER_{self._order_counter}_{uuid.uuid4().hex[:8]}"
        
        order_details = {
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'order_type': order_type,
            'product': product,
            'price': price,
            'exchange': exchange,
            'strategy': strategy,
            'simulated_order_id': simulated_order_id
        }
        
        self.simulated_orders.append(order_details)
        
        # Log prominently what WOULD have been placed
        logger.warning("=" * 60)
        logger.warning(f"🔔 ANALYZER: ORDER WOULD BE PLACED (NOT EXECUTED)")
        logger.warning(f"   Symbol:   {symbol}")
        logger.warning(f"   Action:   {action}")
        logger.warning(f"   Quantity: {quantity}")
        logger.warning(f"   Type:     {order_type}")
        logger.warning(f"   Price:    {price}")
        logger.warning(f"   Exchange: {exchange}")
        logger.warning(f"   Order ID: {simulated_order_id}")
        logger.warning("=" * 60)
        
        # Return success response as if order was placed
        return {
            'status': 'success',
            'orderid': simulated_order_id,
            'message': 'ANALYZER_MODE: Order simulated, not executed'
        }
    
    def get_order_status(self, order_id: str) -> Dict:
        """
        Return simulated order status for analyzer orders
        """
        if order_id.startswith('ANALYZER_'):
            # Find the simulated order to get its price and quantity
            order_price = 52000.0  # Default
            order_qty = 1
            for order in self.simulated_orders:
                if order.get('simulated_order_id') == order_id:
                    order_price = float(order.get('price', 52000.0))
                    order_qty = int(order.get('quantity', 1))
                    break
            
            logger.info(f"[ANALYZER] Simulated order status for {order_id}: COMPLETE @ ₹{order_price:,.2f}")
            return {
                'status': 'COMPLETE',
                'filledqty': order_qty,  # Return int, not string
                'price': order_price,    # Return float, not string
                'orderid': order_id
            }
        # For real order IDs, pass through to real broker
        return self.real_broker.get_order_status(order_id)
    
    def modify_order(self, order_id: str, new_price: float) -> Dict:
        """Simulate order modification"""
        if order_id.startswith('ANALYZER_'):
            logger.warning(f"[ANALYZER] Would modify order {order_id} to price {new_price}")
            return {'status': 'success', 'message': 'ANALYZER_MODE: Modification simulated'}
        return self.real_broker.modify_order(order_id, new_price)
    
    def cancel_order(self, order_id: str) -> Dict:
        """Simulate order cancellation"""
        if order_id.startswith('ANALYZER_'):
            logger.warning(f"[ANALYZER] Would cancel order {order_id}")
            return {'status': 'success', 'message': 'ANALYZER_MODE: Cancellation simulated'}
        return self.real_broker.cancel_order(order_id)
    
    # Pass-through methods that use real broker (read-only operations)
    def get_funds(self) -> Dict:
        """Get real account funds from broker"""
        logger.info("[ANALYZER] Fetching real account funds from broker")
        return self.real_broker.get_funds()
    
    def get_quote(self, symbol: str, exchange: str = "NFO") -> Dict:
        """Get real market quote from broker"""
        return self.real_broker.get_quote(symbol, exchange)
    
    def get_positions(self) -> Dict:
        """Get real positions from broker"""
        return self.real_broker.get_positions()
    
    def get_orderbook(self) -> Dict:
        """Get real order book from broker"""
        return self.real_broker.get_orderbook()
    
    def get_simulated_orders(self) -> list:
        """Return list of all simulated orders for review"""
        return self.simulated_orders.copy()
    
    def get_simulated_orders_summary(self) -> str:
        """Get a formatted summary of simulated orders"""
        if not self.simulated_orders:
            return "No orders simulated in this session"
        
        lines = [f"📋 ANALYZER SESSION SUMMARY: {len(self.simulated_orders)} orders simulated"]
        lines.append("-" * 50)
        for i, order in enumerate(self.simulated_orders, 1):
            lines.append(f"{i}. {order['action']} {order['quantity']} {order['symbol']} @ {order['order_type']}")
        return "\n".join(lines)


def create_broker_client(broker_type: str, config: Dict[str, Any]):
    """
    Create broker client based on type and execution mode
    
    Args:
        broker_type: Type of broker ('openalgo', 'mock')
        config: Broker configuration dictionary
            - execution_mode: 'live' (default) or 'analyzer' (dry-run)
        
    Returns:
        Broker client instance (possibly wrapped in AnalyzerBrokerWrapper)
        
    Raises:
        ValueError: If broker_type is unknown
    """
    execution_mode = config.get('execution_mode', 'live').lower()
    
    if broker_type.lower() == 'openalgo':
        from brokers.openalgo_client import OpenAlgoClient
        
        base_url = config.get('openalgo_url', 'http://127.0.0.1:5000')
        api_key = config.get('openalgo_api_key')
        
        if not api_key:
            raise ValueError("OpenAlgo API key is required")
        
        logger.info(f"Creating OpenAlgo client: {base_url}")
        real_broker = OpenAlgoClient(base_url, api_key)
        
        # Wrap in analyzer if not in live mode
        if execution_mode == 'analyzer':
            logger.info("🔬 Execution mode: ANALYZER (dry-run)")
            return AnalyzerBrokerWrapper(real_broker, broker_name="openalgo")
        else:
            logger.info("🚀 Execution mode: LIVE (real orders)")
            return real_broker
    
    elif broker_type.lower() == 'mock':
        from tests.mocks.mock_broker import MockBrokerSimulator
        
        logger.info("Creating MockBrokerSimulator (always simulated)")
        return MockBrokerSimulator()
    
    else:
        raise ValueError(f"Unknown broker type: {broker_type}")
