"""
Unit tests for Portfolio State Manager

Tests portfolio-level calculations:
- Risk aggregation across positions
- Volatility aggregation  
- Margin utilization
- Equity calculations (closed, open, blended)
- Portfolio gate checks
"""
import pytest
from datetime import datetime
from core.portfolio_state import PortfolioStateManager
from core.models import Position
from core.config import PortfolioConfig

@pytest.fixture
def portfolio_manager():
    """Create portfolio manager with Rs 50L capital"""
    return PortfolioStateManager(initial_capital=5000000.0)

@pytest.fixture
def sample_gold_position():
    """Sample Gold Mini position"""
    return Position(
        position_id="Gold_Long_1",
        instrument="GOLD_MINI",
        entry_timestamp=datetime(2025, 11, 15, 10, 30),
        entry_price=78500.0,
        lots=3,
        quantity=300,  # 3 lots × 100g
        initial_stop=77800.0,
        current_stop=78000.0,
        highest_close=78800.0,
        atr=150.0,  # Realistic ATR for Gold Mini
        status="open"
    )

@pytest.fixture
def sample_bn_position():
    """Sample Bank Nifty position"""
    return Position(
        position_id="BN_Long_1",
        instrument="BANK_NIFTY",
        entry_timestamp=datetime(2025, 11, 15, 11, 0),
        entry_price=52000.0,
        lots=5,
        quantity=175,  # 5 lots × 35
        initial_stop=51650.0,
        current_stop=51800.0,
        highest_close=52300.0,
        atr=200.0,  # Realistic ATR for Bank Nifty
        status="open"
    )

