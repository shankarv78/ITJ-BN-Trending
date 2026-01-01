"""
Auto-Hedge System - Database Models (SQLAlchemy ORM)

Schema: auto_hedge

Tables:
- strategy_schedule: Defines when each portfolio enters
- daily_session: Daily configuration (index, baskets, budget)
- hedge_transactions: Audit log of all hedge actions
- strategy_executions: Tracks each strategy's margin state
- active_hedges: Currently held hedge positions
"""

from datetime import datetime, date, time
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Time, Text,
    ForeignKey, Index, Boolean, Enum as SQLEnum, Numeric
)
from sqlalchemy.orm import relationship
from app.database import Base

# Schema for auto-hedge tables
HEDGE_SCHEMA = "auto_hedge"


# ============================================================
# Enums
# ============================================================

class DayOfWeek(str, Enum):
    """Trading days of the week."""
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"


class IndexName(str, Enum):
    """Supported indices."""
    NIFTY = "NIFTY"
    SENSEX = "SENSEX"


class ExpiryType(str, Enum):
    """Option expiry types."""
    ZERO_DTE = "0DTE"
    ONE_DTE = "1DTE"
    TWO_DTE = "2DTE"


class HedgeAction(str, Enum):
    """Hedge transaction action types."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order execution status."""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerReason(str, Enum):
    """Reason for hedge action."""
    PRE_STRATEGY = "PRE_STRATEGY"
    EXCESS_MARGIN = "EXCESS_MARGIN"
    MANUAL = "MANUAL"
    EOD_EXIT = "EOD_EXIT"


class ExitReason(str, Enum):
    """Strategy exit reason."""
    TIMED = "TIMED"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"
    MANUAL = "MANUAL"


# ============================================================
# Models
# ============================================================

