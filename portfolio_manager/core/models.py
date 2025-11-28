"""
Data models for portfolio management system
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict
from enum import Enum
from dateutil import parser as date_parser  # For robust ISO 8601 parsing

class InstrumentType(Enum):
    """Supported instruments"""
    GOLD_MINI = "GOLD_MINI"
    BANK_NIFTY = "BANK_NIFTY"

class SignalType(Enum):
    """Signal types"""
    BASE_ENTRY = "BASE_ENTRY"
    PYRAMID = "PYRAMID"
    EXIT = "EXIT"

class PositionLayer(Enum):
    """Position layers for pyramiding"""
    BASE = "Long_1"
    PYR1 = "Long_2"
    PYR2 = "Long_3"
    PYR3 = "Long_4"
    PYR4 = "Long_5"
    PYR5 = "Long_6"

@dataclass
class InstrumentConfig:
    """Configuration for each instrument"""
    name: str
    instrument_type: InstrumentType
    lot_size: int  # Units per lot (35 for BN, 100g for Gold)
    point_value: float  # Rs per point PER LOT (35 for BN, 10 for Gold Mini)
    margin_per_lot: float  # Rs per lot
    initial_risk_percent: float = 0.5  # Initial position risk
    ongoing_risk_percent: float = 1.0  # Ongoing position risk
    initial_vol_percent: float = 0.2  # Initial volatility exposure
    ongoing_vol_percent: float = 0.3  # Ongoing volatility exposure
    initial_atr_mult: float = 1.0  # Initial stop multiplier
    trailing_atr_mult: float = 2.0  # Trailing stop multiplier
    max_pyramids: int = 5  # Maximum pyramid levels

@dataclass
class Signal:
    """Trading signal from TradingView"""
    timestamp: datetime
    instrument: str
    signal_type: SignalType
    position: str  # Long_1, Long_2, etc.
    price: float
    stop: float
    suggested_lots: int
    atr: float
    er: float  # Efficiency ratio
    supertrend: float
    roc: Optional[float] = None
    reason: Optional[str] = None  # Required for EXIT signals
    
    def __post_init__(self):
        """Validate signal data"""
        if self.price <= 0:
            raise ValueError(f"Invalid price: {self.price}")
        if self.signal_type != SignalType.EXIT and self.stop <= 0:
            raise ValueError(f"Invalid stop: {self.stop}")
        if self.atr < 0:
            raise ValueError(f"Invalid ATR: {self.atr}")
        # EXIT signals must have a reason
        if self.signal_type == SignalType.EXIT and not self.reason:
            raise ValueError("EXIT signals require a 'reason' field")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Signal':
        """
        Create Signal from webhook JSON data
        
        Args:
            data: Dictionary with webhook JSON data
            
        Returns:
            Signal instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validate required fields
        required_fields = ['type', 'instrument', 'position', 'price', 'stop',
                          'lots', 'atr', 'er', 'supertrend', 'timestamp']
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        # Parse and validate signal type (handle both "BASE_ENTRY" and "base_entry")
        signal_type_str = data['type'].upper()
        try:
            signal_type = SignalType[signal_type_str]
        except KeyError:
            valid_types = [e.value for e in SignalType]
            raise ValueError(f"Invalid signal type: '{data['type']}'. Must be one of: {valid_types}")

        # Validate instrument
        instrument = data['instrument'].upper()
        if instrument not in ['BANK_NIFTY', 'GOLD_MINI']:
            raise ValueError(f"Invalid instrument: {instrument}")

        # Strict position validation
        position = data['position']
        valid_positions = ['Long_1', 'Long_2', 'Long_3', 'Long_4', 'Long_5', 'Long_6', 'ALL']
        if position not in valid_positions:
            raise ValueError(f"Invalid position: {position}. Must be one of: {valid_positions}")

        # Parse timestamp using dateutil for robust ISO 8601 handling
        # Handles: milliseconds, timezone offsets, various formats
        timestamp_str = data['timestamp']
        try:
            timestamp = date_parser.parse(timestamp_str)
        except Exception as e:
            raise ValueError(f"Invalid timestamp format: '{timestamp_str}'. Expected ISO 8601 format.")

        # Type coercion
        try:
            price = float(data['price'])
            stop = float(data['stop'])
            lots = int(data['lots'])
            atr = float(data['atr'])
            er = float(data['er'])
            supertrend = float(data['supertrend'])
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid numeric field: {e}")

        # Optional fields
        roc = float(data['roc']) if 'roc' in data and data['roc'] is not None else None
        reason = data.get('reason')

        return cls(
            timestamp=timestamp,
            instrument=instrument,
            signal_type=signal_type,
            position=position,
            price=price,
            stop=stop,
            suggested_lots=lots,
            atr=atr,
            er=er,
            supertrend=supertrend,
            roc=roc,
            reason=reason
        )

class RolloverStatus(Enum):
    """Rollover status for positions"""
    NONE = "none"           # Not yet rolled / no rollover needed
    PENDING = "pending"     # Scheduled for rollover
    IN_PROGRESS = "in_progress"  # Rollover in progress
    ROLLED = "rolled"       # Successfully rolled to next month
    FAILED = "failed"       # Rollover failed, needs attention


