"""
Margin Monitor - Analytics Service

Provides day-of-week and historical analytics.
"""

import logging
from datetime import date, timedelta
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.db_models import DailySummary

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analytics and historical analysis."""

    async def get_day_of_week_analytics(
        self,
        db: AsyncSession,
        period_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get analytics grouped by day of week.

        Args:
            db: Database session
            period_days: Number of days to look back (default 30)

        Returns:
            List of analytics per day of week.
        """
        cutoff_date = date.today() - timedelta(days=period_days)

        result = await db.execute(
            select(
                DailySummary.day_name,
                DailySummary.index_name,
                func.count(DailySummary.id).label('trading_days'),
                func.avg(DailySummary.max_utilization_pct).label('avg_max_utilization'),
                func.avg(DailySummary.total_hedge_cost).label('avg_hedge_cost'),
                func.avg(DailySummary.total_pnl).label('avg_pnl'),
            )
            .where(DailySummary.date >= cutoff_date)
            .group_by(DailySummary.day_name, DailySummary.index_name, DailySummary.day_of_week)
            .order_by(DailySummary.day_of_week)
        )

        rows = result.all()

        analytics = []
        for row in rows:
            analytics.append({
                'day_name': row.day_name,
                'index_name': row.index_name,
                'trading_days': row.trading_days,
                'avg_max_utilization': round(row.avg_max_utilization or 0, 1),
                'avg_hedge_cost': round(row.avg_hedge_cost or 0, 2),
                'avg_pnl': round(row.avg_pnl or 0, 2),
            })

        return analytics

    async def get_date_range_summaries(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get daily summaries for a date range.

        Args:
            db: Database session
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of daily summary dictionaries.
        """
        result = await db.execute(
            select(DailySummary)
            .where(DailySummary.date >= start_date)
            .where(DailySummary.date <= end_date)
            .order_by(DailySummary.date.desc())
        )

        summaries = result.scalars().all()

        return [
            {
                'date': s.date.strftime('%Y-%m-%d'),
                'day_name': s.day_name,
                'index_name': s.index_name,
                'num_baskets': s.num_baskets,
                'max_utilization_pct': round(s.max_utilization_pct, 1),
                'total_hedge_cost': round(s.total_hedge_cost, 2),
                'total_pnl': round(s.total_pnl, 2),
            }
            for s in summaries
        ]


# Global service instance
analytics_service = AnalyticsService()
