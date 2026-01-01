"""
Auto-Hedge System - API Routes

REST API endpoints for managing and monitoring the auto-hedge system.
"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.hedge_models import (
    StrategySchedule, DailySession, HedgeTransaction,
    StrategyExecution, ActiveHedge
)
from app.models.hedge_constants import IndexName, ExpiryType, DAY_TO_INDEX_EXPIRY
from app.api.hedge_schemas import (
    ScheduleCreateRequest, ScheduleResponse, StrategyEntrySchema,
    SessionCreateRequest, SessionResponse,
    HedgeStatusResponse, ActiveHedgeSchema, NextEntrySchema,
    TransactionsResponse, HedgeTransactionSchema,
    ManualHedgeBuyRequest, ManualHedgeExitRequest, ActionResponse,
    AnalyticsResponse, DailyAnalyticsSchema,
    ToggleRequest, ToggleResponse
)
from app.services.strategy_scheduler import StrategySchedulerService
from app.services.hedge_orchestrator import AutoHedgeOrchestrator
from app.services.hedge_executor import HedgeExecutorService
from app.services.hedge_selector import HedgeStrikeSelectorService, HedgeCandidate
from app.services.margin_calculator import MarginCalculatorService

import pytz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hedge", tags=["Auto-Hedge"])

IST = pytz.timezone('Asia/Kolkata')

# Global orchestrator instance (set by main.py on startup)
_orchestrator: Optional[AutoHedgeOrchestrator] = None


def get_orchestrator() -> Optional[AutoHedgeOrchestrator]:
    """Get the global orchestrator instance."""
    return _orchestrator


def set_orchestrator(orchestrator: AutoHedgeOrchestrator):
    """Set the global orchestrator instance."""
    global _orchestrator
    _orchestrator = orchestrator


# ============================================================
# Status Endpoints
# ============================================================

@router.get("/status", response_model=HedgeStatusResponse)
async def get_hedge_status(db: AsyncSession = Depends(get_db)):
    """
    Get current auto-hedge status.

    Returns:
        Current status including session, active hedges, next entry
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        return HedgeStatusResponse(
            status="not_initialized",
            dry_run=False
        )

    status_data = await orchestrator.get_status()

    return HedgeStatusResponse(
        status="running" if status_data['is_running'] else "stopped",
        dry_run=status_data.get('dry_run', False),
        session=SessionResponse(**status_data['session']) if status_data.get('session') else None,
        active_hedges=[ActiveHedgeSchema(**h) for h in status_data.get('active_hedges', [])],
        next_entry=NextEntrySchema(**status_data['next_entry']) if status_data.get('next_entry') else None,
        cooldown_remaining=status_data.get('cooldown_remaining', 0)
    )


