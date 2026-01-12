"""
Heartbeat Scheduler

Sends periodic status updates via Telegram alerts.
- Configurable interval (default: 1 hour)
- Includes equity, positions, today's signals
- Market hours aware (only during trading hours)
"""

import logging
import asyncio
from datetime import datetime, time, timedelta
from typing import Optional, Callable, Any

from telegram_bot.alerts import TelegramAlertPublisher

logger = logging.getLogger(__name__)


class HeartbeatScheduler:
    """
    Scheduler for periodic heartbeat alerts.

    Sends status updates at configurable intervals during market hours.
    """

    def __init__(
        self,
        alert_publisher: TelegramAlertPublisher,
        interval_minutes: int = 60,
        market_open: time = time(9, 15),
        market_close: time = time(15, 30),
        mcx_close: time = time(23, 30),
        include_weekends: bool = False,
        get_status_callback: Optional[Callable[[], dict]] = None
    ):
        """
        Initialize heartbeat scheduler.

        Args:
            alert_publisher: TelegramAlertPublisher for sending alerts
            interval_minutes: Minutes between heartbeats (default: 60)
            market_open: NSE market open time (default: 9:15 AM)
            market_close: NSE market close time (default: 3:30 PM)
            mcx_close: MCX market close time (default: 11:30 PM)
            include_weekends: Send heartbeats on weekends (default: False)
            get_status_callback: Callback to get current status dict
        """
        self.alert_publisher = alert_publisher
        self.interval_minutes = interval_minutes
        self.market_open = market_open
        self.market_close = market_close
        self.mcx_close = mcx_close
        self.include_weekends = include_weekends
        self.get_status_callback = get_status_callback

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_heartbeat: Optional[datetime] = None

        logger.info(
            f"[Heartbeat] Initialized with {interval_minutes}min interval, "
            f"market hours {market_open}-{market_close} (MCX till {mcx_close})"
        )

    async def start(self):
        """Start the heartbeat scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("[Heartbeat] Scheduler started")

    async def stop(self):
        """Stop the heartbeat scheduler."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[Heartbeat] Scheduler stopped")

    async def _heartbeat_loop(self):
        """Main heartbeat loop."""
        while self._running:
            try:
                # Check if we should send heartbeat
                if self._should_send_heartbeat():
                    await self._send_heartbeat()
                    self._last_heartbeat = datetime.now()

                # Wait for next check (every minute)
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Heartbeat] Error in loop: {e}")
                await asyncio.sleep(60)

    def _should_send_heartbeat(self) -> bool:
        """Check if we should send a heartbeat now."""
        now = datetime.now()

        # Check weekend
        if not self.include_weekends and now.weekday() >= 5:  # Sat=5, Sun=6
            return False

        # Check time since last heartbeat
        if self._last_heartbeat:
            elapsed = (now - self._last_heartbeat).total_seconds() / 60
            if elapsed < self.interval_minutes:
                return False

        # Check market hours (extended for MCX)
        current_time = now.time()

        # Send heartbeat if within extended market hours (9:15 AM to 11:30 PM)
        if current_time < self.market_open:
            return False
        if current_time > self.mcx_close:
            return False

        return True

    async def _send_heartbeat(self):
        """Send heartbeat alert."""
        try:
            # Get status from callback if available
            status = {}
            if self.get_status_callback:
                try:
                    status = self.get_status_callback()
                except Exception as e:
                    logger.warning(f"[Heartbeat] Error getting status: {e}")

            # Send alert
            equity = status.get('equity', 0)
            open_positions = status.get('open_positions', 0)
            signals_today = status.get('signals_today', 0)

            self.alert_publisher.alert_heartbeat(
                equity=equity,
                open_positions=open_positions,
                signals_today=signals_today
            )

            logger.debug(
                f"[Heartbeat] Sent: equity={equity}, positions={open_positions}, "
                f"signals={signals_today}"
            )

        except Exception as e:
            logger.error(f"[Heartbeat] Error sending heartbeat: {e}")

    def send_startup_heartbeat(self):
        """Send immediate startup heartbeat."""
        try:
            status = {}
            if self.get_status_callback:
                status = self.get_status_callback()

            self.alert_publisher.queue_alert(
                self.alert_publisher.publisher.queue_alert if hasattr(self.alert_publisher, 'publisher') else None
            )

            # Use convenience method directly
            self.alert_publisher.alert_heartbeat(
                equity=status.get('equity', 0),
                open_positions=status.get('open_positions', 0),
                signals_today=status.get('signals_today', 0)
            )

            self._last_heartbeat = datetime.now()
            logger.info("[Heartbeat] Startup heartbeat sent")

        except Exception as e:
            logger.error(f"[Heartbeat] Error sending startup heartbeat: {e}")

    def is_market_hours(self) -> bool:
        """Check if currently within market hours."""
        now = datetime.now()

        # Weekend check
        if now.weekday() >= 5:
            return False

        current_time = now.time()

        # NSE hours (9:15 AM - 3:30 PM)
        # MCX hours (9:00 AM - 11:30 PM for Gold/Silver)
        # Use extended hours
        return self.market_open <= current_time <= self.mcx_close

    def get_next_heartbeat_time(self) -> Optional[datetime]:
        """Get estimated time of next heartbeat."""
        if not self._last_heartbeat:
            return None

        return self._last_heartbeat + timedelta(minutes=self.interval_minutes)


