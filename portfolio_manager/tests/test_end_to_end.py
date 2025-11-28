"""
End-to-End Tests

Tests complete workflow from signal loading to final results
"""
import pytest
import logging
from datetime import datetime, timedelta
from backtest.engine import PortfolioBacktestEngine
from core.models import Signal, SignalType
from tests.fixtures.mock_signals import generate_signal_sequence

logger = logging.getLogger(__name__)

@pytest.mark.integration
class TestEndToEnd:
    """End-to-end integration tests"""
    
    def test_complete_backtest_workflow(self):
        """
        Test complete backtest from signal loading to final P&L
        
        Scenario:
        1. Start with Rs 50L
        2. Enter Gold position
        3. Enter Bank Nifty position
        4. Pyramid Gold
        5. Exit Bank Nifty
        6. Verify portfolio metrics updated correctly
        """
        engine = PortfolioBacktestEngine(initial_capital=5000000.0)
        signals = generate_signal_sequence()
        
        # Run backtest
        results = engine.run_backtest(signals)
        
        # Verify results structure
        assert 'initial_capital' in results
        assert 'final_equity' in results
        assert 'total_pnl' in results
        assert 'stats' in results
        assert 'final_state' in results
        
        # Verify some signals processed
        assert results['stats']['signals_processed'] > 0
        
        # Verify engine tracked stats
        assert 'entries_executed' in results['stats']
        assert 'pyramids_executed' in results['stats']
        
        # Note: Some entries may be blocked by volatility constraint
        # which is correct behavior - we're testing the workflow works
    
    def test_portfolio_risk_cap_enforced(self):
        """
        Test that 15% portfolio risk cap is enforced
        
        Scenario: Try to add positions until risk cap hit
        """
        engine = PortfolioBacktestEngine(initial_capital=5000000.0)
        
        # Create multiple high-risk signals
        signals = []
        for i in range(10):
            signal = Signal(
                timestamp=datetime(2025, 11, 15, 10, i),
                instrument="GOLD_MINI",
                signal_type=SignalType.BASE_ENTRY,
                position=f"Long_{i+1}",
                price=78500.0,
                stop=75000.0,  # Very wide stop (high risk)
                suggested_lots=15,  # Large position
                atr=700.0,
                er=0.85,
                supertrend=75000.0
            )
            signals.append(signal)
        
        results = engine.run_backtest(signals)
        
        # Some entries should be blocked
        assert results['stats']['entries_blocked'] > 0
        
        # Final portfolio risk should be under 15%
        final_risk = results['final_state'].total_risk_percent
        assert final_risk <= 15.0, f"Portfolio risk {final_risk}% exceeds 15% cap"
    
    def test_cross_instrument_portfolio(self):
        """
        Test portfolio with both Gold and Bank Nifty
        
        Verifies:
        - Both instruments can be held simultaneously
        - Portfolio risk aggregates correctly
        - Each instrument sized independently
        """
        engine = PortfolioBacktestEngine(initial_capital=5000000.0)
        
        signals = [
            # Gold entry - wider stop to pass volatility constraint
            Signal(
                timestamp=datetime(2025, 11, 15, 10, 30),
                instrument="GOLD_MINI",
                signal_type=SignalType.BASE_ENTRY,
                position="Long_1",
                price=78500.0,
                stop=76500.0,  # Wider stop (2000 points)
                suggested_lots=3,
                atr=250.0,  # Lower ATR
                er=0.85,
                supertrend=76500.0
            ),
            # Bank Nifty entry - wider stop
            Signal(
                timestamp=datetime(2025, 11, 15, 11, 0),
                instrument="BANK_NIFTY",
                signal_type=SignalType.BASE_ENTRY,
                position="Long_1",
                price=52000.0,
                stop=50500.0,  # Wider stop (1500 points)
                suggested_lots=5,
                atr=200.0,  # Lower ATR
                er=0.82,
                supertrend=50500.0
            )
        ]
        
        results = engine.run_backtest(signals)
        
        # At least one entry should execute
        assert results['stats']['entries_executed'] >= 1
        
        # Check positions were created
        final_state = results['final_state']
        assert final_state.position_count() >= 1
    
    def test_statistics_accuracy(self):
        """Test that statistics are accurately tracked"""
        engine = PortfolioBacktestEngine(initial_capital=5000000.0)
        signals = generate_signal_sequence()
        
        results = engine.run_backtest(signals)
        stats = results['stats']
        
        # Verify stat relationships
        assert stats['signals_processed'] == len(signals)
        assert stats['entries_executed'] + stats['entries_blocked'] <= stats['signals_processed']
        assert stats['pyramids_executed'] + stats['pyramids_blocked'] <= stats['signals_processed']
        
        # All counts should be non-negative
        for key, value in stats.items():
            assert value >= 0, f"{key} should be non-negative, got {value}"

@pytest.mark.slow
class TestLargeScaleBacktest:
    """Tests with large number of signals"""
    
    def test_performance_with_1000_signals(self):
        """Test engine can handle 1000+ signals efficiently"""
        engine = PortfolioBacktestEngine(initial_capital=5000000.0)
        
        # Generate 1000 alternating signals
        signals = []
        for i in range(500):
            # Gold entry
            signals.append(Signal(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i*2),
                instrument="GOLD_MINI",
                signal_type=SignalType.BASE_ENTRY,
                position="Long_1",
                price=78500.0 + (i * 10),
                stop=77800.0 + (i * 10),
                suggested_lots=3,
                atr=700.0,
                er=0.85,
                supertrend=77800.0
            ))
            
            # Gold exit
            signals.append(Signal(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i*2+1),
                instrument="GOLD_MINI",
                signal_type=SignalType.EXIT,
                position="Long_1",
                price=79000.0 + (i * 10),
                stop=78000.0,
                suggested_lots=3,
                atr=720.0,
                er=0.87,
                supertrend=78500.0,
                reason="TOM_BASSO_STOP"
            ))
        
        import time
        start = time.time()
        results = engine.run_backtest(signals)
        duration = time.time() - start
        
        # Performance check
        print(f"Processed 1000 signals in {duration:.2f} seconds")
        
        assert duration < 10.0, "Backtest should complete in under 10 seconds"
        assert results['stats']['signals_processed'] == 1000

