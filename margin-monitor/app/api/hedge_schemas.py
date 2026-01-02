"""
Auto-Hedge System - API Schemas (Pydantic Models)

Request and response schemas for hedge API endpoints.
"""

from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================
# Schedule Schemas
# ============================================================

class StrategyEntrySchema(BaseModel):
    """Schema for a single strategy entry."""
    portfolio_name: str
    entry_time: str  # HH:MM:SS
    exit_time: Optional[str] = None  # HH:MM:SS or null


class ScheduleCreateRequest(BaseModel):
    """Request to create/update schedule for a day."""
    day_of_week: str = Field(..., description="Monday, Tuesday, etc.")
    index_name: str = Field(..., description="NIFTY or SENSEX")
    expiry_type: str = Field(..., description="0DTE, 1DTE, or 2DTE")
    entries: List[StrategyEntrySchema]


class ScheduleResponse(BaseModel):
    """Response with schedule for a day."""
    day_of_week: str
    index_name: str
    expiry_type: str
    entries: List[StrategyEntrySchema]
    total_entries: int


# ============================================================
# Session Schemas
# ============================================================

class SessionCreateRequest(BaseModel):
    """Request to create/update daily session."""
    session_date: date
    index_name: str
    expiry_type: str
    expiry_date: date
    num_baskets: int
    budget_per_basket: float = 1000000.0
    auto_hedge_enabled: bool = True


class SessionResponse(BaseModel):
    """Response with session details."""
    id: int
    session_date: date
    day_of_week: str
    index_name: str
    expiry_type: str
    expiry_date: date
    num_baskets: int
    budget_per_basket: float
    total_budget: float
    baseline_margin: Optional[float]
    auto_hedge_enabled: bool
    created_at: datetime


# ============================================================
# Status Schemas
# ============================================================

class ActiveHedgeSchema(BaseModel):
    """Schema for an active hedge."""
    id: int
    symbol: str
    strike: int
    option_type: str
    quantity: int
    entry_price: float
    otm_distance: Optional[int]


class NextEntrySchema(BaseModel):
    """Schema for next scheduled entry."""
    portfolio: str
    entry_time: str
    seconds_until: int


class SimulatedHedgeSchema(BaseModel):
    """Schema for a simulated hedge in dry run mode."""
    strike: int
    option_type: str
    margin_benefit: float
    timestamp: str


class SimulatedMarginSchema(BaseModel):
    """Schema for simulated margin info in dry run mode."""
    total_reduction: float = Field(..., description="Total simulated margin reduction in ₹")
    max_reduction: float = Field(0, description="Maximum allowed reduction (75% floor)")
    hedge_count: int = Field(..., description="Number of simulated hedges placed")
    ce_hedge_count: int = Field(0, description="Number of CE hedges")
    pe_hedge_count: int = Field(0, description="Number of PE hedges")
    ce_hedge_qty: int = Field(0, description="Total CE hedge quantity")
    pe_hedge_qty: int = Field(0, description="Total PE hedge quantity")
    real_utilization_pct: float = Field(0, description="Real margin utilization %")
    simulated_utilization_pct: float = Field(0, description="Simulated margin utilization % after hedges")
    hedges: List[SimulatedHedgeSchema] = Field(default=[], description="Recent simulated hedges")


class HedgeCapacitySchema(BaseModel):
    """Schema for hedge capacity limits - prevents over-hedging."""
    remaining_ce_capacity: int = Field(..., description="Remaining CE qty that can be hedged")
    remaining_pe_capacity: int = Field(..., description="Remaining PE qty that can be hedged")
    short_ce_qty: int = Field(..., description="Total CE options sold")
    short_pe_qty: int = Field(..., description="Total PE options sold")
    long_ce_qty: int = Field(..., description="Current CE hedges held")
    long_pe_qty: int = Field(..., description="Current PE hedges held")
    is_fully_hedged: bool = Field(..., description="True if no more hedges can provide benefit")


class HedgeStatusResponse(BaseModel):
    """Response with current auto-hedge status."""
    status: str = Field(..., description="running, stopped, disabled, no_session")
    dry_run: bool = False
    session: Optional[SessionResponse] = None
    active_hedges: List[ActiveHedgeSchema] = []
    next_entry: Optional[NextEntrySchema] = None
    cooldown_remaining: int = 0
    simulated_margin: Optional[SimulatedMarginSchema] = Field(None, description="Simulated margin info (dry run only)")
    hedge_capacity: Optional[HedgeCapacitySchema] = Field(None, description="Current hedge capacity limits")


# ============================================================
# Transaction Schemas
# ============================================================

class HedgeTransactionSchema(BaseModel):
    """Schema for a hedge transaction."""
    id: int
    timestamp: datetime
    action: str  # BUY or SELL
    trigger_reason: str
    symbol: str
    exchange: str
    strike: int
    option_type: str
    quantity: int
    lots: int
    order_price: float
    executed_price: Optional[float]
    total_cost: Optional[float]
    utilization_before: float
    utilization_after: Optional[float]
    margin_impact: Optional[float]
    order_id: Optional[str]
    order_status: str
    error_message: Optional[str]


class TransactionsResponse(BaseModel):
    """Response with transaction history."""
    session_date: date
    transactions: List[HedgeTransactionSchema]
    total_count: int
    total_cost: float
    total_recovered: float
    net_cost: float


# ============================================================
# Manual Action Schemas
# ============================================================

class ManualHedgeBuyRequest(BaseModel):
    """Request for manual hedge buy."""
    index_name: str = Field("NIFTY", description="Index name: NIFTY or SENSEX")
    expiry_date: str = Field(..., description="Expiry date in YYYY-MM-DD format")
    option_type: str = Field(..., description="CE or PE")
    strike_offset: int = Field(500, description="OTM distance in points")
    lots: int = Field(1, ge=1, le=50, description="Number of lots")
    reason: Optional[str] = Field(None, description="Reason for manual hedge")
    dry_run: bool = Field(True, description="Simulate without placing real order")


class ManualHedgeExitRequest(BaseModel):
    """Request for manual hedge exit."""
    hedge_id: int
    reason: Optional[str] = Field(None, description="Reason for exit")
    dry_run: bool = Field(True, description="Simulate without placing real order")


class ActionResponse(BaseModel):
    """Response for action requests."""
    success: bool
    message: str
    order_id: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False
    simulated_order: Optional[dict] = None  # Details of simulated order in dry run
    error: Optional[str] = None


# ============================================================
# Analytics Schemas
# ============================================================

class DailyAnalyticsSchema(BaseModel):
    """Analytics for a single day."""
    session_date: date
    day_of_week: str
    index_name: str
    num_baskets: int
    hedge_count: int
    total_cost: float
    total_recovered: float
    net_cost: float
    peak_utilization: float
    strategies_executed: int


class AnalyticsResponse(BaseModel):
    """Response with analytics data."""
    days: int
    data: List[DailyAnalyticsSchema]
    summary: dict


# ============================================================
# Toggle Schemas
# ============================================================

class ToggleRequest(BaseModel):
    """Request to toggle auto-hedge."""
    enabled: bool


class ToggleResponse(BaseModel):
    """Response for toggle request."""
    success: bool
    auto_hedge_enabled: bool
    message: str