class DailyReportScheduler:
    """
    Scheduler for daily summary reports.

    Sends end-of-day summary at configurable time.
    """

    def __init__(
        self,
        alert_publisher: TelegramAlertPublisher,
        report_time: time = time(16, 0),  # 4 PM IST
        get_daily_report_callback: Optional[Callable[[], dict]] = None
    ):
        """
        Initialize daily report scheduler.

        Args:
            alert_publisher: TelegramAlertPublisher for sending alerts
            report_time: Time to send daily report (default: 4 PM)
            get_daily_report_callback: Callback to get daily report data
        """
        self.alert_publisher = alert_publisher
        self.report_time = report_time
        self.get_daily_report_callback = get_daily_report_callback

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_report_date: Optional[datetime] = None

        logger.info(f"[DailyReport] Initialized for {report_time}")

    async def start(self):
        """Start the daily report scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._report_loop())
        logger.info("[DailyReport] Scheduler started")

    async def stop(self):
        """Stop the daily report scheduler."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[DailyReport] Scheduler stopped")

    async def _report_loop(self):
        """Main report loop."""
        while self._running:
            try:
                now = datetime.now()

                # Check if we should send report
                if self._should_send_report(now):
                    await self._send_daily_report()
                    self._last_report_date = now.date()

                # Sleep until next check (every minute)
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DailyReport] Error in loop: {e}")
                await asyncio.sleep(60)

    def _should_send_report(self, now: datetime) -> bool:
        """Check if we should send daily report now."""
        # Skip weekends
        if now.weekday() >= 5:
            return False

        # Check if already sent today
        if self._last_report_date and self._last_report_date == now.date():
            return False

        # Check if past report time
        current_time = now.time()
        if current_time < self.report_time:
            return False

        return True

    async def _send_daily_report(self):
        """Send daily report alert."""
        try:
            report = {}
            if self.get_daily_report_callback:
                try:
                    report = self.get_daily_report_callback()
                except Exception as e:
                    logger.warning(f"[DailyReport] Error getting report: {e}")

            # Format report message
            from telegram_bot.alerts import Alert, AlertType

            lines = [
                f"Date: {datetime.now().strftime('%Y-%m-%d')}",
                "",
                f"Signals Today: {report.get('signals_today', 0)}",
                f"  Processed: {report.get('processed', 0)}",
                f"  Rejected: {report.get('rejected', 0)}",
                "",
                f"Orders Today: {report.get('orders_today', 0)}",
                f"  Executed: {report.get('executed', 0)}",
                f"  Failed: {report.get('failed', 0)}",
                "",
                f"P&L Today: Rs {report.get('pnl_today', 0):,.0f}",
                f"Current Equity: Rs {report.get('equity', 0):,.0f}",
                f"Open Positions: {report.get('open_positions', 0)}"
            ]

            alert = Alert(
                alert_type=AlertType.HEARTBEAT,
                title="Daily Summary",
                message='\n'.join(lines)
            )

            self.alert_publisher.queue_alert(alert)
            logger.info("[DailyReport] Daily report sent")

        except Exception as e:
            logger.error(f"[DailyReport] Error sending report: {e}")
