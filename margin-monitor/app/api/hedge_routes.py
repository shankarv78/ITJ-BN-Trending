"""
Auto-Hedge System - API Routes

REST API endpoints for managing and monitoring the auto-hedge system.
"""

import logging
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, func, case
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
    BaselineUpdateRequest, ExcludedMarginUpdateRequest, AutoSessionRequest,
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

# ============================================================
# Security
# ============================================================

security = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> bool:
    """
    Verify API key for sensitive endpoints.

    Requires HEDGE_API_KEY environment variable to be set.
    Pass the key as: Authorization: Bearer <api_key>

    In development (HEDGE_DEV_MODE=true), allows requests without API key.
    In production, API key is REQUIRED - no fallback.
    """
    api_key = os.getenv("HEDGE_API_KEY")
    dev_mode = os.getenv("HEDGE_DEV_MODE", "false").lower() == "true"

    # If no API key configured
    if not api_key:
        if dev_mode:
            logger.warning(
                "[SECURITY] HEDGE_DEV_MODE=true - API key not required (dev only!)"
            )
            return True
        else:
            # Production: REQUIRE API key configuration
            logger.critical(
                "[SECURITY] HEDGE_API_KEY not set - blocking request! "
                "Set HEDGE_API_KEY env var or use HEDGE_DEV_MODE=true for development."
            )
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: API authentication not configured"
            )

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Use Authorization: Bearer <api_key>"
        )

    if credentials.credentials != api_key:
        logger.warning("[SECURITY] Invalid API key attempt")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return True

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

