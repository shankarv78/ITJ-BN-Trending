"""
Telegram Alert Publisher

Sends real-time alerts to Telegram for:
- Signal received/processed/rejected
- Order executions
- System errors
- Heartbeat status

Non-blocking design using asyncio queues.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Alert type classification."""
    SIGNAL_RECEIVED = "signal_received"
    SIGNAL_PROCESSED = "signal_processed"
    SIGNAL_REJECTED = "signal_rejected"
    ORDER_EXECUTED = "order_executed"
    ORDER_FAILED = "order_failed"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    HEARTBEAT = "heartbeat"


@dataclass
class Alert:
    """Alert data structure."""
    alert_type: AlertType
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    priority: int = 0  # Higher = more important

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class TelegramAlertPublisher:
    """
    Non-blocking alert publisher for Telegram.

    Uses asyncio queue to avoid blocking the main trading loop.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True,
        queue_size: int = 100,
        rate_limit_per_minute: int = 20
    ):
        """
        Initialize alert publisher.

        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat ID to send alerts to
            enabled: Whether alerts are enabled
            queue_size: Maximum queue size
            rate_limit_per_minute: Max alerts per minute
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.rate_limit = rate_limit_per_minute

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._sent_count = 0
        self._last_rate_reset = datetime.now()
        self._http_client: Optional[httpx.AsyncClient] = None

        # Alert type emoji mapping
        self._emoji_map = {
            AlertType.SIGNAL_RECEIVED: "",
            AlertType.SIGNAL_PROCESSED: "",
            AlertType.SIGNAL_REJECTED: "",
            AlertType.ORDER_EXECUTED: "",
            AlertType.ORDER_FAILED: "",
            AlertType.POSITION_OPENED: "",
            AlertType.POSITION_CLOSED: "",
            AlertType.SYSTEM_ERROR: "",
            AlertType.SYSTEM_WARNING: "",
            AlertType.HEARTBEAT: ""
        }

        logger.info(f"[TelegramAlerts] Publisher initialized, enabled={enabled}")

    async def start(self):
        """Start the alert publisher background task."""
        if self._running:
            return

        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("[TelegramAlerts] Publisher started")

    async def stop(self):
        """Stop the alert publisher."""
        if not self._running:
            return

        self._running = False

        # Cancel task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Close HTTP client
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("[TelegramAlerts] Publisher stopped")

    def queue_alert(self, alert: Alert) -> bool:
        """
        Queue an alert for sending.

        Non-blocking - returns immediately.

        Args:
            alert: Alert to send

        Returns:
            True if queued successfully
        """
        if not self.enabled:
            return False

        try:
            self._queue.put_nowait(alert)
            logger.debug(f"[TelegramAlerts] Queued: {alert.alert_type.value}")
            return True
        except asyncio.QueueFull:
            logger.warning("[TelegramAlerts] Queue full, dropping alert")
            return False

    async def _process_queue(self):
        """Background task to process alert queue."""
        while self._running:
            try:
                # Wait for alert with timeout
                try:
                    alert = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Check rate limit
                if not self._check_rate_limit():
                    logger.warning("[TelegramAlerts] Rate limited, dropping alert")
                    continue

                # Send alert
                await self._send_alert(alert)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TelegramAlerts] Error processing queue: {e}")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limit."""
        now = datetime.now()

        # Reset counter every minute
        if (now - self._last_rate_reset).total_seconds() >= 60:
            self._sent_count = 0
            self._last_rate_reset = now

        if self._sent_count >= self.rate_limit:
            return False

        self._sent_count += 1
        return True

    async def _send_alert(self, alert: Alert):
        """Send alert to Telegram."""
        try:
            # Format message
            message = self._format_alert(alert)

            # Send via Telegram API using HTML parse mode (safer than Markdown)
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }

            if self._http_client:
                response = await self._http_client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(
                        f"[TelegramAlerts] Failed to send: {response.status_code} - {response.text}"
                    )
                else:
                    logger.debug(f"[TelegramAlerts] Sent: {alert.alert_type.value}")

        except Exception as e:
            logger.error(f"[TelegramAlerts] Error sending alert: {e}")

    def _escape_html(self, text: str) -> str:
        """
        Escape special HTML characters for Telegram HTML parse mode.

        Only need to escape: < > &
        This is much safer than Markdown which has many special characters.
        """
        text = str(text)
        text = text.replace('&', '&amp;')  # Must be first
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

    def _format_alert(self, alert: Alert) -> str:
        """Format alert for Telegram using HTML parse mode."""
        emoji = self._emoji_map.get(alert.alert_type, "")
        timestamp = alert.timestamp.strftime('%H:%M:%S') if alert.timestamp else ""

        # Escape title and message for HTML safety
        safe_title = self._escape_html(alert.title)
        safe_message = self._escape_html(alert.message)

        lines = [
            f"{emoji} <b>{safe_title}</b>",
            f"<i>{timestamp}</i>",
            "",
            safe_message
        ]

        # Add data fields if present
        if alert.data:
            lines.append("")
            for key, value in alert.data.items():
                # Escape key for HTML safety
                safe_key = self._escape_html(key)
                # Format numbers nicely
                if isinstance(value, float):
                    if 'pct' in key.lower() or 'percent' in key.lower():
                        value = f"{value:.2%}"
                    elif 'price' in key.lower() or 'equity' in key.lower() or 'amount' in key.lower():
                        value = f"Rs {value:,.2f}"
                    else:
                        value = f"{value:.2f}"
                else:
                    value = self._escape_html(str(value))
                lines.append(f"{safe_key}: {value}")

        return '\n'.join(lines)

    # Convenience methods for common alerts

    def alert_signal_received(
        self,
        instrument: str,
        signal_type: str,
        position: str,
        price: float
    ):
        """Alert: Signal received from TradingView."""
        alert = Alert(
            alert_type=AlertType.SIGNAL_RECEIVED,
            title=f"{instrument} Signal",
            message=f"Received {signal_type} {position}",
            data={
                "price": price
            }
        )
        self.queue_alert(alert)

    def alert_signal_processed(
        self,
        instrument: str,
        signal_type: str,
        lots: int,
        fill_price: float,
        slippage_pct: Optional[float] = None
    ):
        """Alert: Signal processed successfully."""
        data = {
            "lots": lots,
            "fill_price": fill_price
        }
        if slippage_pct is not None:
            data["slippage_pct"] = slippage_pct

        alert = Alert(
            alert_type=AlertType.SIGNAL_PROCESSED,
            title=f"{instrument} Executed",
            message=f"{signal_type} - {lots} lots filled",
            data=data
        )
        self.queue_alert(alert)

    def alert_signal_rejected(
        self,
        instrument: str,
        signal_type: str,
        reason: str,
        outcome: str
    ):
        """Alert: Signal rejected."""
        alert = Alert(
            alert_type=AlertType.SIGNAL_REJECTED,
            title=f"{instrument} Rejected",
            message=f"{signal_type} not executed",
            data={
                "outcome": outcome,
                "reason": reason[:100]  # Truncate long reasons
            }
        )
        self.queue_alert(alert)

    def alert_order_executed(
        self,
        instrument: str,
        action: str,
        lots: int,
        fill_price: float,
        order_type: str = "LIMIT"
    ):
        """Alert: Order executed."""
        alert = Alert(
            alert_type=AlertType.ORDER_EXECUTED,
            title=f"{instrument} Order Filled",
            message=f"{action} {lots} lots @ Rs {fill_price:,.2f}",
            data={
                "order_type": order_type,
                "fill_price": fill_price
            }
        )
        self.queue_alert(alert)

    def alert_order_failed(
        self,
        instrument: str,
        action: str,
        lots: int,
        reason: str
    ):
        """Alert: Order failed."""
        alert = Alert(
            alert_type=AlertType.ORDER_FAILED,
            title=f"{instrument} Order Failed",
            message=f"{action} {lots} lots rejected",
            data={
                "reason": reason[:100]
            },
            priority=1
        )
        self.queue_alert(alert)

    def alert_position_opened(
        self,
        instrument: str,
        position: str,
        lots: int,
        entry_price: float,
        stop_price: float
    ):
        """Alert: New position opened."""
        alert = Alert(
            alert_type=AlertType.POSITION_OPENED,
            title=f"{instrument} Position Opened",
            message=f"{position} {lots} lots",
            data={
                "entry_price": entry_price,
                "stop_price": stop_price
            }
        )
        self.queue_alert(alert)

    def alert_position_closed(
        self,
        instrument: str,
        position: str,
        lots: int,
        exit_price: float,
        pnl: float
    ):
        """Alert: Position closed."""
        pnl_emoji = "" if pnl >= 0 else ""
        alert = Alert(
            alert_type=AlertType.POSITION_CLOSED,
            title=f"{instrument} Position Closed",
            message=f"{position} {lots} lots - {pnl_emoji} Rs {abs(pnl):,.0f}",
            data={
                "exit_price": exit_price,
                "pnl": pnl
            }
        )
        self.queue_alert(alert)

    def alert_system_error(self, error_type: str, message: str, details: Optional[str] = None):
        """Alert: System error."""
        data = {}
        if details:
            data["details"] = details[:200]

        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            title=f"System Error: {error_type}",
            message=message,
            data=data if data else None,
            priority=2
        )
        self.queue_alert(alert)

    def alert_system_warning(self, warning_type: str, message: str):
        """Alert: System warning."""
        alert = Alert(
            alert_type=AlertType.SYSTEM_WARNING,
            title=f"Warning: {warning_type}",
            message=message,
            priority=1
        )
        self.queue_alert(alert)

    def alert_heartbeat(self, equity: float, open_positions: int, signals_today: int):
        """Alert: Heartbeat/status update."""
        alert = Alert(
            alert_type=AlertType.HEARTBEAT,
            title="PM Status",
            message="System running",
            data={
                "equity": equity,
                "open_positions": open_positions,
                "signals_today": signals_today
            }
        )
        self.queue_alert(alert)


