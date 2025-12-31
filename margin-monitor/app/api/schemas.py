"""
Margin Monitor - Pydantic Schemas for API
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================
# Request Schemas
# ============================================================

class ConfigRequest(BaseModel):
    """Request to set daily configuration."""
    index_name: str = Field(..., pattern="^(NIFTY|SENSEX)$", description="Index to trade")
    expiry_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Expiry date (YYYY-MM-DD)")
    num_baskets: int = Field(..., ge=1, le=50, description="Number of baskets")
    budget_per_basket: Optional[float] = Field(1000000.0, ge=100000, description="Budget per basket")


class ManualBaselineRequest(BaseModel):
    """Request to manually set baseline."""
    baseline_margin: float = Field(..., ge=0, description="Baseline margin amount")
    reason: Optional[str] = Field(None, description="Reason for manual override")


class BaselineRequest(BaseModel):
    """Request to capture baseline (optional config_id)."""
    config_id: Optional[int] = Field(None, description="Config ID (uses today if not provided)")


# ============================================================
# Response Schemas - Config
# ============================================================

class ConfigResponse(BaseModel):
    """Daily configuration response."""
    id: int
    date: str
    day_of_week: int
    day_name: str
    index_name: str
    expiry_date: str
    num_baskets: int
    budget_per_basket: float
    total_budget: float
    baseline_margin: Optional[float]
    baseline_captured_at: Optional[str]


class ConfigCreateResponse(BaseModel):
    """Response after creating config."""
    success: bool
    config: ConfigResponse


class BaselineCaptureResponse(BaseModel):
    """Response after capturing baseline."""
    success: bool
    baseline_margin: float
    captured_at: str
    manual: bool = False


# ============================================================
# Response Schemas - Margin
# ============================================================

class MarginData(BaseModel):
    """Current margin data."""
    total_used: float
    baseline: float
    intraday_used: float
    available_cash: float
    collateral: float
    utilization_pct: float
    budget_remaining: float


class PositionSummary(BaseModel):
    """Position summary data."""
    short_count: int
    short_qty: int
    long_count: int
    long_qty: int
    closed_count: int
    hedge_cost: float
    total_pnl: float


class M2MData(BaseModel):
    """Mark-to-market data."""
    realized: float
    unrealized: float


class CurrentMarginResponse(BaseModel):
    """Response for current margin status."""
    success: bool
    timestamp: str
    config: ConfigResponse
    margin: MarginData
    positions: PositionSummary
    m2m: M2MData


# ============================================================
# Response Schemas - Positions
# ============================================================

class PositionData(BaseModel):
    """Individual position data."""
    symbol: str
    quantity: int
    average_price: float
    ltp: float
    pnl: float
    strike: Optional[int]
    option_type: Optional[str]


class ExcludedPosition(BaseModel):
    """Excluded position with reason."""
    symbol: str
    quantity: int
    reason: str


class PositionsFilter(BaseModel):
    """Filter applied to positions."""
    index: str
    expiry: str


class PositionsSummary(BaseModel):
    """Summary of filtered positions."""
    short_count: int
    short_qty: int
    short_pnl: float
    long_count: int
    long_qty: int
    long_pnl: float
    hedge_cost: float
    closed_count: int
    closed_pnl: float
    total_pnl: float


class PositionsResponse(BaseModel):
    """Response for positions endpoint."""
    success: bool
    timestamp: str
    filter: PositionsFilter
    short_positions: List[PositionData]
    long_positions: List[PositionData]
    closed_positions: List[PositionData]
    excluded_positions: List[ExcludedPosition]
    summary: PositionsSummary


# ============================================================
# Response Schemas - History
# ============================================================

class HistorySnapshot(BaseModel):
    """Single snapshot for history."""
    timestamp: str
    intraday_margin: float
    utilization_pct: float
    short_count: int
    long_count: int
    hedge_cost: float
    total_pnl: float


class HistoryConfig(BaseModel):
    """Config info for history."""
    day_name: str
    index_name: str
    num_baskets: int
    total_budget: float
    baseline_margin: float


class HistoryResponse(BaseModel):
    """Response for history endpoint."""
    success: bool
    date: str
    config: HistoryConfig
    snapshots: List[HistorySnapshot]


# ============================================================
# Response Schemas - Summary
# ============================================================

class DailySummaryData(BaseModel):
    """Daily summary data."""
    date: str
    day_name: str
    index_name: str
    num_baskets: int
    max_utilization_pct: float
    total_hedge_cost: float
    total_pnl: float


class SummaryResponse(BaseModel):
    """Response for summary endpoint."""
    success: bool
    summaries: List[DailySummaryData]


# ============================================================
# Response Schemas - Analytics
# ============================================================

class DayOfWeekAnalytics(BaseModel):
    """Analytics for a specific day of week."""
    day_name: str
    index_name: str
    trading_days: int
    avg_max_utilization: float
    avg_hedge_cost: float
    avg_pnl: float


class AnalyticsResponse(BaseModel):
    """Response for analytics endpoint."""
    success: bool
    period_days: int
    by_day_of_week: List[DayOfWeekAnalytics]


# ============================================================
# Response Schemas - Snapshot
# ============================================================

class SnapshotCaptureResponse(BaseModel):
    """Response after manually capturing a snapshot."""
    success: bool
    snapshot_id: int
    utilization_pct: float


# ============================================================
# Market Status Response
# ============================================================

class MarketStatusResponse(BaseModel):
    """Market status and session information."""
    success: bool = True
    timestamp: str

    # Market timing
    is_open: bool
    is_pre_market: bool
    is_post_market: bool
    is_weekend: bool
    session_status: str  # 'pre_market', 'open', 'closed', 'weekend'
    next_event: str
    market_open_time: str
    market_close_time: str

    # Session state
    has_config: bool
    has_baseline: bool
    has_eod_summary: bool
    session_complete: bool  # True if market closed AND EOD summary exists


class EODSummaryResponse(BaseModel):
    """Today's EOD summary if available."""
    date: str
    day_name: str
    index_name: str
    num_baskets: int
    total_budget: float
    baseline_margin: float
    max_intraday_margin: float
    max_utilization_pct: float
    avg_utilization_pct: Optional[float]
    total_hedge_cost: float
    total_pnl: float
    max_short_count: int
    max_long_count: int
    total_closed_count: int
    snapshot_count: int
    first_snapshot_time: Optional[str]
    last_snapshot_time: Optional[str]


class TodayStatusResponse(BaseModel):
    """Full status response including market status and EOD summary."""
    success: bool = True
    timestamp: str
    market: MarketStatusResponse
    eod_summary: Optional[EODSummaryResponse] = None


# ============================================================
# Error Response
# ============================================================

class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None
