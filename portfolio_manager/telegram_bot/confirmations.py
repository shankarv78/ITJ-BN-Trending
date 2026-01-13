"""
Dual-Channel Confirmation Manager

Sends confirmations to both macOS dialog AND Telegram simultaneously.
First response wins, other channel is cancelled.

Usage:
    manager = DualChannelConfirmationManager(bot_token, chat_id)
    result = await manager.request_confirmation(
        confirmation_type=ConfirmationType.VALIDATION_FAILED,
        context={'instrument': 'GOLDM', 'reason': 'signal_stale'},
        options=[
            ConfirmationOption(ConfirmationAction.REJECT, "Reject", is_default=True),
            ConfirmationOption(ConfirmationAction.EXECUTE_ANYWAY, "Execute Anyway")
        ]
    )
    # result.action == ConfirmationAction.EXECUTE_ANYWAY
    # result.source == 'telegram' or 'macos' or 'timeout'
"""

import asyncio
import logging
import platform
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

IS_MACOS = platform.system() == 'Darwin'


class ConfirmationType(Enum):
    """Types of confirmations that can be requested."""
    VALIDATION_FAILED = "validation_failed"
    ORDER_FAILED = "order_failed"
    EXIT_FAILED = "exit_failed"
    ROLLBACK_FAILED = "rollback_failed"
    PARTIAL_FILL = "partial_fill"
    SLIPPAGE_EXCEEDED = "slippage_exceeded"
    ZERO_LOTS = "zero_lots"
    MISSING_SYMBOLS = "missing_symbols"


class ConfirmationAction(Enum):
    """Possible actions for confirmations."""
    # Universal actions
    CANCEL = "cancel"
    RETRY = "retry"
    MANUAL = "manual"

    # Validation specific
    EXECUTE_ANYWAY = "execute_anyway"
    REJECT = "reject"

    # Order specific
    ACCEPT_SLIPPAGE = "accept_slippage"
    MARKET_ORDER = "market_order"
    FORCE_ONE_LOT = "force_one_lot"
    SKIP = "skip"
    KEEP_PARTIAL = "keep_partial"

    # Position specific
    DELETE_POSITION = "delete_position"
    MANUAL_FIX = "manual_fix"


@dataclass
class ConfirmationOption:
    """An option presented to the user in a confirmation dialog."""
    action: ConfirmationAction
    label: str
    is_default: bool = False  # Used for timeout - which action to take if no response


@dataclass
class PendingConfirmation:
    """Tracks a pending confirmation request."""
    id: str
    confirmation_type: ConfirmationType
    context: Dict[str, Any]
    options: List[ConfirmationOption]
    created_at: datetime
    timeout_seconds: int

    # State tracking
    telegram_message_id: Optional[int] = None
    telegram_chat_id: Optional[str] = None
    macos_process: Optional[subprocess.Popen] = None
    response_event: asyncio.Event = field(default_factory=asyncio.Event)
    result: Optional[ConfirmationAction] = None
    result_source: Optional[str] = None  # 'telegram', 'macos', or 'timeout'
    cancelled: bool = False


@dataclass
class ConfirmationResult:
    """Result of a confirmation request."""
    action: ConfirmationAction
    confirmation_id: str
    source: str  # 'telegram', 'macos', or 'timeout'
    user_id: Optional[int] = None
    response_time_seconds: float = 0.0