@router.get("/debug")
async def debug_orchestrator():
    """Debug endpoint to check orchestrator state."""
    orchestrator = get_orchestrator()
    if not orchestrator:
        return {"error": "orchestrator is None"}

    try:
        # Check basic attributes
        info = {
            "has_scheduler": orchestrator.scheduler is not None,
            "has_executor": orchestrator.hedge_executor is not None,
            "has_db": orchestrator.db is not None,
            "_is_running": getattr(orchestrator, '_is_running', 'NOT_SET'),
            "_dry_run": getattr(orchestrator, '_dry_run', 'NOT_SET'),
            "_session": str(getattr(orchestrator, '_session', 'NOT_SET')),
        }

        # Try get_status
        try:
            status = await orchestrator.get_status()
            info["get_status"] = "SUCCESS"
            info["status_data"] = status
        except Exception as e:
            import traceback
            info["get_status"] = f"FAILED: {e}"
            info["traceback"] = traceback.format_exc()

        return info
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/status", response_model=HedgeStatusResponse)
async def get_hedge_status(db: AsyncSession = Depends(get_db)):
    """
    Get current auto-hedge status.

    Returns:
        Current status including session, active hedges, next entry
    """
    orchestrator = get_orchestrator()

    # Always fetch session from DB for accurate toggle state
    today = datetime.now(IST).date()
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    db_session = result.scalar_one_or_none()

    if not db_session:
        # Fall back to most recent session
        result = await db.execute(
            select(DailySession)
            .order_by(DailySession.session_date.desc())
            .limit(1)
        )
        db_session = result.scalar_one_or_none()

    session_response = None
    if db_session:
        session_response = SessionResponse(
            id=db_session.id,
            session_date=db_session.session_date,
            day_of_week=db_session.day_of_week,
            index_name=db_session.index_name,
            expiry_type=db_session.expiry_type,
            expiry_date=db_session.expiry_date,
            num_baskets=db_session.num_baskets,
            budget_per_basket=float(db_session.budget_per_basket),
            total_budget=float(db_session.total_budget),
            baseline_margin=float(db_session.baseline_margin) if db_session.baseline_margin else None,
            auto_hedge_enabled=db_session.auto_hedge_enabled,
            created_at=db_session.created_at
        )

    if not orchestrator:
        return HedgeStatusResponse(
            status="not_initialized",
            dry_run=False,
            session=session_response  # Still show session even if orchestrator not started
        )

    try:
        status_data = await orchestrator.get_status()
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Error getting orchestrator status: {e}\n{error_detail}")
        # Return partial response even if orchestrator fails
        return HedgeStatusResponse(
            status="error",
            dry_run=False,
            session=session_response
        )

    # Determine status based on session's auto_hedge_enabled
    if session_response and not session_response.auto_hedge_enabled:
        display_status = "disabled"
    elif status_data.get('is_running', False):
        display_status = "running"
    else:
        display_status = "stopped"

    # Build simulated margin schema if present (dry run mode)
    simulated_margin = None
    if status_data.get('simulated_margin'):
        from app.api.hedge_schemas import SimulatedMarginSchema, SimulatedHedgeSchema
        sim_data = status_data['simulated_margin']
        simulated_margin = SimulatedMarginSchema(
            total_reduction=sim_data.get('total_reduction', 0),
            max_reduction=sim_data.get('max_reduction', 0),
            hedge_count=sim_data.get('hedge_count', 0),
            ce_hedge_count=sim_data.get('ce_hedge_count', 0),
            pe_hedge_count=sim_data.get('pe_hedge_count', 0),
            ce_hedge_qty=sim_data.get('ce_hedge_qty', 0),
            pe_hedge_qty=sim_data.get('pe_hedge_qty', 0),
            real_utilization_pct=sim_data.get('real_utilization_pct', 0),
            simulated_utilization_pct=sim_data.get('simulated_utilization_pct', 0),
            hedges=[SimulatedHedgeSchema(**h) for h in sim_data.get('hedges', [])]
        )

    # Build hedge capacity schema if present
    hedge_capacity = None
    if status_data.get('hedge_capacity'):
        from app.api.hedge_schemas import HedgeCapacitySchema
        cap_data = status_data['hedge_capacity']
        hedge_capacity = HedgeCapacitySchema(
            remaining_ce_capacity=cap_data.get('remaining_ce_capacity', 0),
            remaining_pe_capacity=cap_data.get('remaining_pe_capacity', 0),
            short_ce_qty=cap_data.get('short_ce_qty', 0),
            short_pe_qty=cap_data.get('short_pe_qty', 0),
            long_ce_qty=cap_data.get('long_ce_qty', 0),
            long_pe_qty=cap_data.get('long_pe_qty', 0),
            is_fully_hedged=cap_data.get('is_fully_hedged', False)
        )

    return HedgeStatusResponse(
        status=display_status,
        dry_run=status_data.get('dry_run', False),
        session=session_response,
        active_hedges=[ActiveHedgeSchema(**h) for h in status_data.get('active_hedges', [])],
        next_entry=NextEntrySchema(**status_data['next_entry']) if status_data.get('next_entry') else None,
        cooldown_remaining=status_data.get('cooldown_remaining', 0),
        simulated_margin=simulated_margin,
        hedge_capacity=hedge_capacity
    )


