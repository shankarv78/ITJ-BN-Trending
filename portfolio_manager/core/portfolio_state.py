"""
Portfolio State Manager

Tracks all positions, calculates portfolio-level metrics:
- Total portfolio risk (sum of all position risks)
- Total portfolio volatility
- Margin utilization
- Equity calculations (closed, open, blended)
"""
import logging
from typing import Dict, List, Tuple
from datetime import datetime
from core.models import Position, PortfolioState, InstrumentType
from core.config import PortfolioConfig, get_instrument_config

logger = logging.getLogger(__name__)

class PortfolioStateManager:
    """Manages portfolio state and calculates metrics"""
    
    def __init__(self, initial_capital: float, portfolio_config: PortfolioConfig = None):
        """
        Initialize portfolio state manager
        
        Args:
            initial_capital: Starting capital in Rs
            portfolio_config: Portfolio configuration
        """
        self.initial_capital = initial_capital
        self.config = portfolio_config or PortfolioConfig()
        
        # Current state
        self.closed_equity = initial_capital
        self.positions: Dict[str, Position] = {}
        
        logger.info(f"Portfolio initialized: Capital=₹{initial_capital:,.0f}")
    
    def get_current_state(self, current_time: datetime = None) -> PortfolioState:
        """
        Get current portfolio state snapshot
        
        Args:
            current_time: Current timestamp
            
        Returns:
            PortfolioState with all metrics calculated
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Calculate unrealized P&L
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values() 
                                    if p.status == "open")
        
        # Calculate equity values
        open_equity = self.closed_equity + total_unrealized_pnl
        blended_equity = self.config.get_equity(self.closed_equity, total_unrealized_pnl)
        
        # Create state object
        state = PortfolioState(
            timestamp=current_time,
            equity=blended_equity,  # Primary equity for decisions
            closed_equity=self.closed_equity,
            open_equity=open_equity,
            blended_equity=blended_equity,
            positions=dict(self.positions)
        )
        
        # Calculate portfolio metrics
        self._calculate_risk_metrics(state)
        self._calculate_volatility_metrics(state)
        self._calculate_margin_metrics(state)
        
        return state
    
    def _calculate_risk_metrics(self, state: PortfolioState):
        """Calculate portfolio risk metrics"""
        total_risk = 0.0
        gold_risk = 0.0
        bn_risk = 0.0
        
        for pos in state.get_open_positions().values():
            # Get instrument config for point value
            instrument = pos.instrument
            if instrument == "BANK_NIFTY":
                inst_type = InstrumentType.BANK_NIFTY
            elif instrument == "GOLD_MINI":
                inst_type = InstrumentType.GOLD_MINI
            else:
                logger.warning(f"Unknown instrument: {instrument}")
                continue
            
            config = get_instrument_config(inst_type)
            pos_risk = pos.calculate_risk(config.point_value)
            
            total_risk += pos_risk
            if instrument == "GOLD_MINI":
                gold_risk += pos_risk
            else:
                bn_risk += pos_risk
        
        state.total_risk_amount = total_risk
        state.total_risk_percent = (total_risk / state.equity * 100) if state.equity > 0 else 0
        state.gold_risk_percent = (gold_risk / state.equity * 100) if state.equity > 0 else 0
        state.banknifty_risk_percent = (bn_risk / state.equity * 100) if state.equity > 0 else 0
    
    def _calculate_volatility_metrics(self, state: PortfolioState):
        """Calculate portfolio volatility metrics"""
        total_vol = 0.0
        gold_vol = 0.0
        bn_vol = 0.0

        for pos in state.get_open_positions().values():
            # Volatility contribution = ATR × Quantity × Point_Value
            instrument = pos.instrument

            # Use actual ATR from position, fallback to typical values if not set
            if pos.atr > 0:
                atr = pos.atr
            else:
                # Fallback to typical ATR if not stored (backwards compatibility)
                atr = 450 if instrument == "GOLD_MINI" else 350

            if instrument == "GOLD_MINI":
                point_val = 10  # Rs 10 per point per lot
                vol = atr * pos.lots * point_val
                gold_vol += vol
            else:  # BANK_NIFTY
                point_val = 35  # Rs 35 per point per lot
                vol = atr * pos.lots * point_val
                bn_vol += vol

            total_vol += vol
        
        state.total_vol_amount = total_vol
        state.total_vol_percent = (total_vol / state.equity * 100) if state.equity > 0 else 0
        state.gold_vol_percent = (gold_vol / state.equity * 100) if state.equity > 0 else 0
        state.banknifty_vol_percent = (bn_vol / state.equity * 100) if state.equity > 0 else 0
    
    def _calculate_margin_metrics(self, state: PortfolioState):
        """Calculate margin utilization metrics"""
        total_margin_used = 0.0
        
        for pos in state.get_open_positions().values():
            instrument = pos.instrument
            
            if instrument == "GOLD_MINI":
                margin_per_lot = 105000.0
            else:  # BANK_NIFTY
                margin_per_lot = 270000.0
            
            total_margin_used += pos.lots * margin_per_lot
        
        state.margin_used = total_margin_used
        state.margin_available = max(0, state.equity - total_margin_used)
        state.margin_utilization_percent = (
            (total_margin_used / state.equity * 100) if state.equity > 0 else 0
        )
    
    def add_position(self, position: Position):
        """Add new position to portfolio"""
        self.positions[position.position_id] = position
        logger.info(f"Position added: {position.position_id}, {position.lots} lots @ ₹{position.entry_price}")
    
    def close_position(self, position_id: str, exit_price: float, exit_time: datetime) -> float:
        """
        Close position and update closed equity
        
        Args:
            position_id: Position to close
            exit_price: Exit price
            exit_time: Exit timestamp
            
        Returns:
            Realized P&L from this position
        """
        if position_id not in self.positions:
            logger.error(f"Position not found: {position_id}")
            return 0.0
        
        pos = self.positions[position_id]
        
        # Get point value
        if pos.instrument == "GOLD_MINI":
            point_value = 10.0
        else:
            point_value = 35.0
        
        # Calculate realized P&L
        pnl = pos.calculate_pnl(exit_price, point_value)
        pos.realized_pnl = pnl
        pos.status = "closed"
        
        # Update closed equity
        self.closed_equity += pnl
        
        logger.info(f"Position closed: {position_id}, P&L=₹{pnl:,.0f}, "
                   f"New closed equity=₹{self.closed_equity:,.0f}")
        
        return pnl
    
    def update_position_unrealized_pnl(self, position_id: str, current_price: float):
        """Update unrealized P&L for open position"""
        if position_id not in self.positions:
            return
        
        pos = self.positions[position_id]
        if pos.status != "open":
            return
        
        # Get point value
        if pos.instrument == "GOLD_MINI":
            point_value = 10.0
        else:
            point_value = 35.0
        
        pos.unrealized_pnl = pos.calculate_pnl(current_price, point_value)
    
    def check_portfolio_gate(
        self, 
        new_position_risk: float, 
        new_position_vol: float
    ) -> Tuple[bool, str]:
        """
        Check if new position would exceed portfolio limits
        
        Args:
            new_position_risk: Risk of proposed position in Rs
            new_position_vol: Volatility of proposed position in Rs
            
        Returns:
            (allowed, reason)
        """
        state = self.get_current_state()
        
        # Check risk limit
        projected_risk = state.total_risk_amount + new_position_risk
        projected_risk_pct = (projected_risk / state.equity * 100) if state.equity > 0 else 0
        
        if projected_risk_pct > self.config.max_portfolio_risk_percent:
            reason = f"Portfolio risk would be {projected_risk_pct:.1f}% (limit: {self.config.max_portfolio_risk_percent}%)"
            logger.warning(f"Portfolio gate BLOCKED: {reason}")
            return False, reason
        
        # Check volatility limit
        projected_vol = state.total_vol_amount + new_position_vol
        projected_vol_pct = (projected_vol / state.equity * 100) if state.equity > 0 else 0
        
        if projected_vol_pct > self.config.max_portfolio_vol_percent:
            reason = f"Portfolio volatility would be {projected_vol_pct:.1f}% (limit: {self.config.max_portfolio_vol_percent}%)"
            logger.warning(f"Portfolio gate BLOCKED: {reason}")
            return False, reason
        
        logger.debug(f"Portfolio gate OPEN: Risk={projected_risk_pct:.1f}%, Vol={projected_vol_pct:.1f}%")
        return True, "Portfolio gates passed"

