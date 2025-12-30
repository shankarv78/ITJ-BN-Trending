"""
Margin Monitor - Margin Service

Calculates intraday margin utilization and captures snapshots.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db_models import DailyConfig, MarginSnapshot, PositionSnapshot, DailySummary
from app.services.openalgo_service import openalgo_service, FundsData
from app.services.position_service import position_service
from app.utils.date_utils import now_ist, format_datetime_ist
from app.utils.symbol_parser import parse_symbol, get_position_type

logger = logging.getLogger(__name__)


class MarginService:
    """Service for margin calculations and snapshots."""

    async def get_current_margin(
        self,
        config: DailyConfig,
        db: AsyncSession
    ) -> dict:
        """
        Get current margin status for a config.

        Args:
            config: Daily configuration with baseline
            db: Database session

        Returns:
            Dictionary with margin, positions, and M2M data.
        """
        # Fetch funds from OpenAlgo
        funds = await openalgo_service.get_funds()

        # Calculate intraday margin
        baseline = config.baseline_margin or 0.0
        intraday = funds['used_margin'] - baseline
        utilization = (intraday / config.total_budget) * 100 if config.total_budget > 0 else 0.0
        budget_remaining = config.total_budget - intraday

        # Fetch and filter positions
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