class StrategySchedule(Base):
    """
    Strategy schedule configuration.
    Defines when each portfolio enters and exits for each day of week.
    """
    __tablename__ = 'strategy_schedule'
    __table_args__ = (
        Index('idx_strategy_schedule_day', 'day_of_week'),
        Index('idx_strategy_schedule_active', 'is_active'),
        {'schema': HEDGE_SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Schedule definition
    day_of_week = Column(String(10), nullable=False)  # Monday, Tuesday, etc.
    index_name = Column(String(10), nullable=False)   # NIFTY, SENSEX
    expiry_type = Column(String(10), nullable=False)  # 0DTE, 1DTE, 2DTE
    portfolio_name = Column(String(50), nullable=False)
    entry_time = Column(Time, nullable=False)
    exit_time = Column(Time, nullable=True)  # NULL = expire worthless

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class DailySession(Base):
    """
    Daily session configuration.
    One record per trading day with index, basket count, and budget.
    """
    __tablename__ = 'daily_session'
    __table_args__ = (
        Index('idx_daily_session_date', 'session_date'),
        {'schema': HEDGE_SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_date = Column(Date, nullable=False, unique=True)

    # Day configuration
    day_of_week = Column(String(10), nullable=False)
    index_name = Column(String(10), nullable=False)
    expiry_type = Column(String(10), nullable=False)
    expiry_date = Column(Date, nullable=False)

    # Portfolio configuration
    num_baskets = Column(Integer, nullable=False)
    budget_per_basket = Column(Numeric(12, 2), default=1000000.00)
    total_budget = Column(Numeric(14, 2), nullable=False)  # Calculated: num_baskets × budget_per_basket

    # Baseline (from margin monitor)
    baseline_margin = Column(Numeric(14, 2), nullable=True)
    baseline_captured_at = Column(DateTime(timezone=True), nullable=True)

    # Auto-hedge toggle
    auto_hedge_enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    hedge_transactions = relationship("HedgeTransaction", back_populates="session")
    strategy_executions = relationship("StrategyExecution", back_populates="session")
    active_hedges = relationship("ActiveHedge", back_populates="session")


class HedgeTransaction(Base):
    """
    Hedge transaction log.
    Records every hedge buy/sell action with full audit trail.
    """
    __tablename__ = 'hedge_transactions'
    __table_args__ = (
        Index('idx_hedge_transactions_session', 'session_id'),
        Index('idx_hedge_transactions_timestamp', 'timestamp'),
        Index('idx_hedge_transactions_status', 'order_status'),
        {'schema': HEDGE_SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.daily_session.id'), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Action details
    action = Column(String(10), nullable=False)  # BUY, SELL
    trigger_reason = Column(String(100), nullable=False)  # PRE_STRATEGY:ITJ_NF_EXP_4, EXCESS_MARGIN, MANUAL

    # Position details
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(10), nullable=False)  # NFO, BFO
    strike = Column(Integer, nullable=False)
    option_type = Column(String(2), nullable=False)  # CE, PE
    quantity = Column(Integer, nullable=False)
    lots = Column(Integer, nullable=False)

    # Pricing
    order_price = Column(Numeric(10, 2), nullable=False)
    executed_price = Column(Numeric(10, 2), nullable=True)
    total_cost = Column(Numeric(12, 2), nullable=True)

    # Margin impact
    utilization_before = Column(Numeric(5, 2), nullable=False)
    utilization_after = Column(Numeric(5, 2), nullable=True)
    margin_impact = Column(Numeric(14, 2), nullable=True)  # Positive = margin freed

    # Execution
    order_id = Column(String(50), nullable=True)
    order_status = Column(String(20), nullable=False, default='PENDING')  # PENDING, SUCCESS, FAILED, CANCELLED
    error_message = Column(Text, nullable=True)

    # Alerts
    telegram_sent = Column(Boolean, default=False)
    telegram_message_id = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    session = relationship("DailySession", back_populates="hedge_transactions")


class StrategyExecution(Base):
    """
    Strategy execution tracking.
    Records pre/post entry margin state for each scheduled strategy.
    """
    __tablename__ = 'strategy_executions'
    __table_args__ = (
        Index('idx_strategy_executions_session', 'session_id'),
        Index('idx_strategy_executions_portfolio', 'portfolio_name'),
        {'schema': HEDGE_SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.daily_session.id'), nullable=False)
    portfolio_name = Column(String(50), nullable=False)
    scheduled_entry_time = Column(Time, nullable=False)

    # Pre-entry state
    utilization_before = Column(Numeric(5, 2), nullable=True)
    projected_utilization = Column(Numeric(5, 2), nullable=True)
    hedge_required = Column(Boolean, default=False)
    hedge_transaction_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.hedge_transactions.id'), nullable=True)

    # Post-entry state
    actual_entry_time = Column(DateTime(timezone=True), nullable=True)
    utilization_after = Column(Numeric(5, 2), nullable=True)
    entry_successful = Column(Boolean, nullable=True)

    # Exit tracking
    scheduled_exit_time = Column(Time, nullable=True)
    actual_exit_time = Column(DateTime(timezone=True), nullable=True)
    exit_reason = Column(String(20), nullable=True)  # TIMED, SL_HIT, EXPIRED, MANUAL

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("DailySession", back_populates="strategy_executions")
    hedge_transaction = relationship("HedgeTransaction")


class ActiveHedge(Base):
    """
    Active hedge positions.
    Tracks currently held hedges for the session.
    """
    __tablename__ = 'active_hedges'
    __table_args__ = (
        Index('idx_active_hedges_session', 'session_id', 'is_active'),
        Index('idx_active_hedges_symbol', 'symbol'),
        {'schema': HEDGE_SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.daily_session.id'), nullable=False)
    transaction_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.hedge_transactions.id'), nullable=False)

    # Position details
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(10), nullable=False)
    strike = Column(Integer, nullable=False)
    option_type = Column(String(2), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(10, 2), nullable=False)
    current_price = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    exit_transaction_id = Column(Integer, ForeignKey(f'{HEDGE_SCHEMA}.hedge_transactions.id'), nullable=True)

    # Calculated fields
    otm_distance = Column(Integer, nullable=True)  # Points from ATM at entry
    margin_benefit = Column(Numeric(14, 2), nullable=True)  # Estimated margin reduction

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("DailySession", back_populates="active_hedges")
    entry_transaction = relationship("HedgeTransaction", foreign_keys=[transaction_id])
    exit_transaction = relationship("HedgeTransaction", foreign_keys=[exit_transaction_id])
