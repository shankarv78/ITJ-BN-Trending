"""
Configuration management for portfolio system
"""
from typing import Dict, Optional
from core.models import InstrumentConfig, InstrumentType
from core.signal_validation_config import SignalValidationConfig

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
        margin_per_lot=105000.0,  # Rs 1.05L per lot (conservative margin cushion)
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
        self.mcx_market_end = "23:55"    # MCX closes (winter), 23:30 in summer (US DST)
        
        # Bank Nifty futures symbol for rollover (configurable by broker)
        self.banknifty_futures_symbol = "BANKNIFTY-I"  # Near month futures symbol
        
        # Signal validation settings
        self.signal_validation_config: Optional[SignalValidationConfig] = None
        """Signal validation configuration (uses defaults if None)"""
        
        self.execution_strategy: str = "progressive"
        """Execution strategy: 'simple_limit' or 'progressive'"""
        
        self.signal_validation_enabled: bool = True
        """Enable signal validation (can be disabled via feature flag)"""
        
        self.partial_fill_strategy: str = "cancel"
        """Partial fill strategy: 'cancel', 'wait', or 'reattempt' (default: 'cancel')"""

        self.partial_fill_wait_timeout: int = 30
        """Timeout in seconds for 'wait' partial fill strategy (default: 30)"""

        # ============================================================
        # EOD (End-of-Day) Pre-Close Execution Settings
        # ============================================================
        # Enables execution of orders before market close when the last
        # candle's signal would otherwise arrive after market is closed.
        #
        # Timeline:
        # T-15 min: TradingView starts sending EOD_MONITOR signals
        # T-45 sec: Final condition check + position sizing
        # T-30 sec: Place limit order
        # T-15 sec: Track order to completion
        # T-0: Market closes

        self.eod_enabled: bool = True
        """Enable EOD pre-close execution system"""

        self.eod_monitoring_start_minutes: int = 15
        """Start monitoring window (minutes before market close)"""

        self.eod_condition_check_seconds: int = 45
        """Seconds before close to do final condition check"""

        self.eod_execution_seconds: int = 30
        """Seconds before close to place order"""

        self.eod_tracking_seconds: int = 15
        """Seconds before close to track order completion"""

        self.eod_order_timeout: int = 10
        """Order placement timeout in seconds"""

        self.eod_tracking_poll_interval: float = 1.0
        """Interval in seconds between order status polls"""

        self.eod_limit_buffer_pct: float = 0.1
        """Buffer percentage for limit orders (0.1 = 0.1% above LTP for buys)"""

        self.eod_fallback_to_market: bool = True
        """Fallback to market order if limit not filled within timeout"""

        self.eod_fallback_seconds: int = 10
        """Seconds before close to fallback to market order (if enabled)"""

        self.eod_max_signal_age_seconds: int = 90
        """Maximum age of EOD_MONITOR signal before it's considered stale"""

        # Market close times (24-hour format, IST)
        # Note: MCX hours vary with US Daylight Saving Time
        # Summer (Mar-Nov): 23:30, Winter (Nov-Mar): 23:55
        self.market_close_times: Dict[str, str] = {
            "BANK_NIFTY": "15:30",  # NSE closes at 3:30 PM IST (fixed)
            "GOLD_MINI": "23:30"    # MCX summer timing (will be overridden dynamically)
        }
        """Market close times for each instrument (HH:MM format, IST)"""

        # MCX seasonal close times (US DST dependent)
        self.mcx_summer_close: str = "23:30"  # Mar 2nd Sun to Nov 1st Sun (US DST)
        """MCX close time during US Daylight Saving (summer)"""

        self.mcx_winter_close: str = "23:55"  # Nov 1st Sun to Mar 2nd Sun
        """MCX close time during US Standard Time (winter)"""

        # EOD execution for each instrument (can be selectively disabled)
        self.eod_instruments_enabled: Dict[str, bool] = {
            "BANK_NIFTY": True,
            "GOLD_MINI": True
        }
        """Enable/disable EOD execution per instrument"""

    def get_mcx_close_time(self, check_date=None) -> str:
        """
        Get MCX market close time based on US Daylight Saving Time.

        MCX aligns with COMEX (US) trading hours:
        - US DST (Mar 2nd Sun - Nov 1st Sun): 23:30 IST
        - US Standard Time (Nov 1st Sun - Mar 2nd Sun): 23:55 IST

        Args:
            check_date: Date to check (default: today)

        Returns:
            Close time string in HH:MM format
        """
        from datetime import datetime, date
        import pytz

        if check_date is None:
            check_date = date.today()
        elif isinstance(check_date, datetime):
            check_date = check_date.date()

        # Check if US is in DST
        us_eastern = pytz.timezone('America/New_York')
        # Create a datetime at noon on the check date
        check_datetime = datetime(check_date.year, check_date.month, check_date.day, 12, 0)
        localized = us_eastern.localize(check_datetime)

        # If DST offset is non-zero, we're in summer time
        if localized.dst().total_seconds() > 0:
            return self.mcx_summer_close  # 23:30 IST
        else:
            return self.mcx_winter_close  # 23:55 IST

    def get_market_close_time(self, instrument: str, check_date=None) -> str:
        """
        Get market close time for an instrument.

        Handles MCX seasonal timing automatically.

        Args:
            instrument: Instrument name (e.g., "GOLD_MINI", "BANK_NIFTY")
            check_date: Date to check (default: today)

        Returns:
            Close time string in HH:MM format
        """
        if instrument == "GOLD_MINI":
            return self.get_mcx_close_time(check_date)
        return self.market_close_times.get(instrument, "15:30")

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