@router.post("/toggle", response_model=ToggleResponse, dependencies=[Depends(verify_api_key)])
async def toggle_auto_hedge(
    request: ToggleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enable or disable auto-hedge for the active session.

    Requires API key authentication.

    Args:
        request: Toggle request with enabled flag

    Returns:
        Success status
    """
    today = datetime.now(IST).date()

    # Try today's session first
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    # Fall back to most recent session
    if not session:
        result = await db.execute(
            select(DailySession)
            .order_by(DailySession.session_date.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(400, "No session found")

    session.auto_hedge_enabled = request.enabled
    await db.commit()

    status = "enabled" if request.enabled else "disabled"
    logger.info(f"[HEDGE_API] Auto-hedge {status} for session {session.session_date}")

    return ToggleResponse(
        success=True,
        auto_hedge_enabled=request.enabled,
        message=f"Auto-hedge {status} for session {session.session_date}"
    )


@router.post("/reset-dry-run", response_model=ActionResponse)
async def reset_dry_run(db: AsyncSession = Depends(get_db)):
    """
    Reset dry run data - deletes all transactions and resets simulated margin.

    Only works when system is in dry run mode.
    Does NOT require API key since it only affects simulated data.

    Returns:
        Action result with count of deleted records
    """
    orchestrator = get_orchestrator()

    # Check if in dry run mode
    if orchestrator and not orchestrator._dry_run:
        raise HTTPException(400, "Reset only available in dry run mode")

    # Get the current session
    today = datetime.now(IST).date()
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        # Fall back to most recent session
        result = await db.execute(
            select(DailySession)
            .order_by(DailySession.session_date.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(400, "No session found")

    # Delete all hedge transactions for this session
    from sqlalchemy import delete

    txn_result = await db.execute(
        delete(HedgeTransaction).where(HedgeTransaction.session_id == session.id)
    )
    txn_count = txn_result.rowcount

    # Delete active hedges
    hedge_result = await db.execute(
        delete(ActiveHedge).where(ActiveHedge.session_id == session.id)
    )
    hedge_count = hedge_result.rowcount

    await db.commit()

    # Reset orchestrator's in-memory simulated margin tracking
    if orchestrator:
        orchestrator.reset_simulated_margin()

    logger.info(
        f"[HEDGE_API] Reset dry run: deleted {txn_count} transactions, "
        f"{hedge_count} active hedges for session {session.session_date}"
    )

    return ActionResponse(
        success=True,
        message=f"Reset complete: deleted {txn_count} transactions, {hedge_count} active hedges",
        dry_run=True
    )


# ============================================================
# Schedule Endpoints
# ============================================================

@router.get("/schedule")
async def get_schedule(
    day: Optional[str] = None,
    all_days: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Get strategy schedule.

    Args:
        day: Optional day name (Monday, Tuesday, etc.). If not provided,
             returns today's schedule.
        all_days: If true, returns schedule for all days (Monday-Friday)

    Returns:
        Schedule for the specified day, or list of schedules for all days
    """
    # If all_days requested, return a list of schedules for each day
    if all_days:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        result_list = []

        for d in days:
            result = await db.execute(
                select(StrategySchedule)
                .where(StrategySchedule.day_of_week == d)
                .where(StrategySchedule.is_active == True)
                .order_by(StrategySchedule.entry_time)
            )
            schedules = result.scalars().all()

            entries = [
                {
                    "id": s.id,
                    "day_of_week": s.day_of_week,
                    "index_name": s.index_name,
                    "expiry_type": s.expiry_type,
                    "portfolio_name": s.portfolio_name,
                    "entry_time": s.entry_time.isoformat() if s.entry_time else "",
                    "exit_time": s.exit_time.isoformat() if s.exit_time else None,
                    "is_active": s.is_active
                }
                for s in schedules
            ]

            result_list.append({
                "day": d,
                "entries": entries
            })

        return result_list

    # Original single-day logic
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
async def get_current_session(
    session_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get session configuration.

    If session_date is provided, returns that specific session.
    Otherwise, returns today's session or the most recent session if none for today.

    Returns:
        Session data or 404 if not found
    """
    from datetime import datetime as dt

    session = None

    if session_date:
        # Parse provided date
        try:
            target_date = dt.strptime(session_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, f"Invalid date format: {session_date}. Use YYYY-MM-DD")

        result = await db.execute(
            select(DailySession).where(DailySession.session_date == target_date)
        )
        session = result.scalar_one_or_none()
    else:
        # Try today first
        today = datetime.now(IST).date()
        result = await db.execute(
            select(DailySession).where(DailySession.session_date == today)
        )
        session = result.scalar_one_or_none()

        if not session:
            # Fall back to most recent session
            result = await db.execute(
                select(DailySession)
                .order_by(DailySession.session_date.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "No session found")

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
        excluded_margin=float(session.excluded_margin) if session.excluded_margin else None,
        excluded_margin_breakdown=_parse_json_or_none(session.excluded_margin_breakdown) if hasattr(session, 'excluded_margin_breakdown') else None,
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


def _parse_json_or_none(json_str) -> Optional[dict]:
    """Parse JSON string or return None."""
    if not json_str:
        return None
    try:
        import json
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


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
        excluded_margin=float(session.excluded_margin) if session.excluded_margin else None,
        excluded_margin_breakdown=_parse_json_or_none(session.excluded_margin_breakdown),
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


@router.patch("/session/baseline")
async def update_baseline_margin(
    request: BaselineUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update baseline margin for today's session.

    This allows manual adjustment of the baseline margin at day start.
    Useful when overnight positions change or baseline was captured incorrectly.

    Args:
        request: New baseline margin value

    Returns:
        Updated session
    """
    # Get today's session
    today = datetime.now(IST).date()
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "No session found for today. Create a session first.")

    # Update baseline
    session.baseline_margin = request.baseline_margin
    session.baseline_captured_at = datetime.now(IST)

    await db.commit()
    await db.refresh(session)

    logger.info(
        f"[HEDGE_API] Baseline margin updated to ₹{request.baseline_margin:,.0f} "
        f"for session {session.session_date}"
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
        excluded_margin=float(session.excluded_margin) if session.excluded_margin else None,
        excluded_margin_breakdown=_parse_json_or_none(session.excluded_margin_breakdown),
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


@router.post("/session/refresh-excluded")
async def refresh_excluded_margin(
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh excluded margin calculation for today's session.

    Queries PM for trend-following positions and identifies long-term positions,
    then updates the session's excluded_margin field.

    Returns:
        Updated session with new excluded margin values
    """
    import json
    from app.services.margin_service import margin_service

    # Get today's session
    today = datetime.now(IST).date()
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "No session found for today. Create a session first.")

    # Calculate excluded margin
    try:
        excluded_data = await margin_service.get_excluded_margin_breakdown()

        # Update session
        session.excluded_margin = excluded_data["total_excluded"]
        session.excluded_margin_breakdown = json.dumps(excluded_data["combined_breakdown"])
        session.excluded_margin_updated_at = datetime.now(IST)

        await db.commit()
        await db.refresh(session)

        logger.info(
            f"[HEDGE_API] Excluded margin refreshed: ₹{excluded_data['total_excluded']:,.0f} "
            f"(PM: ₹{excluded_data['pm_excluded']:,.0f}, "
            f"Long-term: ₹{excluded_data['long_term_excluded']:,.0f})"
        )

        return {
            "session_id": session.id,
            "excluded_margin": float(session.excluded_margin),
            "breakdown": excluded_data,
            "updated_at": session.excluded_margin_updated_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to refresh excluded margin: {e}")
        raise HTTPException(500, f"Failed to calculate excluded margin: {str(e)}")


@router.post("/session/auto-create")
async def auto_create_session(
    request: AutoSessionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Auto-create session based on strategy schedule.

    Looks up the strategy_schedule table for the specified day to determine
    index and expiry type, then calculates the actual expiry date.

    Args:
        request: Session parameters (date, baskets, budget)

    Returns:
        Created session
    """
    from app.services.strategy_scheduler import expiry_utils

    target_date = request.session_date or datetime.now(IST).date()
    day_name = target_date.strftime("%A")

    # Check if session already exists
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == target_date)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return SessionResponse(
            id=existing.id,
            session_date=existing.session_date,
            day_of_week=existing.day_of_week,
            index_name=existing.index_name,
            expiry_type=existing.expiry_type,
            expiry_date=existing.expiry_date,
            num_baskets=existing.num_baskets,
            budget_per_basket=float(existing.budget_per_basket),
            total_budget=float(existing.total_budget),
            baseline_margin=float(existing.baseline_margin) if existing.baseline_margin else None,
            excluded_margin=float(existing.excluded_margin) if existing.excluded_margin else None,
            excluded_margin_breakdown=_parse_json_or_none(existing.excluded_margin_breakdown),
            auto_hedge_enabled=existing.auto_hedge_enabled,
            created_at=existing.created_at
        )

    # Look up schedule for this day
    result = await db.execute(
        select(StrategySchedule)
        .where(StrategySchedule.day_of_week == day_name)
        .where(StrategySchedule.is_active == True)
        .limit(1)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        # Use defaults from DAY_TO_INDEX_EXPIRY if no schedule
        day_config = DAY_TO_INDEX_EXPIRY.get(day_name, {})
        index_name = day_config.get("index", "NIFTY")
        expiry_type = day_config.get("expiry", "0DTE")
    else:
        index_name = schedule.index_name
        expiry_type = schedule.expiry_type

    # Calculate expiry date
    try:
        expiry_date = expiry_utils.get_expiry_date(
            IndexName(index_name),
            ExpiryType(expiry_type),
            target_date
        )
    except Exception as e:
        logger.warning(f"Failed to calculate expiry: {e}, using target date")
        expiry_date = target_date

    # Create session
    session = DailySession(
        session_date=target_date,
        day_of_week=day_name,
        index_name=index_name,
        expiry_type=expiry_type,
        expiry_date=expiry_date,
        num_baskets=request.num_baskets,
        budget_per_basket=request.budget_per_basket,
        total_budget=request.num_baskets * request.budget_per_basket,
        auto_hedge_enabled=request.auto_hedge_enabled
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        f"[HEDGE_API] Auto-created session for {target_date}: "
        f"{index_name} {expiry_type}, {request.num_baskets} baskets"
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
        excluded_margin=float(session.excluded_margin) if session.excluded_margin else None,
        excluded_margin_breakdown=_parse_json_or_none(session.excluded_margin_breakdown),
        auto_hedge_enabled=session.auto_hedge_enabled,
        created_at=session.created_at
    )


@router.get("/excluded-margin")
async def get_excluded_margin():
    """
    Get current excluded margin breakdown without updating session.

    Returns real-time calculation of:
    - PM trend-following positions (Gold Mini, Bank Nifty, Silver Mini, etc.)
    - Long-term positions (expiry > 30 days)
    """
    from app.services.margin_service import margin_service

    try:
        excluded_data = await margin_service.get_excluded_margin_breakdown()
        return excluded_data
    except Exception as e:
        logger.error(f"Failed to get excluded margin: {e}")
        raise HTTPException(500, f"Failed to calculate excluded margin: {str(e)}")


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

@router.post("/manual/buy", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
async def manual_hedge_buy(
    request: ManualHedgeBuyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a hedge buy.

    Requires API key authentication.
    Supports dry_run mode for paper trading / testing.

    Args:
        request: Index, expiry, option type, strike offset, lots, and dry_run flag

    Returns:
        Action result with simulated order details if dry_run
    """
    # Get session from DB (works even without orchestrator)
    today = datetime.now(IST).date()
    result = await db.execute(
        select(DailySession).where(DailySession.session_date == today)
    )
    session = result.scalar_one_or_none()

    if not session:
        # Fall back to most recent session
        result = await db.execute(
            select(DailySession)
            .order_by(DailySession.session_date.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(400, "No session found. Create a session first.")

    # Calculate simulated strike based on index name and offset
    # In real mode, we'd fetch the current spot price
    simulated_spot = 24000 if request.index_name == "NIFTY" else 80000  # Placeholder
    if request.option_type == "PE":
        simulated_strike = simulated_spot - request.strike_offset
    else:
        simulated_strike = simulated_spot + request.strike_offset

    # Round strike to nearest valid strike (50 for NIFTY, 100 for SENSEX)
    strike_gap = 50 if request.index_name == "NIFTY" else 100
    simulated_strike = round(simulated_strike / strike_gap) * strike_gap

    # Get lot size for the index
    index_upper = request.index_name.upper()
    lot_sizes = {"NIFTY": 65, "BANKNIFTY": 30, "SENSEX": 20}
    lot_size = lot_sizes.get(index_upper, 65)  # Default to NIFTY
    quantity = request.lots * lot_size

    # Build the simulated order details
    simulated_order = {
        "index": request.index_name,
        "expiry_date": request.expiry_date,
        "option_type": request.option_type,
        "strike": simulated_strike,
        "strike_offset": request.strike_offset,
        "lots": request.lots,
        "lot_size": lot_size,
        "quantity": quantity,
        "estimated_premium": 5.0,  # Would be fetched from option chain
        "estimated_cost": quantity * 5.0,
        "reason": request.reason or "Manual hedge via UI",
        "session_id": session.id,
        "session_date": str(session.session_date),
    }

    if request.dry_run:
        # Paper trade - just log and return
        logger.info(f"[PAPER TRADE] Manual buy simulated: {simulated_order}")
        return ActionResponse(
            success=True,
            message=f"📝 Paper trade simulated: {request.option_type} {simulated_strike} x {request.lots} lots",
            dry_run=True,
            simulated_order=simulated_order
        )

    # Real order - use the executor
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(400, "Orchestrator not running. Cannot place real orders.")

    # Fetch current margin utilization for accurate audit trail
    current_util = 0.0
    try:
        margin_data = await orchestrator._get_current_margin()
        if margin_data:
            current_util = margin_data.get('utilization_pct', 0.0)
    except Exception as e:
        logger.warning(f"[HEDGE_API] Could not fetch margin for manual buy: {e}")

    # Create hedge candidate
    candidate = HedgeCandidate(
        strike=simulated_strike,
        option_type=request.option_type,
        ltp=5.0,  # Will be fetched
        otm_distance=request.strike_offset,
        estimated_margin_benefit=0,
        cost_per_lot=0,
        total_cost=0,
        total_lots=request.lots,
        mbpr=0
    )

    executor = HedgeExecutorService(db)

    exec_result = await executor.execute_hedge_buy(
        session_id=session.id,
        candidate=candidate,
        index=IndexName(session.index_name),
        expiry_date=session.expiry_date.isoformat(),
        num_baskets=session.num_baskets,
        trigger_reason="MANUAL",
        utilization_before=current_util,
        dry_run=False
    )

    return ActionResponse(
        success=exec_result.success,
        message="Hedge buy executed" if exec_result.success else "Hedge buy failed",
        order_id=exec_result.order_id,
        error=exec_result.error_message,
        dry_run=False
    )


@router.post("/manual/exit", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
async def manual_hedge_exit(
    request: ManualHedgeExitRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a hedge exit.

    Requires API key authentication.
    Supports dry_run mode for paper trading / testing.

    Args:
        request: Hedge ID to exit and dry_run flag

    Returns:
        Action result
    """
    # Get the hedge from DB
    result = await db.execute(
        select(ActiveHedge).where(ActiveHedge.id == request.hedge_id)
    )
    hedge = result.scalar_one_or_none()

    if not hedge:
        raise HTTPException(404, f"Hedge {request.hedge_id} not found")

    # Build simulated exit details
    simulated_exit = {
        "hedge_id": request.hedge_id,
        "symbol": hedge.symbol,
        "strike": hedge.strike,
        "option_type": hedge.option_type,
        "quantity": hedge.quantity,
        "entry_price": float(hedge.entry_price),
        "estimated_exit_price": float(hedge.entry_price) * 0.8,  # Estimate some decay
        "reason": request.reason or "Manual exit via UI",
    }

    if request.dry_run:
        # Paper trade - just log and return
        logger.info(f"[PAPER TRADE] Manual exit simulated: {simulated_exit}")
        return ActionResponse(
            success=True,
            message=f"📝 Paper exit simulated: {hedge.symbol} x {hedge.quantity} qty",
            dry_run=True,
            simulated_order=simulated_exit
        )

    # Real order - need orchestrator for margin tracking
    orchestrator = get_orchestrator()

    # Fetch current margin utilization for accurate audit trail
    current_util = 0.0
    if orchestrator:
        try:
            margin_data = await orchestrator._get_current_margin()
            if margin_data:
                current_util = margin_data.get('utilization_pct', 0.0)
        except Exception as e:
            logger.warning(f"[HEDGE_API] Could not fetch margin for manual exit: {e}")

    executor = HedgeExecutorService(db)

    exec_result = await executor.execute_hedge_exit(
        hedge_id=request.hedge_id,
        session_id=hedge.session_id,
        trigger_reason="MANUAL",
        utilization_before=current_util,
        dry_run=False
    )

    return ActionResponse(
        success=exec_result.success,
        message="Hedge exit executed" if exec_result.success else "Hedge exit failed",
        order_id=exec_result.order_id,
        error=exec_result.error_message,
        dry_run=False
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
                    case(
                        (HedgeTransaction.action == 'BUY', HedgeTransaction.total_cost),
                        else_=0
                    )
                ).label('cost'),
                func.sum(
                    case(
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
