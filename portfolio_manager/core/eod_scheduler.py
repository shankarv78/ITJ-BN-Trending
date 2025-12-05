"""
EOD (End-of-Day) Scheduler - Precise Timing for Pre-Close Execution

Uses APScheduler for precise timing of EOD order execution.
Schedules daily jobs for condition checks, order placement, and tracking.

Timeline (per instrument):
- T-45 sec: Final condition check + position sizing
- T-30 sec: Place limit order (if conditions met)
- T-15 sec: Track order to completion

Bank Nifty (NSE): Closes at 15:30 IST
Gold Mini (MCX): Closes at 23:30 IST
"""
import logging
import threading
from datetime import datetime, time, timedelta
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass, field
import pytz

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.executors.pool import ThreadPoolExecutor
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    BackgroundScheduler = None

from core.config import PortfolioConfig

logger = logging.getLogger(__name__)

# IST timezone
IST = pytz.timezone('Asia/Kolkata')


@dataclass
class EODJobResult:
    """Result of an EOD scheduled job"""
    job_type: str  # 'condition_check', 'execution', 'tracking'
    instrument: str
    timestamp: datetime
    success: bool
    result: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class EODScheduleConfig:
    """Configuration for EOD scheduling for one instrument"""
    instrument: str
    close_time: time  # Market close time in IST
    condition_check_offset: int  # Seconds before close for condition check
    execution_offset: int  # Seconds before close for order placement
    tracking_offset: int  # Seconds before close for order tracking

    def get_condition_check_time(self, close_datetime: datetime) -> datetime:
        """Get the condition check time"""
        return close_datetime - timedelta(seconds=self.condition_check_offset)

    def get_execution_time(self, close_datetime: datetime) -> datetime:
        """Get the execution time"""
        return close_datetime - timedelta(seconds=self.execution_offset)

    def get_tracking_time(self, close_datetime: datetime) -> datetime:
        """Get the tracking time"""
        return close_datetime - timedelta(seconds=self.tracking_offset)