@router.post("/toggle", response_model=ToggleResponse)
async def toggle_auto_hedge(
    request: ToggleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enable or disable auto-hedge for today's session.

    Args:
        request: Toggle request with enabled flag

    Returns:
        Success status
    """
    today = datetime.now(IST).date()

    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(400, "No session found for today")

    session.auto_hedge_enabled = request.enabled
    await db.commit()

    status = "enabled" if request.enabled else "disabled"
    logger.info(f"[HEDGE_API] Auto-hedge {status} for {today}")

    return ToggleResponse(
        success=True,
        auto_hedge_enabled=request.enabled,
        message=f"Auto-hedge {status} for today's session"
    )


# ============================================================
# Schedule Endpoints
# ============================================================

@router.get("/schedule")
async def get_schedule(
    day: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get strategy schedule.

    Args:
        day: Optional day name (Monday, Tuesday, etc.). If not provided,
             returns today's schedule.

    Returns:
        Schedule for the specified day
    """
    if day is None:
        day = datetime.now(IST).strftime("%A")

    result = await db.execute(
        select(StrategySchedule)
        .where(StrategySchedule.day_of_week == day)
        .where(StrategySchedule.is_active == True)
        .order_by(StrategySchedule.entry_time)
    )
    schedules = result.scalars().all()

    if not schedules:
        return ScheduleResponse(
            day_of_week=day,
            index_name="",
            expiry_type="",
            entries=[],
            total_entries=0
        )

    entries = [
        StrategyEntrySchema(
            portfolio_name=s.portfolio_name,
            entry_time=s.entry_time.isoformat() if s.entry_time else "",
            exit_time=s.exit_time.isoformat() if s.exit_time else None
        )
        for s in schedules
    ]

    return ScheduleResponse(
        day_of_week=day,
        index_name=schedules[0].index_name,
        expiry_type=schedules[0].expiry_type,
        entries=entries,
        total_entries=len(entries)
    )


@router.put("/schedule")
async def update_schedule(
    request: ScheduleCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update strategy schedule for a day.

    Args:
        request: Schedule data with entries

    Returns:
        Updated schedule
    """
    # Delete existing entries for the day
    result = await db.execute(
        select(StrategySchedule)
        .where(StrategySchedule.day_of_week == request.day_of_week)
    )
    existing = result.scalars().all()
    for s in existing:
        await db.delete(s)

    # Insert new entries
    for entry in request.entries:
        schedule = StrategySchedule(
            day_of_week=request.day_of_week,
            index_name=request.index_name,
            expiry_type=request.expiry_type,
            portfolio_name=entry.portfolio_name,
            entry_time=datetime.strptime(entry.entry_time, "%H:%M:%S").time(),
            exit_time=datetime.strptime(entry.exit_time, "%H:%M:%S").time() if entry.exit_time else None,
            is_active=True
        )
        db.add(schedule)

    await db.commit()

    logger.info(
        f"[HEDGE_API] Updated schedule for {request.day_of_week}: "
        f"{len(request.entries)} entries"
    )

    return await get_schedule(request.day_of_week, db)


# ============================================================
# Session Endpoints
# ============================================================

@router.get("/session")
async def get_current_session(db: AsyncSession = Depends(get_db)):
    """
    Get today's session configuration.

    Returns:
        Session data or 404 if not found
    """
    today = datetime.now(IST).date()

    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "No session found for today")

    return SessionResponse(
        id=session.id,
        session_date=session.session_date,
        day_of_week=session.day_of_week,
        index_name=session.index_name,
        expiry_type=session.expiry_type,
        expiry_date=session.expiry_date,
        num_baskets=session.num_baskets,
        budget_per_basket=float(session.budget_per_basket),
        total_budget=float(session.total_budget),
        baseline_margin=float(session.baseline_margin) if session.baseline_margin else None,
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


@router.post("/session")
async def create_session(
    request: SessionCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create or update a daily session.

    Args:
        request: Session configuration

    Returns:
        Created/updated session
    """
    # Check if session already exists
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == request.session_date)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing
        existing.index_name = request.index_name
        existing.expiry_type = request.expiry_type
        existing.expiry_date = request.expiry_date
        existing.num_baskets = request.num_baskets
        existing.budget_per_basket = request.budget_per_basket
        existing.total_budget = request.num_baskets * request.budget_per_basket
        existing.auto_hedge_enabled = request.auto_hedge_enabled
        session = existing
    else:
        # Create new
        session = DailySession(
            session_date=request.session_date,
            day_of_week=request.session_date.strftime("%A"),
            index_name=request.index_name,
            expiry_type=request.expiry_type,
            expiry_date=request.expiry_date,
            num_baskets=request.num_baskets,
            budget_per_basket=request.budget_per_basket,
            total_budget=request.num_baskets * request.budget_per_basket,
            auto_hedge_enabled=request.auto_hedge_enabled
        )
        db.add(session)

    await db.commit()
    await db.refresh(session)

    logger.info(
        f"[HEDGE_API] Session {'updated' if existing else 'created'} for "
        f"{request.session_date}: {request.index_name}, {request.num_baskets} baskets"
    )

    return SessionResponse(
        id=session.id,
        session_date=session.session_date,
        day_of_week=session.day_of_week,
        index_name=session.index_name,
        expiry_type=session.expiry_type,
        expiry_date=session.expiry_date,
        num_baskets=session.num_baskets,
        budget_per_basket=float(session.budget_per_basket),
        total_budget=float(session.total_budget),
        baseline_margin=float(session.baseline_margin) if session.baseline_margin else None,
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


# ============================================================
# Transaction Endpoints
# ============================================================

@router.get("/transactions")
async def get_transactions(
    session_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get hedge transaction history.

    Args:
        session_date: Optional date. Defaults to today.

    Returns:
        Transaction list with summary
    """
    if session_date is None:
        session_date = datetime.now(IST).date()

    # Get session
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == session_date)
    )
    session = result.scalar_one_or_none()

    if not session:
        return TransactionsResponse(
            session_date=session_date,
            transactions=[],
            total_count=0,
            total_cost=0,
            total_recovered=0,
            net_cost=0
        )

    # Get transactions
    result = await db.execute(
        select(HedgeTransaction)
        .where(HedgeTransaction.session_id == session.id)
        .order_by(HedgeTransaction.timestamp.desc())
    )
    transactions = result.scalars().all()

    # Calculate totals
    total_cost = sum(
        float(t.total_cost or 0)
        for t in transactions
        if t.action == "BUY" and t.order_status == "SUCCESS"
    )
    total_recovered = sum(
        float(t.total_cost or 0)
        for t in transactions
        if t.action == "SELL" and t.order_status == "SUCCESS"
    )

    return TransactionsResponse(
        session_date=session_date,
        transactions=[
            HedgeTransactionSchema(
                id=t.id,
                timestamp=t.timestamp,
                action=t.action,
                trigger_reason=t.trigger_reason,
                symbol=t.symbol,
                exchange=t.exchange,
                strike=t.strike,
                option_type=t.option_type,
                quantity=t.quantity,
                lots=t.lots,
                order_price=float(t.order_price),
                executed_price=float(t.executed_price) if t.executed_price else None,
                total_cost=float(t.total_cost) if t.total_cost else None,
                utilization_before=float(t.utilization_before),
                utilization_after=float(t.utilization_after) if t.utilization_after else None,
                margin_impact=float(t.margin_impact) if t.margin_impact else None,
                order_id=t.order_id,
                order_status=t.order_status,
                error_message=t.error_message
            )
            for t in transactions
        ],
        total_count=len(transactions),
        total_cost=total_cost,
        total_recovered=total_recovered,
        net_cost=total_cost - total_recovered
    )


# ============================================================
# Manual Action Endpoints
# ============================================================

@router.post("/manual/buy", response_model=ActionResponse)
async def manual_hedge_buy(
    request: ManualHedgeBuyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a hedge buy.

    Args:
        request: Strike and option type

    Returns:
        Action result
    """
    orchestrator = get_orchestrator()

    if not orchestrator or not orchestrator.session:
        raise HTTPException(400, "No active session")

    session = orchestrator.session

    # Create hedge candidate
    candidate = HedgeCandidate(
        strike=request.strike,
        option_type=request.option_type,
        ltp=5.0,  # Will be fetched
        otm_distance=0,
        estimated_margin_benefit=0,
        cost_per_lot=0,
        total_cost=0,
        total_lots=0,
        mbpr=0
    )

    executor = HedgeExecutorService(db)

    result = await executor.execute_hedge_buy(
        session_id=session.id,
        candidate=candidate,
        index=IndexName(session.index_name),
        expiry_date=session.expiry_date.isoformat(),
        num_baskets=session.num_baskets,
        trigger_reason="MANUAL",
        utilization_before=0,  # Would need to fetch
        dry_run=False
    )

    return ActionResponse(
        success=result.success,
        message="Hedge buy executed" if result.success else "Hedge buy failed",
        order_id=result.order_id,
        error=result.error_message
    )


@router.post("/manual/exit", response_model=ActionResponse)
async def manual_hedge_exit(
    request: ManualHedgeExitRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a hedge exit.

    Args:
        request: Hedge ID to exit

    Returns:
        Action result
    """
    orchestrator = get_orchestrator()

    if not orchestrator or not orchestrator.session:
        raise HTTPException(400, "No active session")

    session = orchestrator.session
    executor = HedgeExecutorService(db)

    result = await executor.execute_hedge_exit(
        hedge_id=request.hedge_id,
        session_id=session.id,
        trigger_reason="MANUAL",
        utilization_before=0,
        dry_run=False
    )

    return ActionResponse(
        success=result.success,
        message="Hedge exit executed" if result.success else "Hedge exit failed",
        order_id=result.order_id,
        error=result.error_message
    )


# ============================================================
# Analytics Endpoints
# ============================================================

@router.get("/analytics")
async def get_analytics(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """
    Get hedge analytics for the past N days.

    Args:
        days: Number of days to analyze

    Returns:
        Analytics data
    """
    # Get sessions with transaction aggregates
    result = await db.execute(
        select(DailySession)
        .order_by(DailySession.session_date.desc())
        .limit(days)
    )
    sessions = result.scalars().all()

    data = []
    total_cost = 0
    total_recovered = 0

    for session in sessions:
        # Get transaction summary for session
        tx_result = await db.execute(
            select(
                func.count(HedgeTransaction.id).label('count'),
                func.sum(
                    func.case(
                        (HedgeTransaction.action == 'BUY', HedgeTransaction.total_cost),
                        else_=0
                    )
                ).label('cost'),
                func.sum(
                    func.case(
                        (HedgeTransaction.action == 'SELL', HedgeTransaction.total_cost),
                        else_=0
                    )
                ).label('recovered'),
                func.max(HedgeTransaction.utilization_before).label('peak_util')
            )
            .where(HedgeTransaction.session_id == session.id)
            .where(HedgeTransaction.order_status == 'SUCCESS')
        )
        tx_data = tx_result.first()

        # Get strategy execution count
        exec_result = await db.execute(
            select(func.count(StrategyExecution.id))
            .where(StrategyExecution.session_id == session.id)
        )
        exec_count = exec_result.scalar() or 0

        cost = float(tx_data.cost or 0)
        recovered = float(tx_data.recovered or 0)

        data.append(DailyAnalyticsSchema(
            session_date=session.session_date,
            day_of_week=session.day_of_week,
            index_name=session.index_name,
            num_baskets=session.num_baskets,
            hedge_count=tx_data.count or 0,
            total_cost=cost,
            total_recovered=recovered,
            net_cost=cost - recovered,
            peak_utilization=float(tx_data.peak_util or 0),
            strategies_executed=exec_count
        ))

        total_cost += cost
        total_recovered += recovered

    return AnalyticsResponse(
        days=days,
        data=data,
        summary={
            'total_sessions': len(data),
            'total_cost': total_cost,
            'total_recovered': total_recovered,
            'net_cost': total_cost - total_recovered,
            'avg_cost_per_day': total_cost / len(data) if data else 0
        }
    )
