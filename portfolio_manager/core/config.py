"""
Configuration management for portfolio system
"""
from typing import Dict
from core.models import InstrumentConfig, InstrumentType

# Default instrument configurations
INSTRUMENT_CONFIGS = {
    InstrumentType.BANK_NIFTY: InstrumentConfig(
        name="Bank Nifty",
        instrument_type=InstrumentType.BANK_NIFTY,
        lot_size=35,  # Current lot size (Apr-Dec 2025)
        point_value=35.0,  # Rs 35 per point per LOT (35 units × ₹1/point/unit)
        margin_per_lot=270000.0,  # Rs 2.7L per lot
        initial_risk_percent=0.5,
        ongoing_risk_percent=1.0,
        initial_vol_percent=0.5,
        ongoing_vol_percent=0.7,
        initial_atr_mult=1.5,
        trailing_atr_mult=2.5,
        max_pyramids=5
    ),
    InstrumentType.GOLD_MINI: InstrumentConfig(
        name="Gold Mini",
        instrument_type=InstrumentType.GOLD_MINI,
        lot_size=100,  # 100 grams per contract
        point_value=10.0,  # Rs 10 per point per LOT (quoted per 10g, contract is 100g)
        margin_per_lot=105000.0,  # Rs 1.05L per lot (approx 10% of contract value)
        initial_risk_percent=0.5,
        ongoing_risk_percent=1.0,
        initial_vol_percent=0.2,
        ongoing_vol_percent=0.3,
        initial_atr_mult=1.0,
        trailing_atr_mult=2.0,
        max_pyramids=3
    )
}

class PortfolioConfig:
    """Portfolio-level configuration"""

    def __init__(self):
        # Portfolio risk management
        self.max_portfolio_risk_percent = 15.0  # Tom Basso limit
        self.max_portfolio_vol_percent = 5.0
        self.max_margin_utilization_percent = 60.0

        # Pyramid gates
        self.pyramid_risk_warning = 12.0  # Start warning at 12%
        self.pyramid_risk_block = 12.0  # Block new pyramids at 12%
        self.pyramid_vol_block = 4.0  # Block pyramids at 4% vol

        # Equity calculation
        self.equity_mode = "blended"  # 'closed', 'open', or 'blended'
        self.blended_unrealized_weight = 0.5  # 50% of unrealized for blended

        # Position management
        self.use_1r_gate = True  # Require 1R move before first pyramid
        self.atr_pyramid_spacing = 0.5  # ATR spacing between pyramids

        # Peel-off settings
        self.enable_peel_off = True
        self.peel_off_check_interval = 1  # Check every bar

        # Rollover settings
        self.enable_auto_rollover = True
        self.banknifty_rollover_days = 7  # Days before expiry to roll Bank Nifty
        self.gold_mini_rollover_days = 8  # Days before expiry to roll Gold Mini (tender period)

        # Rollover execution settings (tight limit orders)
        self.rollover_initial_buffer_pct = 0.25  # Start at LTP ± 0.25%
        self.rollover_increment_pct = 0.05  # Increase by 0.05% per retry
        self.rollover_max_retries = 5  # 5 retries × 3s = 15s total
        self.rollover_retry_interval_sec = 3.0  # Seconds between retries

        # Rollover strike selection (Bank Nifty)
        self.rollover_strike_interval = 500  # Round to nearest 500
        self.rollover_prefer_1000s = True  # Prefer 1000 multiples over 500s

        # Market hours for rollover execution
        self.nse_market_start = "09:15"  # NSE opens
        self.nse_market_end = "15:30"    # NSE closes
        self.mcx_market_start = "09:00"  # MCX opens
        self.mcx_market_end = "23:30"    # MCX closes
        
        # Bank Nifty futures symbol for rollover (configurable by broker)
        self.banknifty_futures_symbol = "BANKNIFTY-I"  # Near month futures symbol
        
    def get_equity(self, closed_equity: float, unrealized_pnl: float) -> float:
        """
        Calculate equity based on configured mode
        
        Args:
            closed_equity: Realized equity (cash + closed P&L)
            unrealized_pnl: Sum of unrealized P&L from open positions
            
        Returns:
            Equity value based on mode
        """
        if self.equity_mode == "closed":
            return closed_equity
        elif self.equity_mode == "open":
            return closed_equity + unrealized_pnl
        else:  # blended
            return closed_equity + (unrealized_pnl * self.blended_unrealized_weight)

def get_instrument_config(instrument: InstrumentType) -> InstrumentConfig:
    """Get configuration for instrument"""
    return INSTRUMENT_CONFIGS[instrument]