class DualChannelConfirmationManager:
    """
    Manages confirmations across both macOS dialogs and Telegram.

    Both channels race - first response wins.
    """

    # Emoji mapping for confirmation types
    TYPE_EMOJI = {
        ConfirmationType.VALIDATION_FAILED: "Warning",
        ConfirmationType.ORDER_FAILED: "X",
        ConfirmationType.EXIT_FAILED: "Alert",
        ConfirmationType.ROLLBACK_FAILED: "CRITICAL",
        ConfirmationType.PARTIAL_FILL: "Partial",
        ConfirmationType.SLIPPAGE_EXCEEDED: "Slippage",
        ConfirmationType.ZERO_LOTS: "Zero",
        ConfirmationType.MISSING_SYMBOLS: "Missing",
    }

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        default_timeout: int = 120,
        enable_macos: bool = True,
        enable_telegram: bool = True,
        voice_announcer=None
    ):
        """
        Initialize the dual-channel confirmation manager.

        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat ID to send confirmations to
            default_timeout: Default timeout in seconds
            enable_macos: Enable macOS dialog channel
            enable_telegram: Enable Telegram channel
            voice_announcer: Optional VoiceAnnouncer for voice repeat during confirmation
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.default_timeout = default_timeout
        self.enable_macos = enable_macos and IS_MACOS
        self.enable_telegram = enable_telegram
        self.voice_announcer = voice_announcer

        self.pending: Dict[str, PendingConfirmation] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(
            f"[Confirmations] Initialized: macos={self.enable_macos}, "
            f"telegram={self.enable_telegram}, timeout={default_timeout}s"
        )

    async def start(self):
        """Start the confirmation manager (create HTTP client)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            logger.info("[Confirmations] Started")

    async def stop(self):
        """Stop the confirmation manager."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("[Confirmations] Stopped")

    async def request_confirmation(
        self,
        confirmation_type: ConfirmationType,
        context: Dict[str, Any],
        options: List[ConfirmationOption],
        timeout_seconds: Optional[int] = None
    ) -> ConfirmationResult:
        """
        Send confirmation to both channels and wait for first response.

        This is the main entry point. It:
        1. Creates PendingConfirmation
        2. Launches both channels in parallel
        3. Waits for first response (asyncio.wait with FIRST_COMPLETED)
        4. Cancels the other channel
        5. Returns result

        Args:
            confirmation_type: Type of confirmation
            context: Context data to display
            options: List of options to present
            timeout_seconds: Timeout in seconds (uses default if not specified)

        Returns:
            ConfirmationResult with action taken and source
        """
        if self._http_client is None:
            await self.start()

        timeout = timeout_seconds or self.default_timeout
        confirmation_id = str(uuid.uuid4())[:8]

        pending = PendingConfirmation(
            id=confirmation_id,
            confirmation_type=confirmation_type,
            context=context,
            options=options,
            created_at=datetime.now(),
            timeout_seconds=timeout
        )
        self.pending[confirmation_id] = pending

        logger.info(
            f"[Confirmations] Request {confirmation_id}: {confirmation_type.value} "
            f"(timeout={timeout}s, options={[o.label for o in options]})"
        )

        try:
            # Create tasks for both channels
            tasks = []

            if self.enable_telegram:
                tasks.append(
                    asyncio.create_task(
                        self._telegram_channel(pending),
                        name=f"telegram_{confirmation_id}"
                    )
                )

            if self.enable_macos:
                tasks.append(
                    asyncio.create_task(
                        self._macos_channel(pending),
                        name=f"macos_{confirmation_id}"
                    )
                )

            # Add timeout task
            tasks.append(
                asyncio.create_task(
                    self._timeout_channel(pending),
                    name=f"timeout_{confirmation_id}"
                )
            )

            if not tasks:
                # No channels enabled - return default immediately
                default_action = self._get_default_action(options)
                return ConfirmationResult(
                    action=default_action,
                    confirmation_id=confirmation_id,
                    source='none',
                    response_time_seconds=0.0
                )

            # Wait for first to complete
            done, pending_tasks = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Get result from completed task
            completed_task = done.pop()
            result = completed_task.result()

            # Clean up the other channel
            await self._cleanup(pending)

            logger.info(
                f"[Confirmations] Resolved {confirmation_id}: "
                f"action={result.action.value}, source={result.source}, "
                f"time={result.response_time_seconds:.1f}s"
            )

            return result

        except Exception as e:
            logger.error(f"[Confirmations] Error in request {confirmation_id}: {e}")
            # Return default on error
            default_action = self._get_default_action(options)
            return ConfirmationResult(
                action=default_action,
                confirmation_id=confirmation_id,
                source='error',
                response_time_seconds=0.0
            )
        finally:
            if confirmation_id in self.pending:
                del self.pending[confirmation_id]

    async def _telegram_channel(self, pending: PendingConfirmation) -> ConfirmationResult:
        """Send Telegram message and wait for callback."""
        try:
            # Send message with inline keyboard
            message = self._format_telegram_message(pending)
            keyboard = self._build_telegram_keyboard(pending)

            # Send via Telegram API
            msg_id = await self._send_telegram_message(message, keyboard)
            pending.telegram_message_id = msg_id
            pending.telegram_chat_id = self.chat_id

            logger.debug(f"[Confirmations] Telegram message sent: {msg_id}")

            # Wait for response (set by callback handler)
            await pending.response_event.wait()

            if pending.result_source == 'telegram':
                return ConfirmationResult(
                    action=pending.result,
                    confirmation_id=pending.id,
                    source='telegram',
                    response_time_seconds=(datetime.now() - pending.created_at).total_seconds()
                )
            else:
                # Another channel won - this will be cancelled
                raise asyncio.CancelledError()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Confirmations] Telegram channel error: {e}")
            raise

    async def _macos_channel(self, pending: PendingConfirmation) -> ConfirmationResult:
        """Show macOS dialog and wait for response."""
        try:
            # Build AppleScript
            script = self._build_applescript(pending)

            # Run in executor (blocking subprocess in thread)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._run_macos_dialog,
                pending,
                script
            )

            if pending.cancelled:
                raise asyncio.CancelledError()

            # Parse result
            action = self._parse_macos_result(result, pending.options)
            pending.result = action
            pending.result_source = 'macos'
            pending.response_event.set()

            return ConfirmationResult(
                action=action,
                confirmation_id=pending.id,
                source='macos',
                response_time_seconds=(datetime.now() - pending.created_at).total_seconds()
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Confirmations] macOS channel error: {e}")
            raise

    async def _timeout_channel(self, pending: PendingConfirmation) -> ConfirmationResult:
        """Wait for timeout and return default action."""
        try:
            await asyncio.sleep(pending.timeout_seconds)

            # Find default option
            default_action = self._get_default_action(pending.options)

            logger.info(
                f"[Confirmations] Timeout reached for {pending.id}, "
                f"using default: {default_action.value}"
            )

            return ConfirmationResult(
                action=default_action,
                confirmation_id=pending.id,
                source='timeout',
                response_time_seconds=pending.timeout_seconds
            )
        except asyncio.CancelledError:
            raise

    async def handle_telegram_callback(self, callback_query) -> bool:
        """
        Handle callback from Telegram inline button press.

        Called by bot's callback_query_handler.

        Args:
            callback_query: Telegram CallbackQuery object

        Returns:
            True if callback was handled, False otherwise
        """
        data = callback_query.data  # "confirm:abc123:execute_anyway"
        parts = data.split(':')

        if len(parts) != 3 or parts[0] != 'confirm':
            return False

        confirmation_id = parts[1]
        action_str = parts[2]

        if confirmation_id not in self.pending:
            await callback_query.answer("Confirmation expired or already resolved")
            return False

        pending = self.pending[confirmation_id]

        try:
            # Set result
            pending.result = ConfirmationAction(action_str)
            pending.result_source = 'telegram'
            pending.response_event.set()

            # Answer callback
            await callback_query.answer(f"Selected: {action_str.replace('_', ' ').title()}")

            logger.info(
                f"[Confirmations] Telegram callback received for {confirmation_id}: {action_str}"
            )
            return True

        except ValueError:
            logger.error(f"[Confirmations] Invalid action in callback: {action_str}")
            await callback_query.answer("Invalid action")
            return False

    async def _cleanup(self, pending: PendingConfirmation):
        """Clean up after confirmation resolved."""
        pending.cancelled = True

        # Kill macOS dialog if running
        if pending.macos_process and pending.macos_process.poll() is None:
            try:
                pending.macos_process.terminate()
                pending.macos_process.wait(timeout=2)
                logger.debug(f"[Confirmations] Killed macOS dialog for {pending.id}")
            except Exception as e:
                logger.warning(f"[Confirmations] Failed to kill macOS dialog: {e}")

        # Edit Telegram message to show result
        if pending.telegram_message_id and pending.result:
            try:
                result_text = self._format_resolution_message(pending)
                await self._edit_telegram_message(
                    pending.telegram_message_id,
                    result_text
                )
                logger.debug(f"[Confirmations] Updated Telegram message for {pending.id}")
            except Exception as e:
                logger.warning(f"[Confirmations] Failed to edit Telegram message: {e}")

    def _get_default_action(self, options: List[ConfirmationOption]) -> ConfirmationAction:
        """Get the default action from options."""
        for opt in options:
            if opt.is_default:
                return opt.action
        return options[0].action if options else ConfirmationAction.CANCEL

    def _format_telegram_message(self, pending: PendingConfirmation) -> str:
        """Format confirmation message for Telegram (HTML)."""
        ctx = pending.context
        type_name = pending.confirmation_type.value.replace('_', ' ').upper()
        type_label = self.TYPE_EMOJI.get(pending.confirmation_type, "?")

        lines = [
            f"[{type_label}] <b>{type_name}</b>",
            "",
        ]

        # Add context fields
        for key, value in ctx.items():
            safe_key = self._escape_html(str(key))
            safe_value = self._escape_html(str(value))
            lines.append(f"<b>{safe_key}:</b> {safe_value}")

        lines.extend([
            "",
            f"Timeout: Auto-select default in {pending.timeout_seconds}s",
        ])

        return '\n'.join(lines)

    def _format_resolution_message(self, pending: PendingConfirmation) -> str:
        """Format message showing confirmation was resolved."""
        type_name = pending.confirmation_type.value.replace('_', ' ').upper()
        action_name = pending.result.value.replace('_', ' ').title() if pending.result else 'Unknown'
        source = pending.result_source or 'unknown'
        elapsed = (datetime.now() - pending.created_at).total_seconds()

        return (
            f"[RESOLVED] <b>{type_name}</b>\n\n"
            f"Action: <b>{action_name}</b>\n"
            f"Source: {source}\n"
            f"Response time: {elapsed:.1f}s"
        )

    def _build_telegram_keyboard(self, pending: PendingConfirmation):
        """Build inline keyboard from options."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        buttons = []
        for opt in pending.options:
            callback_data = f"confirm:{pending.id}:{opt.action.value}"
            label = opt.label
            if opt.is_default:
                label = f"{label} (default)"
            buttons.append(InlineKeyboardButton(label, callback_data=callback_data))

        # Arrange buttons in rows (max 2 per row)
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append(buttons[i:i+2])

        return InlineKeyboardMarkup(rows)

    def _build_applescript(self, pending: PendingConfirmation) -> str:
        """Build AppleScript for macOS dialog."""
        ctx = pending.context
        type_name = pending.confirmation_type.value.replace('_', ' ').upper()

        # Build message - escape quotes for AppleScript
        msg_parts = [f"[{type_name}]\\n\\n"]
        for key, value in ctx.items():
            safe_value = str(value).replace('"', '\\"').replace("'", "\\'")
            msg_parts.append(f"{key}: {safe_value}\\n")
        msg_parts.append(f"\\nTimeout: {pending.timeout_seconds}s")
        message = ''.join(msg_parts)

        # Build button list (AppleScript format)
        button_list = ', '.join(f'"{opt.label}"' for opt in pending.options)

        # Find default button
        default_btn = next(
            (opt.label for opt in pending.options if opt.is_default),
            pending.options[0].label if pending.options else "OK"
        )

        script = f'''
        tell application "System Events"
            display dialog "{message}" ¬
                with title "Portfolio Manager Confirmation" ¬
                buttons {{{button_list}}} ¬
                default button "{default_btn}" ¬
                giving up after {pending.timeout_seconds} ¬
                with icon caution
        end tell
        '''
        return script

    def _run_macos_dialog(self, pending: PendingConfirmation, script: str) -> str:
        """Run macOS dialog (blocking, runs in executor)."""
        try:
            process = subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            pending.macos_process = process

            stdout, stderr = process.communicate(timeout=pending.timeout_seconds + 10)

            if pending.cancelled:
                return ""

            return stdout.strip()

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            return ""
        except Exception as e:
            logger.error(f"[Confirmations] macOS dialog error: {e}")
            return ""

    def _parse_macos_result(
        self,
        result: str,
        options: List[ConfirmationOption]
    ) -> ConfirmationAction:
        """Parse macOS dialog result to get selected action."""
        if not result:
            # Timeout or cancelled - return default
            return self._get_default_action(options)

        # Result format: "button returned:Execute Anyway, gave up:false"
        for opt in options:
            if opt.label in result:
                return opt.action

        # Check for "gave up:true" (timeout)
        if "gave up:true" in result:
            return self._get_default_action(options)

        # Default to first option
        return self._get_default_action(options)

    async def _send_telegram_message(self, text: str, keyboard) -> Optional[int]:
        """Send message to Telegram and return message ID."""
        if not self._http_client:
            return None

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            # Serialize keyboard
            keyboard_dict = {
                "inline_keyboard": [
                    [{"text": btn.text, "callback_data": btn.callback_data} for btn in row]
                    for row in keyboard.inline_keyboard
                ]
            }

            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard_dict
            }

            response = await self._http_client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                return data.get("result", {}).get("message_id")
            else:
                logger.error(
                    f"[Confirmations] Telegram send failed: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"[Confirmations] Error sending Telegram message: {e}")
            return None

    async def _edit_telegram_message(self, message_id: int, text: str):
        """Edit a Telegram message to update its content and remove keyboard."""
        if not self._http_client:
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"

            payload = {
                "chat_id": self.chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML"
            }

            response = await self._http_client.post(url, json=payload)

            if response.status_code != 200:
                logger.warning(
                    f"[Confirmations] Telegram edit failed: {response.status_code}"
                )

        except Exception as e:
            logger.warning(f"[Confirmations] Error editing Telegram message: {e}")

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters for Telegram."""
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text
