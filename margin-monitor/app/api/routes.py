"""
Margin Monitor - API Routes

All REST endpoints for the margin monitor.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.db_models import DailyConfig, MarginSnapshot
from app.services.margin_service import margin_service
from app.services.position_service import position_service
from app.services.openalgo_service import openalgo_service, OpenAlgoError
from app.services.analytics_service import analytics_service
from app.utils.date_utils import today_ist, get_day_of_week, get_day_name, now_ist, format_datetime_ist
from app.api.schemas import (
    ConfigRequest, ConfigCreateResponse, ConfigResponse,
    BaselineRequest, ManualBaselineRequest, BaselineCaptureResponse,
    CurrentMarginResponse, MarginData, PositionSummary, M2MData,
    PositionsResponse, PositionsFilter, PositionData, ExcludedPosition, PositionsSummary,
    HistoryResponse, HistoryConfig, HistorySnapshot,
    SummaryResponse, DailySummaryData,
    AnalyticsResponse, DayOfWeekAnalytics,
    SnapshotCaptureResponse,
    ErrorResponse,
)

router = APIRouter()


# ============================================================
# Helper Functions
# ============================================================

def config_to_response(config: DailyConfig) -> ConfigResponse:
    """Convert DailyConfig model to ConfigResponse schema."""
    return ConfigResponse(
        id=config.id,
        date=config.date.strftime('%Y-%m-%d'),
        day_of_week=config.day_of_week,
        day_name=config.day_name,
        index_name=config.index_name,
        expiry_date=config.expiry_date.strftime('%Y-%m-%d'),
        num_baskets=config.num_baskets,
        budget_per_basket=config.budget_per_basket,
        total_budget=config.total_budget,
        baseline_margin=config.baseline_margin,
        baseline_captured_at=format_datetime_ist(config.baseline_captured_at) if config.baseline_captured_at else None,
    )


# ============================================================
# Configuration Endpoints
# ============================================================

@router.post("/config", response_model=ConfigCreateResponse)
async def set_daily_config(
    request: ConfigRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set daily configuration for margin monitoring.

    Creates or updates the configuration for today's trading day.
    """
    today = today_ist()

    # Check if config exists for today
    result = await db.execute(
        select(DailyConfig).where(DailyConfig.date == today)
    )
    config = result.scalar_one_or_none()

    # Parse expiry date
    try:
        expiry = datetime.strptime(request.expiry_date, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(400, "Invalid expiry_date format")

    total_budget = request.num_baskets * request.budget_per_basket

    if config:
        # Update existing
        config.index_name = request.index_name
        config.expiry_date = expiry
        config.num_baskets = request.num_baskets
        config.budget_per_basket = request.budget_per_basket
        config.total_budget = total_budget
        config.updated_at = datetime.utcnow()
    else:
        # Create new
        config = DailyConfig(
            date=today,
            day_of_week=get_day_of_week(today),
            day_name=get_day_name(today),
            index_name=request.index_name,
            expiry_date=expiry,
            num_baskets=request.num_baskets,
            budget_per_basket=request.budget_per_basket,
            total_budget=total_budget,
        )
        db.add(config)

    try:
        await db.commit()
        await db.refresh(config)
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Database error: {e}")

    return ConfigCreateResponse(
        success=True,
        config=config_to_response(config)
    )


@router.get("/config", response_model=ConfigResponse)
async def get_daily_config(
    config_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), defaults to today"),
    db: AsyncSession = Depends(get_db)
):
    """Get configuration for a specific date (defaults to today)."""
    if config_date:
        try:
            target_date = datetime.strptime(config_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(400, "Invalid date format")
    else:
        target_date = today_ist()

    result = await db.execute(
        select(DailyConfig).where(DailyConfig.date == target_date)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, f"No configuration for {target_date}")

    return config_to_response(config)


# ============================================================
# Baseline Endpoints
# ============================================================

@router.post("/baseline", response_model=BaselineCaptureResponse)
async def capture_baseline(
    request: Optional[BaselineRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Capture baseline margin from OpenAlgo.

    Uses today's config if config_id not provided.
    """
    # Get config
    if request and request.config_id:
        result = await db.execute(
            select(DailyConfig).where(DailyConfig.id == request.config_id)
        )
        config = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(DailyConfig).where(DailyConfig.date == today_ist())
        )
        config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, "No configuration found")

    try:
        funds = await openalgo_service.get_funds()
        baseline = funds['used_margin']

        config.baseline_margin = baseline
        config.baseline_captured_at = now_ist()
        config.baseline_manual = False

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Database error: {e}")

        return BaselineCaptureResponse(
            success=True,
            baseline_margin=baseline,
            captured_at=format_datetime_ist(config.baseline_captured_at),
            manual=False,
        )

    except OpenAlgoError as e:
        raise HTTPException(503, f"OpenAlgo error: {e}")


@router.post("/baseline/manual", response_model=BaselineCaptureResponse)
async def set_manual_baseline(
    request: ManualBaselineRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually set baseline margin (override).

    Use this if automatic capture was missed.
    """
    result = await db.execute(
        select(DailyConfig).where(DailyConfig.date == today_ist())
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, "No configuration for today")

    config.baseline_margin = request.baseline_margin
    config.baseline_captured_at = now_ist()
    config.baseline_manual = True

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Database error: {e}")

    return BaselineCaptureResponse(
        success=True,
        baseline_margin=request.baseline_margin,
        captured_at=format_datetime_ist(config.baseline_captured_at),
        manual=True,
    )


# ============================================================
# Current Margin Endpoint
# ============================================================

@router.get("/current", response_model=CurrentMarginResponse)
async def get_current_margin(
    db: AsyncSession = Depends(get_db)
):
    """
    Get current margin status with live data from OpenAlgo.

    Returns margin utilization, positions, and M2M.
    """
    result = await db.execute(
        select(DailyConfig)
        .where(DailyConfig.date == today_ist())
        .where(DailyConfig.is_active == 1)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, "No configuration for today")

    if config.baseline_margin is None:
        raise HTTPException(400, "Baseline not captured yet")

    try:
        data = await margin_service.get_current_margin(config, db)

        return CurrentMarginResponse(
            success=True,
            timestamp=format_datetime_ist(now_ist()),
            config=config_to_response(config),
            margin=MarginData(**data['margin']),
            positions=PositionSummary(**data['positions']),
            m2m=M2MData(**data['m2m']),
        )

    except OpenAlgoError as e:
        raise HTTPException(503, f"OpenAlgo error: {e}")


# ============================================================
# Positions Endpoint
# ============================================================

@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    db: AsyncSession = Depends(get_db)
):
    """
    Get filtered positions for today's config.

    Positions are filtered by index and expiry, categorized as:
    - short_positions: qty < 0 (sold options)
    - long_positions: qty > 0 (hedges)
    - closed_positions: qty = 0 (exited)
    - excluded_positions: wrong index or expiry
    """
    result = await db.execute(
        select(DailyConfig)
        .where(DailyConfig.date == today_ist())
        .where(DailyConfig.is_active == 1)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, "No configuration for today")

    try:
        positions = await openalgo_service.get_positions()
        expiry_str = config.expiry_date.strftime('%Y-%m-%d')

        filtered = position_service.filter_positions(
            positions, config.index_name, expiry_str
        )
        summary = position_service.get_summary(filtered)

        return PositionsResponse(
            success=True,
            timestamp=format_datetime_ist(now_ist()),
            filter=PositionsFilter(index=config.index_name, expiry=expiry_str),
            short_positions=[
                PositionData(
                    symbol=p['symbol'],
                    quantity=p['quantity'],
                    average_price=p['average_price'],
                    ltp=p['ltp'],
                    pnl=p['pnl'],
                    strike=p.get('strike'),
                    option_type=p.get('option_type'),
                )
                for p in filtered['short_positions']
            ],
            long_positions=[
                PositionData(
                    symbol=p['symbol'],
                    quantity=p['quantity'],
                    average_price=p['average_price'],
                    ltp=p['ltp'],
                    pnl=p['pnl'],
                    strike=p.get('strike'),
                    option_type=p.get('option_type'),
                )
                for p in filtered['long_positions']
            ],
            closed_positions=[
                PositionData(
                    symbol=p['symbol'],
                    quantity=p['quantity'],
                    average_price=p['average_price'],
                    ltp=p['ltp'],
                    pnl=p['pnl'],
                    strike=p.get('strike'),
                    option_type=p.get('option_type'),
                )
                for p in filtered['closed_positions']
            ],
            excluded_positions=[
                ExcludedPosition(
                    symbol=p['symbol'],
                    quantity=p['quantity'],
                    reason=p['reason'],
                )
                for p in filtered['excluded_positions']
            ],
            summary=PositionsSummary(**summary),
        )

    except OpenAlgoError as e:
        raise HTTPException(503, f"OpenAlgo error: {e}")


# ============================================================
# History Endpoint
# ============================================================

@router.get("/history", response_model=HistoryResponse)
async def get_history(
    history_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), defaults to today"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get day's snapshots for charting.

    Returns all 5-minute snapshots for the specified date.
    """
    if history_date:
        try:
            target_date = datetime.strptime(history_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(400, "Invalid date format")
    else:
        target_date = today_ist()

    # Get config
    result = await db.execute(
        select(DailyConfig).where(DailyConfig.date == target_date)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, f"No configuration for {target_date}")

    # Get snapshots
    result = await db.execute(
        select(MarginSnapshot)
        .where(MarginSnapshot.config_id == config.id)
        .where(MarginSnapshot.error_message.is_(None))
        .order_by(MarginSnapshot.timestamp)
    )
    snapshots = result.scalars().all()

    return HistoryResponse(
        success=True,
        date=target_date.strftime('%Y-%m-%d'),
        config=HistoryConfig(
            day_name=config.day_name,
            index_name=config.index_name,
            num_baskets=config.num_baskets,
            total_budget=config.total_budget,
            baseline_margin=config.baseline_margin or 0,
        ),
        snapshots=[
            HistorySnapshot(
                timestamp=format_datetime_ist(s.timestamp),
                intraday_margin=s.intraday_margin,
                utilization_pct=s.utilization_pct,
                short_count=s.short_positions_count,
                long_count=s.long_positions_count,
                hedge_cost=s.total_hedge_cost,
                total_pnl=s.total_pnl,
            )
            for s in snapshots
        ],
    )


# ============================================================
# Summary Endpoint
# ============================================================

@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get daily summaries for a date range.

    Defaults to last 30 days if dates not provided.
    """
    from datetime import timedelta

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(400, "Invalid end_date format")
    else:
        end_dt = today_ist()

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(400, "Invalid start_date format")
    else:
        start_dt = end_dt - timedelta(days=30)

    summaries = await analytics_service.get_date_range_summaries(db, start_dt, end_dt)

    return SummaryResponse(
        success=True,
        summaries=[DailySummaryData(**s) for s in summaries],
    )


# ============================================================
# Analytics Endpoint
# ============================================================

@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    period: int = Query(30, ge=7, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get day-of-week analytics.

    Returns average max utilization, hedge cost, and P&L by day of week.
    """
    analytics = await analytics_service.get_day_of_week_analytics(db, period)

    return AnalyticsResponse(
        success=True,
        period_days=period,
        by_day_of_week=[DayOfWeekAnalytics(**a) for a in analytics],
    )


# ============================================================
# Capture Snapshot (Manual Trigger)
# ============================================================

@router.post("/snapshot", response_model=SnapshotCaptureResponse)
async def capture_snapshot(
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a margin snapshot capture.

    Useful for testing or ad-hoc captures.
    """
    result = await db.execute(
        select(DailyConfig)
        .where(DailyConfig.date == today_ist())
        .where(DailyConfig.is_active == 1)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(404, "No configuration for today")

    if config.baseline_margin is None:
        raise HTTPException(400, "Baseline not captured yet")

    snapshot = await margin_service.capture_snapshot(config, db)

    if snapshot:
        return SnapshotCaptureResponse(
            success=True,
            snapshot_id=snapshot.id,
            utilization_pct=snapshot.utilization_pct,
        )
    else:
        raise HTTPException(500, "Failed to capture snapshot")
