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


class HedgeStatusResponse(BaseModel):
    """Response with current auto-hedge status."""
    status: str = Field(..., description="running, stopped, disabled, no_session")
    dry_run: bool = False
    session: Optional[SessionResponse] = None
    active_hedges: List[ActiveHedgeSchema] = []
    next_entry: Optional[NextEntrySchema] = None
    cooldown_remaining: int = 0


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
    strike: int
    option_type: str = Field(..., description="CE or PE")


class ManualHedgeExitRequest(BaseModel):
    """Request for manual hedge exit."""
    hedge_id: int


class ActionResponse(BaseModel):
    """Response for action requests."""
    success: bool
    message: str
    order_id: Optional[str] = None
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
