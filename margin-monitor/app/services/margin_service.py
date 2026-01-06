"""
Margin Monitor - Margin Service

Calculates intraday margin utilization and captures snapshots.

Key Concepts:
- Total Used Margin: From OpenAlgo (all positions in account)
- Baseline Margin: Captured at day start (overnight positions)
- Excluded Margin: PM trend-following + long-term positions (not intraday)
- Intraday Margin: total_used - baseline - excluded
- Utilization %: (intraday / total_budget) * 100
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db_models import DailyConfig, MarginSnapshot, PositionSnapshot, DailySummary
from app.services.openalgo_service import openalgo_service, FundsData
from app.services.position_service import position_service
from app.services.pm_client import pm_client, ExcludedMarginResult
from app.utils.date_utils import now_ist, format_datetime_ist
from app.utils.symbol_parser import parse_symbol, get_position_type

logger = logging.getLogger(__name__)

# Margin per lot estimates for long-term positions
LONG_TERM_MARGIN_PER_LOT = {
    "NIFTY": 100000,    # ~₹1L per lot for Nifty synthetic/futures
    "BANKNIFTY": 130000,
}

# Positions with expiry > this many days are considered "long-term"
LONG_TERM_EXPIRY_DAYS = 30


class MarginService:
    """Service for margin calculations and snapshots."""

    async def _get_long_term_excluded_margin(
        self,
        positions: List[Dict[str, Any]],
        session_expiry_date: str
    ) -> Dict[str, Any]:
        """
        Identify long-term positions and estimate their margin.

        Long-term positions are those with expiry > LONG_TERM_EXPIRY_DAYS from today.
        These should be excluded from intraday margin calculation.

        Args:
            positions: All positions from OpenAlgo
            session_expiry_date: Current session's expiry (YYYY-MM-DD)

        Returns:
            Dict with total_margin, breakdown, and position details
        """
        today = datetime.now().date()
        cutoff_date = today + timedelta(days=LONG_TERM_EXPIRY_DAYS)

        breakdown: Dict[str, float] = {}
        long_term_positions: List[Dict[str, Any]] = []
        total_margin = 0.0

        for pos in positions:
            symbol = pos.get("symbol", "")
            parsed = parse_symbol(symbol)

            if not parsed or not parsed.expiry_date:
                continue

            try:
                expiry_date = datetime.strptime(parsed.expiry_date, "%Y-%m-%d").date()
            except ValueError:
                continue

            # Check if this is a long-term position
            if expiry_date > cutoff_date:
                index = parsed.index
                qty = abs(pos.get("quantity", 0))

                # Estimate margin based on index
                # For synthetic positions, margin is roughly per lot
                lot_size = 65 if index == "NIFTY" else 20 if index == "BANKNIFTY" else 50
                lots = qty // lot_size if lot_size > 0 else 0

                margin_per_lot = LONG_TERM_MARGIN_PER_LOT.get(index, 50000)
                estimated_margin = lots * margin_per_lot

                breakdown[index] = breakdown.get(index, 0) + estimated_margin
                total_margin += estimated_margin

                long_term_positions.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "expiry_date": parsed.expiry_date,
                    "estimated_margin": estimated_margin,
                    "index": index,
                })

                logger.debug(
                    f"Long-term position: {symbol} qty={qty} expiry={parsed.expiry_date} "
                    f"margin=₹{estimated_margin:,.0f}"
                )

        if long_term_positions:
            logger.info(
                f"Long-term excluded margin: ₹{total_margin:,.0f} "
                f"from {len(long_term_positions)} positions"
            )

        return {
            "total_margin": total_margin,
            "breakdown": breakdown,
            "positions": long_term_positions,
        }

    async def get_excluded_margin_breakdown(self) -> Dict[str, Any]:
        """
        Get excluded margin breakdown.

        Only PM trend-following positions are excluded from intraday calculation.
        Long-term positions are NOT excluded here because they're already
        captured in the baseline margin (captured at market open).

        Returns:
            Dict with pm_excluded and total (same as pm_excluded)
        """
        # Get PM excluded margin (BN, Gold Mini, Silver Mini trend-following)
        pm_result = await pm_client.get_excluded_margin()

        # NOTE: Long-term positions (expiry > 30 days) are NOT excluded here
        # because baseline already captures them. Double-subtracting would
        # cause intraday margin to be underreported.

        return {
            "pm_excluded": pm_result.total_excluded,
            "pm_breakdown": pm_result.breakdown,
            "pm_positions": pm_result.positions,
            "long_term_excluded": 0.0,  # Not used - baseline handles this
            "long_term_breakdown": {},
            "long_term_positions": [],
            "total_excluded": pm_result.total_excluded,  # Only PM positions
            "combined_breakdown": pm_result.breakdown,
        }

    async def get_current_margin(
        self,
        config: DailyConfig,
        db: AsyncSession,
        include_excluded: bool = True
    ) -> dict:
        """
        Get current margin status for a config.

        Args:
            config: Daily configuration with baseline
            db: Database session
            include_excluded: Whether to subtract excluded margin (default True)

        Returns:
            Dictionary with margin, positions, and M2M data.
        """
        # Fetch funds from OpenAlgo
        funds = await openalgo_service.get_funds()

        # Get baseline
        baseline = config.baseline_margin or 0.0

        # Get excluded margin (PM + long-term)
        excluded_margin = 0.0
        excluded_breakdown: Dict[str, Any] = {}

        if include_excluded:
            try:
                excluded_data = await self.get_excluded_margin_breakdown()
                excluded_margin = excluded_data["total_excluded"]
                excluded_breakdown = excluded_data
            except Exception as e:
                logger.warning(f"Failed to get excluded margin: {e}")
                excluded_margin = 0.0

        # Calculate intraday margin
        # Formula: intraday = total_used - baseline - excluded
        intraday = funds['used_margin'] - baseline - excluded_margin

        # Ensure intraday doesn't go negative
        intraday = max(0, intraday)

        utilization = (intraday / config.total_budget) * 100 if config.total_budget > 0 else 0.0
        budget_remaining = config.total_budget - intraday

        # Fetch and filter positions for this session's index/expiry
        positions = await openalgo_service.get_positions()
        filtered = position_service.filter_positions(
            positions,
            config.index_name,
            config.expiry_date.strftime('%Y-%m-%d')
        )
        summary = position_service.get_summary(filtered)

        return {
            'margin': {
                'total_used': funds['used_margin'],
                'baseline': baseline,
                'excluded': excluded_margin,
                'excluded_breakdown': excluded_breakdown,
                'intraday_used': intraday,
                'available_cash': funds['available_cash'],
                'collateral': funds['collateral'],
                'utilization_pct': round(utilization, 2),
                'budget_remaining': round(budget_remaining, 2),
            },
            'positions': {
                'short_count': summary['short_count'],
                'short_qty': summary['short_qty'],
                'long_count': summary['long_count'],
                'long_qty': summary['long_qty'],
                'closed_count': summary['closed_count'],
                'hedge_cost': round(summary['hedge_cost'], 2),
                'total_pnl': round(summary['total_pnl'], 2),
            },
            'm2m': {
                'realized': funds['m2m_realized'],
                'unrealized': funds['m2m_unrealized'],
            },
            'filtered_positions': filtered,
            'funds': funds,
        }

    async def capture_snapshot(
        self,
        config: DailyConfig,
        db: AsyncSession
    ) -> Optional[MarginSnapshot]:
        """
        Capture a margin snapshot and store it.

        Args:
            config: Daily configuration
            db: Database session

        Returns:
            Created MarginSnapshot or None if error.
        """
        try:
            # Get current margin data
            data = await self.get_current_margin(config, db)

            # Create snapshot
            snapshot = MarginSnapshot(
                config_id=config.id,
                timestamp=now_ist(),
                total_margin_used=data['funds']['used_margin'],
                available_cash=data['funds']['available_cash'],
                collateral=data['funds']['collateral'],
                m2m_realized=data['funds']['m2m_realized'],
                m2m_unrealized=data['funds']['m2m_unrealized'],
                baseline_margin=data['margin']['baseline'],
                intraday_margin=data['margin']['intraday_used'],
                utilization_pct=data['margin']['utilization_pct'],
                short_positions_count=data['positions']['short_count'],
                short_positions_qty=data['positions']['short_qty'],
                long_positions_count=data['positions']['long_count'],
                long_positions_qty=data['positions']['long_qty'],
                closed_positions_count=data['positions']['closed_count'],
                total_hedge_cost=data['positions']['hedge_cost'],
                total_pnl=data['positions']['total_pnl'],
            )

            db.add(snapshot)
            await db.flush()

            # Store position details
            for category in ['short_positions', 'long_positions', 'closed_positions']:
                for pos in data['filtered_positions'][category]:
                    parsed = parse_symbol(pos['symbol'])
                    if parsed:
                        pos_snapshot = PositionSnapshot(
                            snapshot_id=snapshot.id,
                            symbol=pos['symbol'],
                            exchange=pos['exchange'],
                            product=pos['product'],
                            quantity=pos['quantity'],
                            average_price=pos['average_price'],
                            ltp=pos['ltp'],
                            pnl=pos['pnl'],
                            position_type=get_position_type(pos['quantity']),
                            option_type=parsed.option_type,
                            strike_price=parsed.strike,
                            expiry_date=datetime.strptime(parsed.expiry_date, '%Y-%m-%d').date(),
                        )
                        db.add(pos_snapshot)

            await db.commit()
            logger.info(f"Captured snapshot: utilization={data['margin']['utilization_pct']:.1f}%")

            return snapshot

        except Exception as e:
            logger.error(f"Failed to capture snapshot: {e}")
            await db.rollback()

            # Create error snapshot
            try:
                error_snapshot = MarginSnapshot(
                    config_id=config.id,
                    timestamp=now_ist(),
                    total_margin_used=0,
                    available_cash=0,
                    collateral=0,
                    baseline_margin=config.baseline_margin or 0,
                    intraday_margin=0,
                    utilization_pct=0,
                    error_message=str(e),
                )
                db.add(error_snapshot)
                await db.commit()
            except Exception:
                pass

            return None

    async def generate_daily_summary(
        self,
        config: DailyConfig,
        db: AsyncSession
    ) -> Optional[DailySummary]:
        """
        Generate end-of-day summary from snapshots.

        Args:
            config: Daily configuration
            db: Database session

        Returns:
            Created DailySummary or None if error.
        """
        try:
            # Get all snapshots for today
            result = await db.execute(
                select(MarginSnapshot)
                .where(MarginSnapshot.config_id == config.id)
                .where(MarginSnapshot.error_message.is_(None))
                .order_by(MarginSnapshot.timestamp)
            )
            snapshots = result.scalars().all()

            if not snapshots:
                logger.warning(f"No snapshots found for config {config.id}")
                return None

            # Calculate metrics
            intraday_margins = [s.intraday_margin for s in snapshots]
            utilizations = [s.utilization_pct for s in snapshots]

            max_intraday = max(intraday_margins)
            max_utilization = max(utilizations)
            avg_utilization = sum(utilizations) / len(utilizations)

            max_short_count = max(s.short_positions_count for s in snapshots)
            max_long_count = max(s.long_positions_count for s in snapshots)

            # Get last snapshot for final P&L
            last_snapshot = snapshots[-1]

            # Create or update summary
            existing = await db.execute(
                select(DailySummary).where(DailySummary.config_id == config.id)
            )
            summary = existing.scalar_one_or_none()

            if summary:
                # Update existing
                summary.max_intraday_margin = max_intraday
                summary.max_utilization_pct = max_utilization
                summary.avg_utilization_pct = avg_utilization
                summary.max_short_count = max_short_count
                summary.max_long_count = max_long_count
                summary.total_closed_count = last_snapshot.closed_positions_count
                summary.total_hedge_cost = last_snapshot.total_hedge_cost
                summary.max_hedge_count = max_long_count
                summary.total_pnl = last_snapshot.total_pnl
                summary.first_position_time = snapshots[0].timestamp
                summary.last_position_time = last_snapshot.timestamp
            else:
                # Create new
                summary = DailySummary(
                    config_id=config.id,
                    date=config.date,
                    day_of_week=config.day_of_week,
                    day_name=config.day_name,
                    index_name=config.index_name,
                    num_baskets=config.num_baskets,
                    total_budget=config.total_budget,
                    baseline_margin=config.baseline_margin or 0,
                    max_intraday_margin=max_intraday,
                    max_utilization_pct=max_utilization,
                    avg_utilization_pct=avg_utilization,
                    total_hedge_cost=last_snapshot.total_hedge_cost,
                    max_hedge_count=max_long_count,
                    max_short_count=max_short_count,
                    max_long_count=max_long_count,
                    total_closed_count=last_snapshot.closed_positions_count,
                    total_pnl=last_snapshot.total_pnl,
                    first_position_time=snapshots[0].timestamp,
                    last_position_time=last_snapshot.timestamp,
                )
                db.add(summary)

            await db.commit()
            logger.info(f"Generated EOD summary: max_utilization={max_utilization:.1f}%")

            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            await db.rollback()
            return None


# Global service instance
margin_service = MarginService()
