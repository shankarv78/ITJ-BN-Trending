"""
Synchronous Bridge for Dual-Channel Confirmation Manager

Allows synchronous code (like LiveTradingEngine) to use the async
DualChannelConfirmationManager by running coroutines in the bot's event loop.

Usage:
    # In async context (bot setup)
    async_manager = DualChannelConfirmationManager(token, chat_id)
    loop = asyncio.get_event_loop()
    sync_bridge = SyncConfirmationBridge(async_manager, loop)

    # In sync context (engine)
    result = sync_bridge.request_confirmation(
        ConfirmationType.VALIDATION_FAILED,
        context={'instrument': 'GOLDM'},
        options=[...]
    )
"""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from .confirmations import (
    ConfirmationAction,
    ConfirmationOption,
    ConfirmationResult,
    ConfirmationType,
    DualChannelConfirmationManager,
)

logger = logging.getLogger(__name__)


class SyncConfirmationBridge:
    """
    Synchronous bridge for DualChannelConfirmationManager.

    Allows sync code (LiveTradingEngine) to call async confirmation manager.
    Runs the async coroutine in the provided event loop.
    """

    def __init__(
        self,
        async_manager: DualChannelConfirmationManager,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        """
        Initialize the sync bridge.

        Args:
            async_manager: The async DualChannelConfirmationManager
            loop: Event loop to run coroutines in. If None, will try to get/create one.
        """
        self.async_manager = async_manager
        self._loop = loop
        self._loop_thread: Optional[threading.Thread] = None

        logger.info("[SyncBridge] Initialized")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop."""
        if self._loop and not self._loop.is_closed():
            return self._loop

        try:
            # Try to get running loop
            self._loop = asyncio.get_running_loop()
            return self._loop
        except RuntimeError:
            pass

        try:
            # Try to get existing loop
            self._loop = asyncio.get_event_loop()
            if not self._loop.is_closed():
                return self._loop
        except RuntimeError:
            pass

        # Create new loop in a thread
        self._start_loop_thread()
        return self._loop

    def _start_loop_thread(self):
        """Start an event loop in a background thread."""
        if self._loop_thread and self._loop_thread.is_alive():
            return

        self._loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        logger.info("[SyncBridge] Started event loop thread")

    def request_confirmation(
        self,
        confirmation_type: ConfirmationType,
        context: Dict[str, Any],
        options: List[ConfirmationOption],
        timeout_seconds: Optional[int] = None
    ) -> ConfirmationResult:
        """
        Synchronous wrapper for request_confirmation.

        Blocks the calling thread until user responds or timeout.

        Args:
            confirmation_type: Type of confirmation
            context: Context data to display
            options: List of options to present
            timeout_seconds: Timeout in seconds

        Returns:
            ConfirmationResult with action taken and source
        """
        loop = self._get_loop()

        # Schedule coroutine in the event loop
        future = asyncio.run_coroutine_threadsafe(
            self.async_manager.request_confirmation(
                confirmation_type,
                context,
                options,
                timeout_seconds
            ),
            loop
        )

        # Block with extra buffer for network latency
        effective_timeout = (timeout_seconds or 120) + 15

        try:
            result = future.result(timeout=effective_timeout)
            logger.debug(
                f"[SyncBridge] Confirmation completed: {result.action.value} via {result.source}"
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("[SyncBridge] Confirmation timed out in sync bridge")
            # Return default action
            default_action = ConfirmationAction.CANCEL
            for opt in options:
                if opt.is_default:
                    default_action = opt.action
                    break
            return ConfirmationResult(
                action=default_action,
                confirmation_id="timeout",
                source="sync_timeout",
                response_time_seconds=effective_timeout
            )
        except Exception as e:
            logger.error(f"[SyncBridge] Error in confirmation: {e}")
            # Return default on error
            default_action = ConfirmationAction.CANCEL
            for opt in options:
                if opt.is_default:
                    default_action = opt.action
                    break
            return ConfirmationResult(
                action=default_action,
                confirmation_id="error",
                source="error",
                response_time_seconds=0.0
            )

    def stop(self):
        """Stop the background event loop if we created one."""
        if self._loop and self._loop_thread:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=5)
            logger.info("[SyncBridge] Stopped event loop thread")


# Convenience function to create validation confirmation
def create_validation_options(default_reject: bool = True) -> List[ConfirmationOption]:
    """Create standard options for validation confirmation."""
    return [
        ConfirmationOption(
            ConfirmationAction.REJECT,
            "Reject Signal",
            is_default=default_reject
        ),
        ConfirmationOption(
            ConfirmationAction.EXECUTE_ANYWAY,
            "Execute Anyway",
            is_default=not default_reject
        )
    ]


def create_order_failure_options() -> List[ConfirmationOption]:
    """Create standard options for order failure confirmation."""
    return [
        ConfirmationOption(
            ConfirmationAction.RETRY,
            "Retry Order"
        ),
        ConfirmationOption(
            ConfirmationAction.CANCEL,
            "Cancel",
            is_default=True
        ),
        ConfirmationOption(
            ConfirmationAction.MANUAL,
            "Manual Override"
        )
    ]


def create_exit_failure_options() -> List[ConfirmationOption]:
    """Create standard options for exit failure confirmation."""
    return [
        ConfirmationOption(
            ConfirmationAction.RETRY,
            "Retry Exit"
        ),
        ConfirmationOption(
            ConfirmationAction.MANUAL,
            "Manual Close",
            is_default=True
        ),
        ConfirmationOption(
            ConfirmationAction.CANCEL,
            "Keep Position"
        )
    ]


def create_zero_lots_options() -> List[ConfirmationOption]:
    """Create standard options for zero lots confirmation."""
    return [
        ConfirmationOption(
            ConfirmationAction.FORCE_ONE_LOT,
            "Force 1 Lot"
        ),
        ConfirmationOption(
            ConfirmationAction.SKIP,
            "Skip Signal",
            is_default=True
        )
    ]
