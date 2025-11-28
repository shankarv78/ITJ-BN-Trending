"""
Pyramid Gate Controller

Checks if pyramiding is allowed based on:
1. Instrument-level gates (1R move, ATR spacing)
2. Portfolio-level gates (15% risk cap, 5% vol cap)
3. Profit gates (unrealized P&L positive)
"""
import logging
from typing import Dict
from core.models import Signal, Position, PyramidGateCheck, InstrumentType
from core.portfolio_state import PortfolioStateManager
from core.config import PortfolioConfig, get_instrument_config

logger = logging.getLogger(__name__)

class PyramidGateController:
    """Controls pyramid entry decisions"""
    
    def __init__(self, portfolio_manager: PortfolioStateManager, config: PortfolioConfig = None):
        """
        Initialize pyramid gate controller
        
        Args:
            portfolio_manager: Portfolio state manager
            config: Portfolio configuration
        """
        self.portfolio = portfolio_manager
        self.config = config or PortfolioConfig()
    
    def check_pyramid_allowed(
        self,
        signal: Signal,
        instrument: str,
        base_position: Position,
        last_pyramid_price: float
    ) -> PyramidGateCheck:
        """
        Check all pyramid gates
        
        Args:
            signal: Pyramid signal
            instrument: Instrument name (GOLD_MINI or BANK_NIFTY)
            base_position: Base entry position for this instrument
            last_pyramid_price: Price of last pyramid entry
            
        Returns:
            PyramidGateCheck with detailed results
        """
        # Get instrument config
        if instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        elif instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        else:
            return PyramidGateCheck(
                allowed=False,
                instrument_gate=False,
                portfolio_gate=False,
                profit_gate=False,
                reason=f"Unknown instrument: {instrument}"
            )
        
        inst_config = get_instrument_config(inst_type)
        
        # CHECK 1: Instrument-level gate
        instrument_gate, inst_reason = self._check_instrument_gate(
            signal, base_position, last_pyramid_price, inst_config
        )
        
        # CHECK 2: Portfolio-level gate
        portfolio_gate, port_reason = self._check_portfolio_gate(signal, inst_config)
        
        # CHECK 3: Profit gate
        profit_gate, profit_reason = self._check_profit_gate(instrument)
        
        # ALL must pass
        allowed = instrument_gate and portfolio_gate and profit_gate
        
        if not allowed:
            reasons = []
            if not instrument_gate:
                reasons.append(inst_reason)
            if not portfolio_gate:
                reasons.append(port_reason)
            if not profit_gate:
                reasons.append(profit_reason)
            reason = " | ".join(reasons)
        else:
            reason = "All gates passed"
        
        # Calculate metrics for display
        price_move_from_entry = signal.price - base_position.entry_price
        initial_risk = base_position.entry_price - base_position.initial_stop
        price_move_r = (price_move_from_entry / initial_risk) if initial_risk > 0 else 0
        
        atr_spacing = (signal.price - last_pyramid_price) / signal.atr if signal.atr > 0 else 0
        
        state = self.portfolio.get_current_state()
        
        result = PyramidGateCheck(
            allowed=allowed,
            instrument_gate=instrument_gate,
            portfolio_gate=portfolio_gate,
            profit_gate=profit_gate,
            reason=reason,
            price_move_r=price_move_r,
            atr_spacing=atr_spacing,
            portfolio_risk_pct=state.total_risk_percent,
            portfolio_vol_pct=state.total_vol_percent
        )
        
        logger.info(f"Pyramid gate check: {allowed} - {reason}")
        return result
    
    def _check_instrument_gate(
        self,
        signal: Signal,
        base_position: Position,
        last_pyramid_price: float,
        inst_config
    ) -> tuple:
        """Check instrument-level pyramid conditions"""
        
        # Condition 1: 1R move from entry (if enabled)
        if self.config.use_1r_gate:
            price_move = signal.price - base_position.entry_price
            initial_risk = base_position.entry_price - base_position.initial_stop
            
            if initial_risk <= 0:
                return False, "Invalid initial risk"
            
            if price_move <= initial_risk:
                return False, f"Price not > 1R (moved {price_move:.0f}, need {initial_risk:.0f})"
        
        # Condition 2: ATR spacing from last pyramid
        price_move_from_last = signal.price - last_pyramid_price
        atr_moves = price_move_from_last / signal.atr if signal.atr > 0 else 0
        
        if atr_moves < self.config.atr_pyramid_spacing:
            return False, f"ATR spacing {atr_moves:.2f} < {self.config.atr_pyramid_spacing}"
        
        return True, "Instrument gate passed"
    
    def _check_portfolio_gate(self, signal: Signal, inst_config) -> tuple:
        """Check portfolio-level constraints"""
        state = self.portfolio.get_current_state()
        
        # Estimate risk/vol of proposed pyramid
        # (Simplified - actual sizing will be calculated separately)
        risk_per_point = signal.price - signal.stop
        estimated_lots = 5  # Conservative estimate for gate check
        
        est_risk = risk_per_point * estimated_lots * inst_config.point_value
        est_vol = signal.atr * estimated_lots * inst_config.point_value
        
        # Check risk limit (use warning threshold for pyramids)
        projected_risk_pct = ((state.total_risk_amount + est_risk) / state.equity * 100) if state.equity > 0 else 0
        
        if projected_risk_pct > self.config.pyramid_risk_block:
            return False, f"Portfolio risk would be {projected_risk_pct:.1f}% (block at {self.config.pyramid_risk_block}%)"
        
        # Check volatility limit
        projected_vol_pct = ((state.total_vol_amount + est_vol) / state.equity * 100) if state.equity > 0 else 0
        
        if projected_vol_pct > self.config.pyramid_vol_block:
            return False, f"Portfolio vol would be {projected_vol_pct:.1f}% (block at {self.config.pyramid_vol_block}%)"
        
        return True, "Portfolio gate passed"
    
    def _check_profit_gate(self, instrument: str) -> tuple:
        """Check if instrument positions are profitable"""
        state = self.portfolio.get_current_state()
        positions = state.get_positions_for_instrument(instrument)
        
        if not positions:
            return False, "No base position exists"
        
        # Check combined unrealized P&L for this instrument
        total_pnl = sum(p.unrealized_pnl for p in positions.values())
        
        if total_pnl <= 0:
            return False, f"Instrument P&L negative: ₹{total_pnl:,.0f}"
        
        return True, "Profit gate passed"

