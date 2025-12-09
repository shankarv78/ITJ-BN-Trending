"""
Mock Broker Simulator for testing signal validation and execution strategies

Simulates broker behavior with configurable market scenarios for comprehensive testing
without requiring paper trading accounts.
"""
import random
import uuid
from datetime import datetime
from typing import Dict, Optional
from enum import Enum


class MarketScenario(Enum):
    """Market scenarios for simulation"""
    NORMAL = "normal"
    VOLATILE = "volatile"
    SURGE = "surge"
    PULLBACK = "pullback"
    GAP = "gap"


class MockBrokerSimulator:
    """
    Simulates broker behavior for testing signal validation.

    Configurable scenarios: normal, volatile, fast market, gaps.
    Provides realistic quote generation and order fill simulation.
    """

    def __init__(
        self,
        scenario: str = "normal",
        base_price: float = 50000.0,
        bid_ask_spread_pct: float = 0.002,  # 0.2% default (realistic for Bank Nifty)
        partial_fill_probability: float = 0.1  # 10% chance of partial fill when order would fill
    ):
        """
        Initialize mock broker simulator

        Args:
            scenario: Market scenario (normal, volatile, surge, pullback, gap)
            base_price: Base price for quote generation
            bid_ask_spread_pct: Bid/ask spread percentage (default: 0.2% for Bank Nifty)
            partial_fill_probability: Probability of partial fill when order would fill (default: 10%)
        """
        self.scenario = MarketScenario(scenario) if isinstance(scenario, str) else scenario
        self.base_price = base_price
        self.volatility = 0.001  # 0.1% default volatility
        self.bid_ask_spread = bid_ask_spread_pct
        self.partial_fill_probability = partial_fill_probability
        self._random_seed = None

        # Track placed orders
        self.orders: Dict[str, Dict] = {}

        # Default available funds (1 crore for sufficient margin)
        self.available_funds = 10000000.0

    def get_funds(self) -> Dict:
        """
        Simulate broker funds/margin query.

        Returns:
            Dictionary with available cash
        """
        return {
            'availablecash': self.available_funds,
            'collateral': self.available_funds * 0.8,
            'total': self.available_funds
        }

    def get_quote(self, instrument: str) -> Dict:
        """
        Simulate broker quote with configurable behavior.

        Args:
            instrument: Trading symbol (e.g., "BANKNIFTY-I")

        Returns:
            Dictionary with ltp, bid, ask, timestamp
        """
        if self.scenario == MarketScenario.NORMAL:
            # Small random divergence (-0.1% to +0.1%)
            divergence = random.uniform(-0.001, 0.001)
        elif self.scenario == MarketScenario.VOLATILE:
            # Larger swings (-1% to +1%)
            divergence = random.uniform(-0.01, 0.01)
        elif self.scenario == MarketScenario.SURGE:
            # Market surged ahead (+0.5% to +2%)
            divergence = random.uniform(0.005, 0.02)
        elif self.scenario == MarketScenario.PULLBACK:
            # Market pulled back (-0.5% to -1.5%)
            divergence = random.uniform(-0.015, -0.005)
        elif self.scenario == MarketScenario.GAP:
            # Price gap (+1.5% to +3%)
            divergence = random.uniform(0.015, 0.03)
        else:
            divergence = 0.0

        simulated_price = self.base_price * (1 + divergence)

        # Ensure price is positive
        simulated_price = max(simulated_price, 1.0)

        return {
            'ltp': round(simulated_price, 2),
            'bid': round(simulated_price * (1 - self.bid_ask_spread/2), 2),
            'ask': round(simulated_price * (1 + self.bid_ask_spread/2), 2),
            'timestamp': datetime.now().isoformat()
        }

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
        exchange: str = "NFO",
        **kwargs
    ) -> Dict:
        """
        Standard broker interface for order placement.
        Wraps place_limit_order for compatibility with OpenAlgo client interface.

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            quantity: Number of units (converted to lots based on instrument)
            order_type: MARKET or LIMIT
            price: Order price (for LIMIT orders)
            exchange: Exchange (NFO, MCX)
            **kwargs: Additional parameters (product, strategy, etc.)

        Returns:
            Order response dictionary
        """
        # Determine lot size based on instrument/exchange
        if exchange == "MCX" or "GOLD" in symbol.upper():
            lot_size = 10  # Gold Mini
        else:
            lot_size = 35  # Bank Nifty

        lots = max(1, quantity // lot_size)

        # For MARKET orders, use current quote price
        if order_type == "MARKET" or price <= 0:
            quote = self.get_quote(symbol)
            price = quote['ask'] if action == "BUY" else quote['bid']

        # Delegate to place_limit_order
        result = self.place_limit_order(symbol, lots, price, action)
        return result

    def place_limit_order(
        self,
        instrument: str,
        lots: int,
        price: float,
        action: str = "BUY"
    ) -> Dict:
        """
        Simulate limit order placement with fill probability.

        Args:
            instrument: Trading symbol
            lots: Number of lots
            price: Limit price
            action: BUY or SELL

        Returns:
            Order response dictionary
        """
        order_id = str(uuid.uuid4())

        # Fill probability based on scenario
        fill_prob = {
            MarketScenario.NORMAL: 0.95,
            MarketScenario.VOLATILE: 0.70,
            MarketScenario.SURGE: 0.30,
            MarketScenario.PULLBACK: 0.90,
            MarketScenario.GAP: 0.10
        }.get(self.scenario, 0.80)

        # Get current quote to determine if limit price is favorable
        quote = self.get_quote(instrument)
        current_ltp = quote['ltp']

        # For BUY: fill if limit >= ask (favorable)
        # For SELL: fill if limit <= bid (favorable)
        if action == "BUY":
            favorable = price >= quote['ask']
        else:  # SELL
            favorable = price <= quote['bid']

        # Adjust fill probability based on favorability
        if favorable:
            fill_prob = min(fill_prob * 1.2, 0.99)  # Higher chance if favorable
        else:
            fill_prob = fill_prob * 0.5  # Lower chance if unfavorable

        if random.random() < fill_prob:
            fill_price = price if favorable else current_ltp

            # Decide: full fill or partial fill?
            if random.random() < self.partial_fill_probability:
                # Partial fill: fill 30-70% of lots
                fill_percentage = random.uniform(0.3, 0.7)
                filled_lots = int(lots * fill_percentage)
                remaining_lots = lots - filled_lots

                order_status = {
                    'status': 'success',
                    'orderid': order_id,
                    'fill_status': 'PARTIAL',
                    'fill_price': round(fill_price, 2),
                    'avg_fill_price': round(fill_price, 2),
                    'lots': lots,
                    'filled_lots': filled_lots,
                    'remaining_lots': remaining_lots
                }
            else:
                # Full fill
                order_status = {
                    'status': 'success',
                    'orderid': order_id,
                    'fill_status': 'COMPLETE',
                    'fill_price': round(fill_price, 2),
                    'lots': lots,
                    'filled_lots': lots,
                    'remaining_lots': 0
                }
        else:
            order_status = {
                'status': 'success',
                'orderid': order_id,
                'fill_status': 'PENDING',
                'lots': lots,
                'filled_lots': 0,
                'remaining_lots': lots
            }

        # Store order for status checking
        self.orders[order_id] = {
            **order_status,
            'instrument': instrument,
            'action': action,
            'limit_price': price,
            'placed_at': datetime.now()
        }

        return order_status

    def get_order_status(self, order_id: str) -> Dict:
        """
        Get status of placed order.

        Args:
            order_id: Order ID

        Returns:
            Order status dictionary
        """
        if order_id not in self.orders:
            return {
                'status': 'error',
                'error': 'Order not found'
            }

        order = self.orders[order_id]

        # If cancelled, return cancelled status
        if order['fill_status'] == 'CANCELLED':
            return {
                'status': 'CANCELLED',
                'fill_status': 'CANCELLED',
                'lots': order['lots'],
                'filled_lots': order.get('filled_lots', 0),
                'remaining_lots': order.get('remaining_lots', order['lots'])
            }

        # If already filled or partially filled, return status
        if order['fill_status'] in ['COMPLETE', 'PARTIAL']:
            return {
                'status': 'COMPLETE' if order['fill_status'] == 'COMPLETE' else 'PARTIAL',
                'fill_status': order['fill_status'],
                'fill_price': order.get('fill_price') or order.get('avg_fill_price') or order['limit_price'],
                'avg_fill_price': order.get('avg_fill_price') or order.get('fill_price') or order['limit_price'],
                'lots': order['lots'],
                'filled_lots': order.get('filled_lots', 0),
                'remaining_lots': order.get('remaining_lots', 0)
            }

        # If pending, check if it should fill now (simulate time passing)
        # For testing, we can manually set fill status or use probability
        return {
            'status': 'PENDING',
            'fill_status': 'PENDING',
            'lots': order['lots'],
            'filled_lots': order.get('filled_lots', 0),
            'remaining_lots': order.get('remaining_lots', order['lots'])
        }

    def modify_order(self, order_id: str, new_price: float) -> Dict:
        """
        Modify existing order price.

        Args:
            order_id: Order ID
            new_price: New limit price

        Returns:
            Modification response
        """
        if order_id not in self.orders:
            return {
                'status': 'error',
                'error': 'Order not found'
            }

        order = self.orders[order_id]

        # Update limit price
        order['limit_price'] = new_price

        # Re-evaluate fill probability with new price
        quote = self.get_quote(order['instrument'])
        current_ltp = quote['ltp']

        if order['action'] == "BUY":
            favorable = new_price >= quote['ask']
        else:
            favorable = new_price <= quote['bid']

        fill_prob = 0.7 if favorable else 0.3

        if random.random() < fill_prob:
            fill_price = new_price if favorable else current_ltp
            order['fill_status'] = 'COMPLETE'
            order['fill_price'] = round(fill_price, 2)
            order['filled_lots'] = order['lots']
            order['remaining_lots'] = 0

            return {
                'status': 'success',
                'fill_status': 'COMPLETE',
                'fill_price': round(fill_price, 2)
            }

        return {
            'status': 'success',
            'fill_status': 'PENDING'
        }

    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel an order.

        Args:
            order_id: Order ID

        Returns:
            Cancellation response
        """
        if order_id not in self.orders:
            return {
                'status': 'error',
                'error': 'Order not found'
            }

        order = self.orders[order_id]
        order['fill_status'] = 'CANCELLED'

        return {
            'status': 'success',
            'fill_status': 'CANCELLED'
        }

    def set_scenario(self, scenario: str):
        """
        Switch market scenario during test.

        Args:
            scenario: New scenario name
        """
        self.scenario = MarketScenario(scenario) if isinstance(scenario, str) else scenario

    def set_base_price(self, base_price: float):
        """
        Update base price for quote generation.

        Args:
            base_price: New base price
        """
        self.base_price = base_price

    def set_seed(self, seed: int):
        """
        Set random seed for deterministic testing.

        Args:
            seed: Random seed value
        """
        self._random_seed = seed
        random.seed(seed)
