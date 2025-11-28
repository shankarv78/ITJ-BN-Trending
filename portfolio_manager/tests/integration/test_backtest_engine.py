"""
Integration tests for Backtest Engine

Tests complete backtest workflow:
- Loading signals
- Processing signal sequence
- Portfolio state updates
- Risk management
- Final results
"""
import pytest
from datetime import datetime, timedelta
from backtest.engine import PortfolioBacktestEngine
from core.models import Signal, SignalType
from tests.fixtures.mock_signals import generate_signal_sequence

@pytest.fixture
def backtest_engine():
    """Create backtest engine with Rs 50L capital"""
    return PortfolioBacktestEngine(initial_capital=5000000.0)

class TestPortfolioBacktestEngine:
    """Integration tests for backtest engine"""
    
    def test_engine_initialization(self, backtest_engine):
        """Test engine initializes correctly"""
        assert backtest_engine.portfolio.initial_capital == 5000000.0
        assert backtest_engine.stats['signals_processed'] == 0
        assert len(backtest_engine.sizers) == 2  # Gold + BN
    
    def test_process_base_entry_signal(self, backtest_engine):
        """Test processing base entry signal"""
        signal = Signal(
            timestamp=datetime(2025, 11, 15, 10, 30),
            instrument="GOLD_MINI",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=78500.0,
            stop=77800.0,
            suggested_lots=3,
            atr=700.0,
            er=0.85,
            supertrend=77800.0
        )
        
        result = backtest_engine.process_signal(signal)
        
        assert result['status'] == 'executed'
        assert result['lots'] > 0
        assert backtest_engine.stats['entries_executed'] == 1
    
    def test_full_signal_sequence(self, backtest_engine):
        """Test processing complete signal sequence"""
        signals = generate_signal_sequence()
        
        # Process all signals
        for signal in signals:
            backtest_engine.process_signal(signal)
        
        assert backtest_engine.stats['signals_processed'] == len(signals)
        assert backtest_engine.stats['entries_executed'] >= 1
    
    def test_portfolio_gate_blocks_excessive_risk(self, backtest_engine):
        """Test that portfolio gate blocks entries when risk too high"""
        # Fill portfolio with risky positions
        for i in range(5):
            signal = Signal(
                timestamp=datetime(2025, 11, 15, 10, i),
                instrument="GOLD_MINI",
                signal_type=SignalType.BASE_ENTRY,
                position=f"Long_{i+1}",
                price=78500.0,
                stop=75000.0,  # Very wide stop (high risk)
                suggested_lots=20,  # Large position
                atr=700.0,
                er=0.85,
                supertrend=75000.0
            )
            backtest_engine.process_signal(signal)
        
        # Attempt one more entry
        final_signal = Signal(
            timestamp=datetime(2025, 11, 15, 10, 30),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=48000.0,  # Wide stop
            suggested_lots=10,
            atr=350.0,
            er=0.82,
            supertrend=48000.0
        )
        
        result = backtest_engine.process_signal(final_signal)
        
        # Should be blocked due to portfolio risk
        assert backtest_engine.stats['entries_blocked'] > 0
    
    def test_pyramid_requires_base_position(self, backtest_engine):
        """Test pyramid blocked if no base position"""
        pyramid_signal = Signal(
            timestamp=datetime(2025, 11, 15, 11, 0),
            instrument="GOLD_MINI",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=79000.0,
            stop=78500.0,
            suggested_lots=2,
            atr=720.0,
            er=0.87,
            supertrend=78500.0
        )
        
        result = backtest_engine.process_signal(pyramid_signal)
        
        assert result['status'] == 'blocked'
        assert 'base position' in result['reason'].lower()
    
    def test_exit_closes_position_and_updates_equity(self, backtest_engine):
        """Test exit closes position and updates closed equity"""
        # First, enter a position
        entry_signal = Signal(
            timestamp=datetime(2025, 11, 15, 10, 30),
            instrument="GOLD_MINI",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=78500.0,
            stop=77800.0,
            suggested_lots=3,
            atr=700.0,
            er=0.85,
            supertrend=77800.0
        )
        
        backtest_engine.process_signal(entry_signal)
        initial_equity = backtest_engine.portfolio.closed_equity
        
        # Then exit with profit
        exit_signal = Signal(
            timestamp=datetime(2025, 11, 16, 14, 0),
            instrument="GOLD_MINI",
            signal_type=SignalType.EXIT,
            position="Long_1",
            price=79500.0,  # Rs 1000 profit per unit
            stop=0.0,
            suggested_lots=3,
            atr=720.0,
            er=0.87,
            supertrend=78500.0,
            reason="TOM_BASSO_STOP"
        )
        
        result = backtest_engine.process_signal(exit_signal)
        
        assert result['status'] == 'executed'
        assert result['pnl'] > 0
        assert backtest_engine.portfolio.closed_equity > initial_equity
    
    def test_run_complete_backtest(self, backtest_engine):
        """Test running complete backtest from start to finish"""
        signals = generate_signal_sequence()
        
        results = backtest_engine.run_backtest(signals)
        
        assert 'initial_capital' in results
        assert 'final_equity' in results
        assert 'total_pnl' in results
        assert 'stats' in results
        assert results['initial_capital'] == 5000000.0
    
    def test_statistics_tracking(self, backtest_engine):
        """Test that statistics are tracked correctly"""
        signals = generate_signal_sequence()
        
        backtest_engine.run_backtest(signals)
        
        stats = backtest_engine.stats
        
        assert stats['signals_processed'] == len(signals)
        assert stats['entries_executed'] + stats['entries_blocked'] <= stats['signals_processed']
        assert stats['entries_executed'] >= 0
        assert stats['pyramids_executed'] >= 0
        assert stats['exits_executed'] >= 0

