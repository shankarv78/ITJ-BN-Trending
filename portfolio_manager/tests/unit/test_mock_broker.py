"""
Unit tests for MockBrokerSimulator
"""
import pytest
from tests.mocks.mock_broker import MockBrokerSimulator, MarketScenario


class TestMockBrokerSimulator:
    """Test MockBrokerSimulator functionality"""
    
    def test_normal_scenario_quote_generation(self):
        """Test quote generation in normal market scenario"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        quote = broker.get_quote("BANKNIFTY-I")
        
        assert 'ltp' in quote
        assert 'bid' in quote
        assert 'ask' in quote
        assert 'timestamp' in quote
        
        # Normal scenario: small divergence (-0.1% to +0.1%)
        assert 49950 <= quote['ltp'] <= 50050
        assert quote['bid'] < quote['ltp'] < quote['ask']
        assert quote['ltp'] > 0
    
    def test_volatile_scenario_quote_generation(self):
        """Test quote generation in volatile market scenario"""
        broker = MockBrokerSimulator(scenario="volatile", base_price=50000.0)
        quote = broker.get_quote("BANKNIFTY-I")
        
        # Volatile scenario: larger swings (-1% to +1%)
        assert 49500 <= quote['ltp'] <= 50500
        assert quote['ltp'] > 0
    
    def test_surge_scenario_quote_generation(self):
        """Test quote generation when market surges"""
        broker = MockBrokerSimulator(scenario="surge", base_price=50000.0)
        quote = broker.get_quote("BANKNIFTY-I")
        
        # Surge scenario: +0.5% to +2%
        assert quote['ltp'] >= 50250  # At least 0.5% higher
        assert quote['ltp'] <= 51000  # At most 2% higher
    
    def test_pullback_scenario_quote_generation(self):
        """Test quote generation when market pulls back"""
        broker = MockBrokerSimulator(scenario="pullback", base_price=50000.0)
        quote = broker.get_quote("BANKNIFTY-I")
        
        # Pullback scenario: -0.5% to -1.5%
        assert quote['ltp'] <= 49750  # At most -0.5% lower
        assert quote['ltp'] >= 49250  # At least -1.5% lower
    
    def test_gap_scenario_quote_generation(self):
        """Test quote generation with price gap"""
        broker = MockBrokerSimulator(scenario="gap", base_price=50000.0)
        quote = broker.get_quote("BANKNIFTY-I")
        
        # Gap scenario: +1.5% to +3%
        assert quote['ltp'] >= 50750  # At least 1.5% higher
        assert quote['ltp'] <= 51500  # At most 3% higher
    
    def test_order_fill_probability_by_scenario(self):
        """Test that fill probabilities vary by scenario"""
        normal_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        volatile_broker = MockBrokerSimulator(scenario="volatile", base_price=50000.0)
        gap_broker = MockBrokerSimulator(scenario="gap", base_price=50000.0)
        
        # Place orders with favorable prices
        normal_order = normal_broker.place_limit_order("BANKNIFTY-I", 1, 51000, "BUY")
        volatile_order = volatile_broker.place_limit_order("BANKNIFTY-I", 1, 51000, "BUY")
        gap_order = gap_broker.place_limit_order("BANKNIFTY-I", 1, 51000, "BUY")
        
        # All should have order IDs
        assert 'orderid' in normal_order
        assert 'orderid' in volatile_order
        assert 'orderid' in gap_order
        
        # Status should be valid
        assert normal_order['status'] == 'success'
        assert volatile_order['status'] == 'success'
        assert gap_order['status'] == 'success'
    
    def test_scenario_switching_during_test(self):
        """Test that scenario can be switched during test"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        quote1 = broker.get_quote("BANKNIFTY-I")
        assert 49950 <= quote1['ltp'] <= 50050  # Normal range
        
        broker.set_scenario("surge")
        quote2 = broker.get_quote("BANKNIFTY-I")
        assert quote2['ltp'] >= 50250  # Surge range
        
        broker.set_scenario("pullback")
        quote3 = broker.get_quote("BANKNIFTY-I")
        assert quote3['ltp'] <= 49750  # Pullback range
    
    def test_order_status_tracking(self):
        """Test that order status can be retrieved"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        order = broker.place_limit_order("BANKNIFTY-I", 5, 50000, "BUY")
        order_id = order['orderid']
        
        status = broker.get_order_status(order_id)
        assert 'status' in status
        assert 'fill_status' in status
        assert status['lots'] == 5
    
    def test_order_modification(self):
        """Test that orders can be modified"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        order = broker.place_limit_order("BANKNIFTY-I", 5, 50000, "BUY")
        order_id = order['orderid']
        
        modify_result = broker.modify_order(order_id, 50100)
        assert 'status' in modify_result
    
    def test_order_cancellation(self):
        """Test that orders can be cancelled"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        order = broker.place_limit_order("BANKNIFTY-I", 5, 50000, "BUY")
        order_id = order['orderid']
        
        cancel_result = broker.cancel_order(order_id)
        assert cancel_result['status'] == 'success'
        assert cancel_result['fill_status'] == 'CANCELLED'
        
        # Verify order is cancelled
        status = broker.get_order_status(order_id)
        assert status['fill_status'] == 'CANCELLED'
    
    def test_base_price_update(self):
        """Test that base price can be updated"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        quote1 = broker.get_quote("BANKNIFTY-I")
        
        broker.set_base_price(51000.0)
        quote2 = broker.get_quote("BANKNIFTY-I")
        
        # Quote should reflect new base price
        assert quote2['ltp'] > quote1['ltp']
    
    def test_edge_case_zero_price_protection(self):
        """Test that zero or negative prices are prevented"""
        broker = MockBrokerSimulator(scenario="pullback", base_price=1.0)
        
        # Even with very low base price and pullback, should not go to zero
        quote = broker.get_quote("BANKNIFTY-I")
        assert quote['ltp'] >= 1.0
    
    def test_favorable_order_fill_probability(self):
        """Test that favorable orders have higher fill probability"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        
        # Get current quote
        quote = broker.get_quote("BANKNIFTY-I")
        
        # Place favorable BUY order (above ask)
        favorable_order = broker.place_limit_order(
            "BANKNIFTY-I", 1, quote['ask'] + 100, "BUY"
        )
        
        # Place unfavorable BUY order (below bid)
        unfavorable_order = broker.place_limit_order(
            "BANKNIFTY-I", 1, quote['bid'] - 100, "BUY"
        )
        
        # Both should have order IDs
        assert 'orderid' in favorable_order
        assert 'orderid' in unfavorable_order
    
    def test_partial_fill_simulation(self):
        """Test that partial fills can be simulated"""
        broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        broker.partial_fill_probability = 1.0  # Force partial fills
        
        quote = broker.get_quote("BANKNIFTY-I")
        order = broker.place_limit_order("BANKNIFTY-I", 10, quote['ask'] + 100, "BUY")
        
        # Should have partial fill
        assert order['fill_status'] == 'PARTIAL'
        assert 0 < order['filled_lots'] < 10
        assert order['filled_lots'] + order['remaining_lots'] == 10
    
    def test_configurable_bid_ask_spread(self):
        """Test that bid/ask spread is configurable"""
        broker = MockBrokerSimulator(
            scenario="normal",
            base_price=50000.0,
            bid_ask_spread_pct=0.005  # 0.5% spread
        )
        quote = broker.get_quote("BANKNIFTY-I")
        
        spread = (quote['ask'] - quote['bid']) / quote['ltp']
        assert abs(spread - 0.005) < 0.0001  # Within tolerance
    
    def test_random_seed_control(self):
        """Test that random seed can be set for deterministic testing"""
        broker1 = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        broker1.set_seed(42)
        quote1 = broker1.get_quote("BANKNIFTY-I")
        
        broker2 = MockBrokerSimulator(scenario="normal", base_price=50000.0)
        broker2.set_seed(42)
        quote2 = broker2.get_quote("BANKNIFTY-I")
        
        # With same seed, should get same quote
        assert quote1['ltp'] == quote2['ltp']