@dataclass
class Position:
    """Active trading position"""
    position_id: str  # Long_1, Long_2, etc.
    instrument: str  # GOLD_MINI or BANK_NIFTY
    entry_timestamp: datetime
    entry_price: float
    lots: int
    quantity: int  # lots × lot_size
    initial_stop: float
    current_stop: float
    highest_close: float
    atr: float = 0.0  # ATR at entry (for volatility calculations)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: str = "open"  # open, closed, partial

    # For synthetic futures (Bank Nifty)
    strike: Optional[int] = None
    expiry: Optional[str] = None
    pe_symbol: Optional[str] = None
    ce_symbol: Optional[str] = None
    pe_order_id: Optional[str] = None
    ce_order_id: Optional[str] = None

    # For Gold Mini futures
    contract_month: Optional[str] = None  # e.g., "DEC25", "JAN26"
    futures_symbol: Optional[str] = None  # e.g., "GOLDM25DEC31FUT"
    futures_order_id: Optional[str] = None

    # Rollover tracking
    rollover_status: str = "none"  # none, pending, in_progress, rolled, failed
    original_expiry: Optional[str] = None  # Expiry before rollover (for tracking)
    original_strike: Optional[int] = None  # Strike before rollover (for Bank Nifty)
    original_entry_price: Optional[float] = None  # Entry price before rollover (for P&L calculation)
    pe_entry_price: Optional[float] = None  # Original PE entry price (for Bank Nifty synthetic)
    ce_entry_price: Optional[float] = None  # Original CE entry price (for Bank Nifty synthetic)
    rollover_timestamp: Optional[datetime] = None  # When rollover was executed
    rollover_pnl: float = 0.0  # P&L incurred during rollover (slippage, spread)
    rollover_count: int = 0  # Number of times this position has been rolled

    # Metadata
    risk_contribution: float = 0.0  # % of portfolio equity
    vol_contribution: float = 0.0  # % of portfolio equity
    limiter: Optional[str] = None  # What constraint limited size
    is_base_position: bool = False  # TRUE for base entry, FALSE for pyramids
    
    def calculate_risk(self, point_value: float) -> float:
        """
        Calculate current risk exposure in Rs

        Args:
            point_value: Rs per point per LOT
                - Bank Nifty: 35 (lot_size × ₹1/point/unit)
                - Gold Mini: 10 (₹10 per ₹1 move, since quoted per 10g but contract is 100g)

        Returns:
            Risk in Rs = risk_points × lots × point_value
        """
        risk_points = max(0, self.entry_price - self.current_stop)
        return risk_points * self.lots * point_value

    def calculate_pnl(self, current_price: float, point_value: float) -> float:
        """
        Calculate unrealized P&L

        Args:
            current_price: Current market price
            point_value: Rs per point per LOT
                - Bank Nifty: 35 (lot_size × ₹1/point/unit)
                - Gold Mini: 10 (₹10 per ₹1 move, since quoted per 10g but contract is 100g)

        Returns:
            P&L in Rs = price_diff × lots × point_value
        """
        price_diff = current_price - self.entry_price
        return price_diff * self.lots * point_value
    
    def update_stop(self, new_stop: float) -> bool:
        """Update trailing stop (only moves up for long positions)"""
        if new_stop > self.current_stop:
            self.current_stop = new_stop
            return True
        return False

@dataclass
class PortfolioState:
    """Current state of the portfolio"""
    timestamp: datetime
    equity: float  # Current total equity
    closed_equity: float  # Cash + realized P&L
    open_equity: float  # Closed + unrealized P&L
    blended_equity: float  # Closed + 50% unrealized
    
    positions: Dict[str, Position] = field(default_factory=dict)
    
    # Risk metrics
    total_risk_amount: float = 0.0
    total_risk_percent: float = 0.0
    gold_risk_percent: float = 0.0
    banknifty_risk_percent: float = 0.0
    
    # Volatility metrics
    total_vol_amount: float = 0.0
    total_vol_percent: float = 0.0
    gold_vol_percent: float = 0.0
    banknifty_vol_percent: float = 0.0
    
    # Margin metrics
    margin_used: float = 0.0
    margin_available: float = 0.0
    margin_utilization_percent: float = 0.0
    
    def get_open_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return {k: v for k, v in self.positions.items() if v.status == "open"}
    
    def get_positions_for_instrument(self, instrument: str) -> Dict[str, Position]:
        """Get positions for specific instrument"""
        return {k: v for k, v in self.get_open_positions().items() 
                if v.instrument == instrument}
    
    def position_count(self) -> int:
        """Count open positions"""
        return len(self.get_open_positions())
    
    def instrument_position_count(self, instrument: str) -> int:
        """Count positions for specific instrument"""
        return len(self.get_positions_for_instrument(instrument))

@dataclass
class TomBassoConstraints:
    """Tom Basso 3-constraint sizing results"""
    lot_r: float  # Risk-based lots
    lot_v: float  # Volatility-based lots
    lot_m: float  # Margin-based lots
    final_lots: int  # MIN(lot_r, lot_v, lot_m) floored
    limiter: str  # Which constraint limited: 'risk', 'volatility', or 'margin'
    
    def __str__(self):
        return (f"Lot-R: {self.lot_r:.2f}, Lot-V: {self.lot_v:.2f}, "
                f"Lot-M: {self.lot_m:.2f} → Final: {self.final_lots} "
                f"(limited by {self.limiter})")

@dataclass
class PyramidGateCheck:
    """Result of pyramid gate checks"""
    allowed: bool
    instrument_gate: bool
    portfolio_gate: bool
    profit_gate: bool
    reason: str
    
    # Details
    price_move_r: float = 0.0
    atr_spacing: float = 0.0
    portfolio_risk_pct: float = 0.0
    portfolio_vol_pct: float = 0.0