class EODScheduler:
    """
    Scheduler for precise EOD pre-close order execution.

    Uses APScheduler's BackgroundScheduler for non-blocking operation.
    Schedules daily jobs at precise times before market close.

    Usage:
        scheduler = EODScheduler(config)
        scheduler.set_callbacks(
            condition_check=engine.eod_condition_check,
            execution=engine.eod_execute,
            tracking=engine.eod_track
        )
        scheduler.start()
        # ... application runs ...
        scheduler.shutdown()
    """

    def __init__(self, config: PortfolioConfig):
        """
        Initialize EOD Scheduler.

        Args:
            config: Portfolio configuration with EOD settings
        """
        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler is required for EOD scheduling. "
                "Install with: pip install APScheduler>=3.10.0"
            )

        self.config = config
        self._lock = threading.Lock()
        self._running = False

        # Callbacks for each phase
        self._condition_check_callback: Optional[Callable] = None
        self._execution_callback: Optional[Callable] = None
        self._tracking_callback: Optional[Callable] = None

        # Job history for debugging
        self._job_history: List[EODJobResult] = []
        self._max_history = 100

        # Initialize scheduler
        self._scheduler = BackgroundScheduler(
            jobstores={'default': MemoryJobStore()},
            executors={'default': ThreadPoolExecutor(max_workers=4)},
            job_defaults={
                'coalesce': False,  # Don't combine missed jobs
                'max_instances': 1,  # Only one instance per job
                'misfire_grace_time': 10  # 10 sec grace for missed jobs
            },
            timezone=IST
        )

        # Build schedule configs for each instrument
        self._schedule_configs: Dict[str, EODScheduleConfig] = {}
        self._build_schedule_configs()

        logger.info("[EOD-Scheduler] Initialized")

    def _build_schedule_configs(self):
        """Build schedule configurations for each enabled instrument"""
        for instrument, enabled in self.config.eod_instruments_enabled.items():
            if not enabled:
                continue

            # Use dynamic close time (handles MCX seasonal timing)
            close_time_str = self.config.get_market_close_time(instrument)
            if not close_time_str:
                logger.warning(f"[EOD-Scheduler] No close time for {instrument}, skipping")
                continue

            # Parse close time (HH:MM format)
            hour, minute = map(int, close_time_str.split(':'))
            close_time = time(hour, minute, 0)

            self._schedule_configs[instrument] = EODScheduleConfig(
                instrument=instrument,
                close_time=close_time,
                condition_check_offset=self.config.eod_condition_check_seconds,
                execution_offset=self.config.eod_execution_seconds,
                tracking_offset=self.config.eod_tracking_seconds
            )

            logger.info(
                f"[EOD-Scheduler] Configured {instrument}: "
                f"close={close_time_str}, "
                f"check=-{self.config.eod_condition_check_seconds}s, "
                f"exec=-{self.config.eod_execution_seconds}s, "
                f"track=-{self.config.eod_tracking_seconds}s"
            )

    def set_callbacks(
        self,
        condition_check: Optional[Callable[[str], EODJobResult]] = None,
        execution: Optional[Callable[[str], EODJobResult]] = None,
        tracking: Optional[Callable[[str], EODJobResult]] = None
    ):
        """
        Set callback functions for each EOD phase.

        Args:
            condition_check: Called at T-45 sec, receives instrument name
            execution: Called at T-30 sec, receives instrument name
            tracking: Called at T-15 sec, receives instrument name

        Callbacks should return EODJobResult or Dict with execution result.
        """
        with self._lock:
            self._condition_check_callback = condition_check
            self._execution_callback = execution
            self._tracking_callback = tracking
            logger.info("[EOD-Scheduler] Callbacks configured")

    def start(self):
        """
        Start the EOD scheduler.

        Schedules daily jobs for all enabled instruments.
        """
        with self._lock:
            if self._running:
                logger.warning("[EOD-Scheduler] Already running")
                return

            if not self.config.eod_enabled:
                logger.info("[EOD-Scheduler] EOD disabled in config, not starting")
                return

            # Schedule jobs for each instrument
            for instrument, schedule_config in self._schedule_configs.items():
                self._schedule_daily_jobs(schedule_config)

            # Start the scheduler
            self._scheduler.start()
            self._running = True

            logger.info(
                f"[EOD-Scheduler] Started with {len(self._schedule_configs)} instruments"
            )

    def _schedule_daily_jobs(self, schedule_config: EODScheduleConfig):
        """
        Schedule daily jobs for one instrument.

        Uses CronTrigger for daily scheduling at specific times.
        """
        instrument = schedule_config.instrument
        close_time = schedule_config.close_time

        # Calculate trigger times
        # T-45 sec: Condition check
        check_hour = close_time.hour
        check_minute = close_time.minute
        check_second = 60 - schedule_config.condition_check_offset
        if check_second < 0:
            check_minute -= 1
            check_second += 60
        if check_minute < 0:
            check_hour -= 1
            check_minute += 60

        # Schedule condition check job
        self._scheduler.add_job(
            func=self._run_condition_check,
            trigger=CronTrigger(
                hour=check_hour,
                minute=check_minute,
                second=check_second,
                timezone=IST
            ),
            id=f"eod_check_{instrument}",
            args=[instrument],
            replace_existing=True
        )

        # T-30 sec: Execution
        exec_hour = close_time.hour
        exec_minute = close_time.minute
        exec_second = 60 - schedule_config.execution_offset
        if exec_second < 0:
            exec_minute -= 1
            exec_second += 60
        if exec_minute < 0:
            exec_hour -= 1
            exec_minute += 60

        # Schedule execution job
        self._scheduler.add_job(
            func=self._run_execution,
            trigger=CronTrigger(
                hour=exec_hour,
                minute=exec_minute,
                second=exec_second,
                timezone=IST
            ),
            id=f"eod_exec_{instrument}",
            args=[instrument],
            replace_existing=True
        )

        # T-15 sec: Tracking
        track_hour = close_time.hour
        track_minute = close_time.minute
        track_second = 60 - schedule_config.tracking_offset
        if track_second < 0:
            track_minute -= 1
            track_second += 60
        if track_minute < 0:
            track_hour -= 1
            track_minute += 60

        # Schedule tracking job
        self._scheduler.add_job(
            func=self._run_tracking,
            trigger=CronTrigger(
                hour=track_hour,
                minute=track_minute,
                second=track_second,
                timezone=IST
            ),
            id=f"eod_track_{instrument}",
            args=[instrument],
            replace_existing=True
        )

        logger.info(
            f"[EOD-Scheduler] Scheduled {instrument}: "
            f"check@{check_hour:02d}:{check_minute:02d}:{check_second:02d}, "
            f"exec@{exec_hour:02d}:{exec_minute:02d}:{exec_second:02d}, "
            f"track@{track_hour:02d}:{track_minute:02d}:{track_second:02d}"
        )

    def _run_condition_check(self, instrument: str):
        """Execute condition check callback"""
        logger.info(f"[EOD-Scheduler] Running condition check for {instrument}")

        result = EODJobResult(
            job_type='condition_check',
            instrument=instrument,
            timestamp=datetime.now(IST),
            success=False
        )

        try:
            if self._condition_check_callback:
                callback_result = self._condition_check_callback(instrument)
                if isinstance(callback_result, EODJobResult):
                    result = callback_result
                elif isinstance(callback_result, dict):
                    result.success = callback_result.get('success', False)
                    result.result = callback_result
                else:
                    result.success = bool(callback_result)
            else:
                logger.warning(f"[EOD-Scheduler] No condition check callback for {instrument}")
                result.error = "No callback configured"

        except Exception as e:
            logger.error(f"[EOD-Scheduler] Condition check failed for {instrument}: {e}")
            result.error = str(e)

        self._record_job_result(result)
        return result

    def _run_execution(self, instrument: str):
        """Execute order placement callback"""
        logger.info(f"[EOD-Scheduler] Running execution for {instrument}")

        result = EODJobResult(
            job_type='execution',
            instrument=instrument,
            timestamp=datetime.now(IST),
            success=False
        )

        try:
            if self._execution_callback:
                callback_result = self._execution_callback(instrument)
                if isinstance(callback_result, EODJobResult):
                    result = callback_result
                elif isinstance(callback_result, dict):
                    result.success = callback_result.get('success', False)
                    result.result = callback_result
                else:
                    result.success = bool(callback_result)
            else:
                logger.warning(f"[EOD-Scheduler] No execution callback for {instrument}")
                result.error = "No callback configured"

        except Exception as e:
            logger.error(f"[EOD-Scheduler] Execution failed for {instrument}: {e}")
            result.error = str(e)

        self._record_job_result(result)
        return result

    def _run_tracking(self, instrument: str):
        """Execute order tracking callback"""
        logger.info(f"[EOD-Scheduler] Running tracking for {instrument}")

        result = EODJobResult(
            job_type='tracking',
            instrument=instrument,
            timestamp=datetime.now(IST),
            success=False
        )

        try:
            if self._tracking_callback:
                callback_result = self._tracking_callback(instrument)
                if isinstance(callback_result, EODJobResult):
                    result = callback_result
                elif isinstance(callback_result, dict):
                    result.success = callback_result.get('success', False)
                    result.result = callback_result
                else:
                    result.success = bool(callback_result)
            else:
                logger.warning(f"[EOD-Scheduler] No tracking callback for {instrument}")
                result.error = "No callback configured"

        except Exception as e:
            logger.error(f"[EOD-Scheduler] Tracking failed for {instrument}: {e}")
            result.error = str(e)

        self._record_job_result(result)
        return result

    def _record_job_result(self, result: EODJobResult):
        """Record job result to history"""
        with self._lock:
            self._job_history.append(result)
            # Trim history if too long
            if len(self._job_history) > self._max_history:
                self._job_history = self._job_history[-self._max_history:]

    def shutdown(self, wait: bool = True):
        """
        Shutdown the scheduler gracefully.

        Args:
            wait: Wait for running jobs to complete (default True)
        """
        with self._lock:
            if not self._running:
                return

            logger.info("[EOD-Scheduler] Shutting down...")
            self._scheduler.shutdown(wait=wait)
            self._running = False
            logger.info("[EOD-Scheduler] Shutdown complete")

    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self._running

    def get_scheduled_jobs(self) -> List[Dict]:
        """
        Get list of scheduled jobs.

        Returns:
            List of job info dictionaries
        """
        if not self._running:
            return []

        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

    def get_job_history(self, instrument: Optional[str] = None) -> List[EODJobResult]:
        """
        Get job execution history.

        Args:
            instrument: Filter by instrument (optional)

        Returns:
            List of EODJobResult objects
        """
        with self._lock:
            if instrument:
                return [r for r in self._job_history if r.instrument == instrument]
            return list(self._job_history)

    def trigger_now(self, instrument: str, job_type: str = 'condition_check') -> EODJobResult:
        """
        Trigger a job immediately (for testing/manual execution).

        Args:
            instrument: Instrument to trigger
            job_type: 'condition_check', 'execution', or 'tracking'

        Returns:
            EODJobResult from the job execution
        """
        if job_type == 'condition_check':
            return self._run_condition_check(instrument)
        elif job_type == 'execution':
            return self._run_execution(instrument)
        elif job_type == 'tracking':
            return self._run_tracking(instrument)
        else:
            return EODJobResult(
                job_type=job_type,
                instrument=instrument,
                timestamp=datetime.now(IST),
                success=False,
                error=f"Unknown job type: {job_type}"
            )

    def get_next_run_times(self, instrument: str) -> Dict[str, Optional[datetime]]:
        """
        Get next scheduled run times for an instrument.

        Args:
            instrument: Instrument to check

        Returns:
            Dict with 'condition_check', 'execution', 'tracking' keys
        """
        result = {
            'condition_check': None,
            'execution': None,
            'tracking': None
        }

        if not self._running:
            return result

        for job in self._scheduler.get_jobs():
            if job.id == f"eod_check_{instrument}":
                result['condition_check'] = job.next_run_time
            elif job.id == f"eod_exec_{instrument}":
                result['execution'] = job.next_run_time
            elif job.id == f"eod_track_{instrument}":
                result['tracking'] = job.next_run_time

        return result

    def pause_instrument(self, instrument: str):
        """Pause all jobs for an instrument"""
        if not self._running:
            return

        for job_type in ['check', 'exec', 'track']:
            job_id = f"eod_{job_type}_{instrument}"
            try:
                self._scheduler.pause_job(job_id)
                logger.info(f"[EOD-Scheduler] Paused {job_id}")
            except Exception as e:
                logger.warning(f"[EOD-Scheduler] Could not pause {job_id}: {e}")

    def resume_instrument(self, instrument: str):
        """Resume all jobs for an instrument"""
        if not self._running:
            return

        for job_type in ['check', 'exec', 'track']:
            job_id = f"eod_{job_type}_{instrument}"
            try:
                self._scheduler.resume_job(job_id)
                logger.info(f"[EOD-Scheduler] Resumed {job_id}")
            except Exception as e:
                logger.warning(f"[EOD-Scheduler] Could not resume {job_id}: {e}")

    def get_status(self) -> Dict:
        """
        Get scheduler status.

        Returns:
            Status dictionary with scheduler state and job info
        """
        return {
            'running': self._running,
            'eod_enabled': self.config.eod_enabled,
            'instruments': list(self._schedule_configs.keys()),
            'jobs': self.get_scheduled_jobs(),
            'history_count': len(self._job_history)
        }
