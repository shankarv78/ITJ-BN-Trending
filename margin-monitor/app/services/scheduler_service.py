"""
Margin Monitor - Scheduler Service

Manages scheduled jobs for baseline capture, margin polling, and EOD summary.
"""

import logging
import os
import signal
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.config import settings

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')


class SchedulerService:
    """Service for managing scheduled jobs."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=IST)
        self._db_session_maker = None

    def set_db_session_maker(self, session_maker):
        """Set the database session maker."""
        self._db_session_maker = session_maker

    def setup(self):
        """Configure all scheduled jobs."""

        # Baseline capture at 09:15:15 IST
        self.scheduler.add_job(
            self._auto_capture_baseline,
            CronTrigger(day_of_week='mon-fri', hour=9, minute=15, second=15),
            id='baseline_capture',
            replace_existing=True,
            misfire_grace_time=30
        )
        logger.info("Scheduled: baseline_capture at 09:15:15 IST (Mon-Fri)")

        # Margin polling every 5 minutes from 09:20 to 15:30
        self.scheduler.add_job(
            self._capture_snapshot,
            CronTrigger(
                day_of_week='mon-fri',
                hour='9-15',
                minute='0,5,10,15,20,25,30,35,40,45,50,55'
            ),
            id='margin_polling',
            replace_existing=True
        )
        logger.info("Scheduled: margin_polling every 5 min (09:00-15:55 Mon-Fri)")

        # EOD summary at 15:35 IST
        self.scheduler.add_job(
            self._generate_eod_summary,
            CronTrigger(day_of_week='mon-fri', hour=15, minute=35),
            id='eod_summary',
            replace_existing=True
        )
        logger.info("Scheduled: eod_summary at 15:35 IST (Mon-Fri)")

        # Auto-shutdown at 15:40 IST (if enabled)
        if settings.auto_shutdown_after_eod:
            self.scheduler.add_job(
                self._graceful_shutdown,
                CronTrigger(day_of_week='mon-fri', hour=15, minute=40),
                id='auto_shutdown',
                replace_existing=True
            )
            logger.info("Scheduled: auto_shutdown at 15:40 IST (Mon-Fri)")
        else:
            logger.info("Auto-shutdown disabled (set AUTO_SHUTDOWN_AFTER_EOD=true to enable)")

    def start(self):
        """Start the scheduler."""
        self.setup()
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _get_today_config(self, db):
        """Get today's configuration from database."""
        from sqlalchemy import select
        from app.models.db_models import DailyConfig
        from app.utils.date_utils import today_ist

        result = await db.execute(
            select(DailyConfig)
            .where(DailyConfig.date == today_ist())
            .where(DailyConfig.is_active == 1)
        )
        return result.scalar_one_or_none()

    async def _auto_capture_baseline(self):
        """Auto-capture baseline margin at 09:15:15."""
        if not self._db_session_maker:
            logger.error("No database session maker configured")
            return

        from app.services.openalgo_service import openalgo_service
        from app.utils.date_utils import now_ist

        async with self._db_session_maker() as db:
            try:
                config = await self._get_today_config(db)

                if not config:
                    logger.warning("No config for today, skipping baseline capture")
                    return

                if config.baseline_margin is not None:
                    logger.info(f"Baseline already captured: {config.baseline_margin}")
                    return

                # Fetch current margin from OpenAlgo
                funds = await openalgo_service.get_funds()
                baseline = funds['used_margin']

                # Update config with baseline
                config.baseline_margin = baseline
                config.baseline_captured_at = now_ist()
                await db.commit()

                logger.info(f"Baseline captured: {baseline:,.2f}")

            except Exception as e:
                logger.error(f"Failed to capture baseline: {e}")
                await db.rollback()

    async def _capture_snapshot(self):
        """Capture margin snapshot every 5 minutes."""
        if not self._db_session_maker:
            return

        from app.services.margin_service import margin_service
        from app.utils.date_utils import now_ist

        # Skip if outside market hours (extra safety)
        now = now_ist()
        if now.hour < 9 or (now.hour == 9 and now.minute < 20):
            return  # Before 9:20
        if now.hour > 15 or (now.hour == 15 and now.minute > 30):
            return  # After 15:30

        async with self._db_session_maker() as db:
            try:
                config = await self._get_today_config(db)

                if not config:
                    return  # No config, skip

                if config.baseline_margin is None:
                    logger.warning("Baseline not captured yet, skipping snapshot")
                    return

                await margin_service.capture_snapshot(config, db)

            except Exception as e:
                logger.error(f"Failed to capture snapshot: {e}")

    async def _generate_eod_summary(self):
        """Generate end-of-day summary."""
        if not self._db_session_maker:
            return

        from app.services.margin_service import margin_service

        async with self._db_session_maker() as db:
            try:
                config = await self._get_today_config(db)

                if not config:
                    return

                await margin_service.generate_daily_summary(config, db)
                logger.info("EOD summary generated")

            except Exception as e:
                logger.error(f"Failed to generate EOD summary: {e}")

    async def _graceful_shutdown(self):
        """Gracefully shutdown the application after EOD."""
        logger.info("=" * 50)
        logger.info("AUTO-SHUTDOWN: Trading day complete")
        logger.info("EOD summary has been generated")
        logger.info("Initiating graceful shutdown...")
        logger.info("=" * 50)

        # Stop the scheduler first
        self.stop()

        # Give a few seconds for any pending operations
        import asyncio
        await asyncio.sleep(2)

        # Send SIGTERM to self for graceful shutdown
        # This allows FastAPI to properly cleanup
        logger.info("Sending shutdown signal...")
        os.kill(os.getpid(), signal.SIGTERM)


# Global service instance
scheduler_service = SchedulerService()