class TestPortfolioStateManager:
    """Test suite for portfolio state manager"""
    
    def test_initialization(self, portfolio_manager):
        """Test manager initializes with correct capital"""
        assert portfolio_manager.initial_capital == 5000000.0
        assert portfolio_manager.closed_equity == 5000000.0
        assert len(portfolio_manager.positions) == 0
    
    def test_add_position(self, portfolio_manager, sample_gold_position):
        """Test adding position to portfolio"""
        portfolio_manager.add_position(sample_gold_position)
        
        assert len(portfolio_manager.positions) == 1
        assert "Gold_Long_1" in portfolio_manager.positions
        assert portfolio_manager.positions["Gold_Long_1"].lots == 3
    
    def test_closed_equity_calculation(self, portfolio_manager):
        """Test closed equity equals initial capital when no trades closed"""
        state = portfolio_manager.get_current_state()
        
        assert state.closed_equity == 5000000.0
    
    def test_open_equity_with_unrealized_pnl(self, portfolio_manager, sample_gold_position):
        """Test open equity includes unrealized P&L"""
        sample_gold_position.unrealized_pnl = 50000.0  # Rs 50k profit
        portfolio_manager.add_position(sample_gold_position)
        
        state = portfolio_manager.get_current_state()
        
        # Open equity = Closed + Unrealized
        assert state.open_equity == 5050000.0
    
    def test_blended_equity_calculation(self, portfolio_manager, sample_gold_position):
        """Test blended equity uses 50% of unrealized"""
        sample_gold_position.unrealized_pnl = 100000.0  # Rs 1L profit
        portfolio_manager.add_position(sample_gold_position)
        
        state = portfolio_manager.get_current_state()
        
        # Blended = Closed + (50% × Unrealized)
        # = 5000000 + (0.5 × 100000) = 5050000
        assert state.blended_equity == 5050000.0
    
    def test_close_position_updates_closed_equity(self, portfolio_manager, sample_gold_position):
        """Test closing position updates realized equity"""
        portfolio_manager.add_position(sample_gold_position)

        # Close with profit
        exit_price = 79000.0  # Rs 500 profit per 10g
        pnl = portfolio_manager.close_position(
            "Gold_Long_1",
            exit_price,
            datetime(2025, 11, 16)
        )

        # Gold Mini P&L = price_diff × lots × 10 (Rs 10 per point per lot)
        # P&L = (79000 - 78500) × 3 lots × 10 = 500 × 3 × 10 = Rs 15,000
        expected_pnl = (79000 - 78500) * 3 * 10
        assert pnl == pytest.approx(expected_pnl)

        # Closed equity should update
        assert portfolio_manager.closed_equity == pytest.approx(5000000 + expected_pnl)
    
    def test_portfolio_risk_calculation_single_position(
        self, portfolio_manager, sample_gold_position
    ):
        """Test portfolio risk with single position"""
        sample_gold_position.current_stop = 78000.0
        portfolio_manager.add_position(sample_gold_position)

        state = portfolio_manager.get_current_state()

        # Expected risk (Gold Mini):
        # Risk points = 78500 - 78000 = 500 points
        # Risk = 500 pts × 3 lots × Rs 10/pt/lot = Rs 15,000
        # Risk% = 15000 / 5000000 × 100 = 0.3%

        expected_risk = 500 * 3 * 10  # Rs 15,000
        assert state.total_risk_amount == pytest.approx(expected_risk)
        assert state.total_risk_percent == pytest.approx(0.3)
    
    def test_portfolio_risk_calculation_multiple_positions(
        self, portfolio_manager, sample_gold_position, sample_bn_position
    ):
        """Test portfolio risk aggregates across instruments"""
        portfolio_manager.add_position(sample_gold_position)
        portfolio_manager.add_position(sample_bn_position)

        state = portfolio_manager.get_current_state()

        # Gold risk: (78500 - 78000) × 3 lots × 10 = 500 × 3 × 10 = Rs 15,000
        # BN risk: (52000 - 51800) × 5 lots × 35 = 200 × 5 × 35 = Rs 35,000
        # Total: Rs 50,000 = 1% of 50L

        gold_risk = 500 * 3 * 10   # Rs 15,000
        bn_risk = 200 * 5 * 35     # Rs 35,000
        total_risk = gold_risk + bn_risk  # Rs 50,000

        assert state.total_risk_amount == pytest.approx(total_risk)
        assert state.gold_risk_percent == pytest.approx(0.3, rel=0.01)
        assert state.banknifty_risk_percent == pytest.approx(0.7, rel=0.01)
        assert state.total_risk_percent == pytest.approx(1.0, rel=0.01)
    
    def test_margin_utilization_calculation(
        self, portfolio_manager, sample_gold_position, sample_bn_position
    ):
        """Test margin utilization calculation"""
        portfolio_manager.add_position(sample_gold_position)
        portfolio_manager.add_position(sample_bn_position)
        
        state = portfolio_manager.get_current_state()
        
        # Gold: 3 lots × 1.05L = 3.15L
        # BN: 5 lots × 2.7L = 13.5L
        # Total: 16.65L
        # Utilization: 16.65 / 50 × 100 = 33.3%
        
        expected_margin = (3 * 105000) + (5 * 270000)
        assert state.margin_used == pytest.approx(expected_margin)
        assert state.margin_utilization_percent == pytest.approx(33.3, rel=0.01)
    
    def test_portfolio_gate_allows_within_limits(self, portfolio_manager, sample_gold_position):
        """Test portfolio gate allows position within limits"""
        # Use a smaller position with realistic ATR to keep risk and vol low
        small_position = Position(
            position_id="Gold_Long_1",
            instrument="GOLD_MINI",
            entry_timestamp=datetime(2025, 11, 15, 10, 30),
            entry_price=78500.0,
            lots=1,  # Small position
            quantity=100,  # 1 lot
            initial_stop=77800.0,
            current_stop=78300.0,  # Tight stop
            highest_close=78800.0,
            atr=100.0,  # Realistic ATR (not 450 placeholder)
            status="open"
        )
        portfolio_manager.add_position(small_position)

        # Propose new position with moderate risk and vol
        # New position: 1 lot with ATR 100
        # Vol = 100 (ATR) × 100 (qty) × 10 (point_value) = Rs 10,000 (0.2% of 50L)
        # Existing vol = 100 × 100 × 10 = Rs 10,000 (0.2%)
        # Total vol = 0.4% (well under 5% limit)
        new_risk = 100000.0  # Rs 1L (2% of 50L)
        new_vol = 10000.0    # Rs 10k (0.2% of 50L)

        allowed, reason = portfolio_manager.check_portfolio_gate(new_risk, new_vol)

        # Current: ~4% risk (200 pts × 100 units × 10), proposed: 2% → total: 6% (under 15% limit)
        # Current: 0.2% vol, proposed: 0.2% → total: 0.4% (under 5% limit)
        assert allowed is True
        assert "passed" in reason.lower()
    
    def test_portfolio_gate_blocks_over_risk_limit(self, portfolio_manager):
        """Test portfolio gate blocks when risk would exceed 15%"""
        # Add positions totaling 14% risk
        for i in range(5):
            pos = Position(
                position_id=f"Gold_Long_{i+1}",
                instrument="GOLD_MINI",
                entry_timestamp=datetime(2025, 11, 15),
                entry_price=78500.0,
                lots=10,  # Large position
                quantity=1000,
                initial_stop=77000.0,  # Wide stop
                current_stop=77000.0,
                highest_close=78500.0,
                status="open"
            )
            portfolio_manager.add_position(pos)
        
        # Risk per position: (78500 - 77000) × 1000 × 10 = Rs 15,00,000 = 3%
        # 5 positions × 3% = 15% (at limit)
        
        # Try to add one more position
        new_risk = 150000.0  # Another 3%
        new_vol = 100000.0
        
        allowed, reason = portfolio_manager.check_portfolio_gate(new_risk, new_vol)
        
        assert allowed is False
        assert "risk" in reason.lower()
        assert "15" in reason  # Should mention the 15% limit
    
    def test_get_positions_for_instrument(
        self, portfolio_manager, sample_gold_position, sample_bn_position
    ):
        """Test filtering positions by instrument"""
        portfolio_manager.add_position(sample_gold_position)
        portfolio_manager.add_position(sample_bn_position)
        
        state = portfolio_manager.get_current_state()
        gold_positions = state.get_positions_for_instrument("GOLD_MINI")
        bn_positions = state.get_positions_for_instrument("BANK_NIFTY")
        
        assert len(gold_positions) == 1
        assert len(bn_positions) == 1
        assert "Gold_Long_1" in gold_positions
        assert "BN_Long_1" in bn_positions
    
    def test_position_count(self, portfolio_manager, sample_gold_position, sample_bn_position):
        """Test position counting"""
        state = portfolio_manager.get_current_state()
        assert state.position_count() == 0
        
        portfolio_manager.add_position(sample_gold_position)
        state = portfolio_manager.get_current_state()
        assert state.position_count() == 1
        
        portfolio_manager.add_position(sample_bn_position)
        state = portfolio_manager.get_current_state()
        assert state.position_count() == 2
    
    def test_update_unrealized_pnl(self, portfolio_manager, sample_gold_position):
        """Test updating unrealized P&L as price moves"""
        portfolio_manager.add_position(sample_gold_position)

        # Update with new price
        portfolio_manager.update_position_unrealized_pnl("Gold_Long_1", 79000.0)

        # Gold Mini P&L = price_diff × lots × 10
        # P&L = (79000 - 78500) × 3 lots × 10 = 500 × 3 × 10 = Rs 15,000
        pos = portfolio_manager.positions["Gold_Long_1"]
        assert pos.unrealized_pnl == pytest.approx(15000.0)
    
    def test_closed_positions_excluded_from_open_count(
        self, portfolio_manager, sample_gold_position
    ):
        """Test that closed positions don't count as open"""
        portfolio_manager.add_position(sample_gold_position)
        
        state1 = portfolio_manager.get_current_state()
        assert state1.position_count() == 1
        
        # Close the position
        portfolio_manager.close_position("Gold_Long_1", 79000.0, datetime(2025, 11, 16))
        
        state2 = portfolio_manager.get_current_state()
        assert state2.position_count() == 0  # No open positions
        assert len(portfolio_manager.positions) == 1  # Still in history
    
    @pytest.mark.parametrize("equity_mode,closed,unrealized,expected", [
        ("closed", 5000000, 100000, 5000000),  # Ignores unrealized
        ("open", 5000000, 100000, 5100000),    # Includes all unrealized
        ("blended", 5000000, 100000, 5050000), # Includes 50% unrealized
    ])
    def test_equity_mode_calculations(
        self, equity_mode, closed, unrealized, expected, sample_gold_position
    ):
        """Test different equity calculation modes"""
        config = PortfolioConfig()
        config.equity_mode = equity_mode
        
        pm = PortfolioStateManager(closed, config)
        sample_gold_position.unrealized_pnl = unrealized
        pm.add_position(sample_gold_position)
        
        state = pm.get_current_state()
        
        assert state.equity == pytest.approx(expected)