# Synchronous wrapper for non-async code
class SyncAlertPublisher:
    """
    Synchronous wrapper for TelegramAlertPublisher.

    For use in non-async code like LiveTradingEngine.
    """

    def __init__(self, async_publisher: TelegramAlertPublisher):
        """
        Initialize sync wrapper.

        Args:
            async_publisher: TelegramAlertPublisher instance
        """
        self.publisher = async_publisher
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
        return self._loop

    def alert_signal_received(self, *args, **kwargs):
        """Alert: Signal received."""
        self.publisher.alert_signal_received(*args, **kwargs)

    def alert_signal_processed(self, *args, **kwargs):
        """Alert: Signal processed."""
        self.publisher.alert_signal_processed(*args, **kwargs)

    def alert_signal_rejected(self, *args, **kwargs):
        """Alert: Signal rejected."""
        self.publisher.alert_signal_rejected(*args, **kwargs)

    def alert_order_executed(self, *args, **kwargs):
        """Alert: Order executed."""
        self.publisher.alert_order_executed(*args, **kwargs)

    def alert_order_failed(self, *args, **kwargs):
        """Alert: Order failed."""
        self.publisher.alert_order_failed(*args, **kwargs)

    def alert_position_opened(self, *args, **kwargs):
        """Alert: Position opened."""
        self.publisher.alert_position_opened(*args, **kwargs)

    def alert_position_closed(self, *args, **kwargs):
        """Alert: Position closed."""
        self.publisher.alert_position_closed(*args, **kwargs)

    def alert_system_error(self, *args, **kwargs):
        """Alert: System error."""
        self.publisher.alert_system_error(*args, **kwargs)

    def alert_system_warning(self, *args, **kwargs):
        """Alert: System warning."""
        self.publisher.alert_system_warning(*args, **kwargs)

    def alert_heartbeat(self, *args, **kwargs):
        """Alert: Heartbeat."""
        self.publisher.alert_heartbeat(*args, **kwargs)
