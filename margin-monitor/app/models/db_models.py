"""
Margin Monitor - Database Models (SQLAlchemy ORM)
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Text, ForeignKey,
    Index, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import settings

# Schema prefix for all tables
SCHEMA = settings.mm_schema


class DailyConfig(Base):
    """Daily configuration - one per trading day."""

    __tablename__ = 'daily_config'
    __table_args__ = {'schema': SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Mon, 4=Fri
    day_name = Column(String(20), nullable=False)  # 'Monday', etc.

    # Trading configuration
    index_name = Column(String(20), nullable=False)  # 'NIFTY' or 'SENSEX'
    expiry_date = Column(Date, nullable=False)
    num_baskets = Column(Integer, nullable=False)
    budget_per_basket = Column(Float, default=1000000.0)  # ₹10L
    total_budget = Column(Float, nullable=False)  # num_baskets × budget

    # Baseline
    baseline_margin = Column(Float, nullable=True)
    baseline_captured_at = Column(DateTime(timezone=True), nullable=True)
    baseline_manual = Column(Boolean, default=False)

    # Status
    is_active = Column(Integer, default=1)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    snapshots = relationship("MarginSnapshot", back_populates="config")
    summary = relationship("DailySummary", back_populates="config", uselist=False)


class MarginSnapshot(Base):
    """5-minute margin snapshots."""

    __tablename__ = 'margin_snapshots'
    __table_args__ = (
        Index('idx_margin_snapshots_config_time', 'config_id', 'timestamp'),
        Index('idx_margin_snapshots_timestamp', 'timestamp'),  # For time-range queries
        {'schema': SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey(f'{SCHEMA}.daily_config.id'), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # From OpenAlgo funds API
    total_margin_used = Column(Float, nullable=False)  # utiliseddebits
    available_cash = Column(Float, nullable=False)  # availablecash
    collateral = Column(Float, nullable=False)  # collateral
    m2m_realized = Column(Float, default=0.0)  # m2mrealized
    m2m_unrealized = Column(Float, default=0.0)  # m2munrealized

    # Calculated values
    baseline_margin = Column(Float, nullable=False)
    intraday_margin = Column(Float, nullable=False)  # total_margin_used - baseline
    utilization_pct = Column(Float, nullable=False)  # (intraday / budget) × 100

    # Position summary
    short_positions_count = Column(Integer, default=0)
    short_positions_qty = Column(Integer, default=0)
    long_positions_count = Column(Integer, default=0)
    long_positions_qty = Column(Integer, default=0)
    closed_positions_count = Column(Integer, default=0)
    total_hedge_cost = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    config = relationship("DailyConfig", back_populates="snapshots")
    positions = relationship("PositionSnapshot", back_populates="snapshot")


class PositionSnapshot(Base):
    """Position details at each snapshot."""

    __tablename__ = 'position_snapshots'
    __table_args__ = (
        Index('idx_position_snapshots_snapshot', 'snapshot_id'),
        {'schema': SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey(f'{SCHEMA}.margin_snapshots.id'), nullable=False)

    # Position data from OpenAlgo
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(10), nullable=False)  # NFO, BFO
    product = Column(String(10), nullable=False)  # NRML
    quantity = Column(Integer, nullable=False)
    average_price = Column(Float, nullable=False)
    ltp = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)

    # Parsed from symbol
    position_type = Column(String(10), nullable=False)  # 'SHORT', 'LONG', 'CLOSED'
    option_type = Column(String(2), nullable=False)  # 'CE' or 'PE'
    strike_price = Column(Integer, nullable=False)
    expiry_date = Column(Date, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    snapshot = relationship("MarginSnapshot", back_populates="positions")


class DailySummary(Base):
    """Daily summary - generated at EOD."""

    __tablename__ = 'daily_summary'
    __table_args__ = (
        Index('idx_daily_summary_date', 'date'),
        Index('idx_daily_summary_day_of_week', 'day_of_week'),
        {'schema': SCHEMA}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey(f'{SCHEMA}.daily_config.id'), nullable=False, unique=True)

    # Day info
    date = Column(Date, nullable=False)
    day_of_week = Column(Integer, nullable=False)
    day_name = Column(String(20), nullable=False)
    index_name = Column(String(20), nullable=False)
    num_baskets = Column(Integer, nullable=False)
    total_budget = Column(Float, nullable=False)

    # Margin metrics
    baseline_margin = Column(Float, nullable=False)
    max_intraday_margin = Column(Float, nullable=False)
    max_utilization_pct = Column(Float, nullable=False)
    avg_utilization_pct = Column(Float, nullable=True)

    # Hedge metrics
    total_hedge_cost = Column(Float, default=0.0)
    max_hedge_count = Column(Integer, default=0)

    # Position metrics
    max_short_count = Column(Integer, default=0)
    max_long_count = Column(Integer, default=0)
    total_closed_count = Column(Integer, default=0)  # SL hits

    # P&L
    total_pnl = Column(Float, default=0.0)

    # Timestamps
    first_position_time = Column(DateTime(timezone=True), nullable=True)
    last_position_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    config = relationship("DailyConfig", back_populates="summary")
