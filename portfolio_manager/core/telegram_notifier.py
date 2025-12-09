"""
Telegram Notifier - Mobile Alerts for Portfolio Manager

Sends notifications for:
- INFO: Signals, orders, positions, daily summaries
- ALERTS: Failures, warnings, errors
- Commands: /status, /positions, /pause, /resume
"""
import logging
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum
from queue import Queue

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications"""
    INFO = "info"
    ALERT = "alert"
    TRADE = "trade"
    ERROR = "error"
    DAILY_SUMMARY = "daily_summary"


class TelegramNotifier:
    """
    Telegram Bot for Portfolio Manager notifications

    Features:
    - Send INFO messages (signals, orders, positions)
    - Send ALERT messages (failures, warnings)
    - Handle commands (/status, /positions, /pause, /resume)
    - Queue-based async sending
    """

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True,
        engine=None  # LiveTradingEngine reference for commands
    ):
        """
        Initialize TelegramNotifier

        Args:
            bot_token: Telegram bot token from BotFather
            chat_id: Chat ID to send messages to
            enabled: Whether notifications are enabled
            engine: LiveTradingEngine reference for handling commands
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.engine = engine

        # Message queue for async sending
        self._message_queue: Queue = Queue()
        self._sender_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Command handlers
        self._command_handlers: Dict = {}
        self._register_default_commands()

        # Start sender thread
        if enabled and bot_token and chat_id:
            self._start_sender()
            logger.info(f"[TELEGRAM] Notifier initialized (chat_id: {chat_id})")
        else:
            logger.warning("[TELEGRAM] Notifier disabled or missing credentials")

    def _start_sender(self):
        """Start background sender thread"""
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()

    def _sender_loop(self):
        """Background loop to send queued messages"""
        while not self._stop_event.is_set():
            try:
                # Get message with timeout
                message = self._message_queue.get(timeout=1.0)
                self._send_message_sync(message)
            except Exception:
                pass  # Timeout or error, continue

    def _send_message_sync(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send message synchronously

        Args:
            text: Message text
            parse_mode: HTML or Markdown

        Returns:
            True if sent successfully
        """
        if not self.enabled or not self.bot_token:
            return False

        try:
            url = self.TELEGRAM_API_URL.format(token=self.bot_token, method="sendMessage")
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                return True
            else:
                logger.error(f"[TELEGRAM] Send failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"[TELEGRAM] Send error: {e}")
            return False

    def _queue_message(self, text: str):
        """Add message to queue for async sending"""
        if self.enabled:
            self._message_queue.put(text)

    # =========================================================================
    # Public Send Methods
    # =========================================================================

    def send_info(self, message: str):
        """Send INFO notification"""
        text = f"ℹ️ <b>INFO</b>\n{message}"
        self._queue_message(text)

    def send_alert(self, message: str):
        """Send ALERT notification (high priority)"""
        text = f"🚨 <b>ALERT</b>\n{message}"
        self._queue_message(text)

    def send_trade(self, action: str, instrument: str, lots: int, price: float, pnl: Optional[float] = None):
        """
        Send trade notification

        Args:
            action: "ENTRY", "PYRAMID", "EXIT"
            instrument: Instrument name
            lots: Number of lots
            price: Execution price
            pnl: P&L for exits
        """
        emoji = "📈" if action in ["ENTRY", "PYRAMID"] else "📉"

        text = (
            f"{emoji} <b>TRADE {action}</b>\n"
            f"Instrument: {instrument}\n"
            f"Lots: {lots}\n"
            f"Price: ₹{price:,.2f}"
        )

        if pnl is not None:
            pnl_emoji = "✅" if pnl >= 0 else "❌"
            text += f"\n{pnl_emoji} P&L: ₹{pnl:,.2f}"

        self._queue_message(text)

    def send_signal_received(self, instrument: str, signal_type: str, price: float, suggested_lots: int):
        """Send notification for received signal"""
        text = (
            f"📡 <b>SIGNAL RECEIVED</b>\n"
            f"Type: {signal_type}\n"
            f"Instrument: {instrument}\n"
            f"Price: ₹{price:,.2f}\n"
            f"Suggested Lots: {suggested_lots}"
        )
        self._queue_message(text)

    def send_order_placed(self, instrument: str, action: str, lots: int, order_type: str, price: float):
        """Send notification for order placed at broker"""
        text = (
            f"📤 <b>ORDER PLACED</b>\n"
            f"Instrument: {instrument}\n"
            f"Action: {action}\n"
            f"Lots: {lots}\n"
            f"Type: {order_type}\n"
            f"Price: ₹{price:,.2f}"
        )
        self._queue_message(text)

    def send_order_executed(self, instrument: str, action: str, lots: int, price: float, order_id: str = None):
        """Send notification for order executed"""
        text = (
            f"✅ <b>ORDER EXECUTED</b>\n"
            f"Instrument: {instrument}\n"
            f"Action: {action}\n"
            f"Lots: {lots}\n"
            f"Price: ₹{price:,.2f}"
        )
        if order_id:
            text += f"\nOrder ID: {order_id}"
        self._queue_message(text)

    def send_order_failed(self, instrument: str, action: str, reason: str):
        """Send notification for order failure"""
        text = (
            f"❌ <b>ORDER FAILED</b>\n"
            f"Instrument: {instrument}\n"
            f"Action: {action}\n"
            f"Reason: {reason}"
        )
        self._queue_message(text)

    def send_margin_warning(self, utilization: float, threshold: float):
        """Send margin warning notification"""
        text = (
            f"⚠️ <b>MARGIN WARNING</b>\n"
            f"Utilization: {utilization:.1f}%\n"
            f"Threshold: {threshold:.0f}%"
        )
        self._queue_message(text)

    def send_sync_discrepancy(self, pm_positions: Dict, broker_positions: Dict, discrepancies: List[str]):
        """Send sync discrepancy alert"""
        text = (
            f"🔄 <b>SYNC DISCREPANCY</b>\n"
            f"PM Positions: {len(pm_positions)}\n"
            f"Broker Positions: {len(broker_positions)}\n"
            f"Issues:\n" + "\n".join(f"• {d}" for d in discrepancies[:5])
        )
        if len(discrepancies) > 5:
            text += f"\n... and {len(discrepancies) - 5} more"
        self._queue_message(text)

    def send_daily_summary(
        self,
        equity: float,
        daily_pnl: float,
        trades_today: int,
        open_positions: int,
        margin_utilization: float
    ):
        """Send end-of-day summary"""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

        text = (
            f"📊 <b>DAILY SUMMARY</b>\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"💰 Equity: ₹{equity:,.0f}\n"
            f"{pnl_emoji} Daily P&L: ₹{daily_pnl:+,.0f}\n"
            f"📋 Trades Today: {trades_today}\n"
            f"📂 Open Positions: {open_positions}\n"
            f"📊 Margin Used: {margin_utilization:.1f}%"
        )
        self._queue_message(text)

    def send_system_status(self, status: Dict):
        """Send system status"""
        health = status.get('status', 'unknown')
        health_emoji = "✅" if health == 'healthy' else "⚠️"

        text = (
            f"{health_emoji} <b>SYSTEM STATUS</b>\n"
            f"Health: {health}\n"
            f"EOD Scheduler: {status.get('eod_scheduler', 'unknown')}\n"
            f"Rollover Scheduler: {status.get('rollover_scheduler', 'unknown')}\n"
            f"Trading Paused: {status.get('trading_paused', False)}"
        )
        self._queue_message(text)

    # =========================================================================
    # Command Handlers
    # =========================================================================

    def _register_default_commands(self):
        """Register default command handlers"""
        self._command_handlers = {
            '/status': self._cmd_status,
            '/positions': self._cmd_positions,
            '/pause': self._cmd_pause,
            '/resume': self._cmd_resume,
            '/help': self._cmd_help
        }

    def _cmd_status(self) -> str:
        """Handle /status command"""
        if not self.engine:
            return "Engine not available"

        state = self.engine.portfolio.get_current_state()
        return (
            f"📊 <b>Portfolio Status</b>\n"
            f"Equity: ₹{state.equity:,.0f}\n"
            f"Positions: {len(state.get_open_positions())}\n"
            f"Risk: {state.total_risk_percent:.2f}%\n"
            f"Margin Used: {state.margin_utilization_percent:.1f}%"
        )

    def _cmd_positions(self) -> str:
        """Handle /positions command"""
        if not self.engine:
            return "Engine not available"

        state = self.engine.portfolio.get_current_state()
        positions = state.get_open_positions()

        if not positions:
            return "📂 No open positions"

        lines = ["📂 <b>Open Positions</b>"]
        for pos_id, pos in positions.items():
            lines.append(
                f"\n• {pos.instrument}: {pos.lots} lots @ ₹{pos.entry_price:,.2f}"
            )

        return "\n".join(lines)

    def _cmd_pause(self) -> str:
        """Handle /pause command"""
        from core.safety_manager import get_safety_manager
        safety = get_safety_manager()
        if safety:
            safety.pause_trading("Telegram command")
            return "⏸️ Trading paused"
        return "Safety manager not available"

    def _cmd_resume(self) -> str:
        """Handle /resume command"""
        from core.safety_manager import get_safety_manager
        safety = get_safety_manager()
        if safety:
            safety.resume_trading()
            return "▶️ Trading resumed"
        return "Safety manager not available"

    def _cmd_help(self) -> str:
        """Handle /help command"""
        return (
            "🤖 <b>Available Commands</b>\n"
            "/status - Portfolio status\n"
            "/positions - Open positions\n"
            "/pause - Pause trading\n"
            "/resume - Resume trading\n"
            "/help - Show this help"
        )

    def handle_command(self, command: str) -> str:
        """
        Handle incoming command

        Args:
            command: Command string (e.g., "/status")

        Returns:
            Response message
        """
        handler = self._command_handlers.get(command.lower())
        if handler:
            return handler()
        return f"Unknown command: {command}. Use /help for available commands."

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def shutdown(self):
        """Shutdown the notifier"""
        self._stop_event.set()
        if self._sender_thread:
            self._sender_thread.join(timeout=5.0)
        logger.info("[TELEGRAM] Notifier shutdown")


# Global instance
_telegram_notifier: Optional[TelegramNotifier] = None


def init_telegram_notifier(
    bot_token: str,
    chat_id: str,
    enabled: bool = True,
    engine=None
) -> Optional[TelegramNotifier]:
    """Initialize global TelegramNotifier instance"""
    global _telegram_notifier

    if not bot_token or not chat_id:
        logger.warning("[TELEGRAM] Missing bot_token or chat_id, notifier disabled")
        return None

    _telegram_notifier = TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        enabled=enabled,
        engine=engine
    )
    return _telegram_notifier


def get_telegram_notifier() -> Optional[TelegramNotifier]:
    """Get global TelegramNotifier instance"""
    return _telegram_notifier
