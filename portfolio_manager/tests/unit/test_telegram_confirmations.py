"""
Unit tests for Telegram Dual-Channel Confirmation Manager

Tests the confirmation types, options, and basic functionality
without requiring actual Telegram connection.
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.confirmations import (
    ConfirmationType,
    ConfirmationAction,
    ConfirmationOption,
    PendingConfirmation,
    ConfirmationResult,
    DualChannelConfirmationManager,
)
from telegram_bot.sync_bridge import (
    SyncConfirmationBridge,
    create_validation_options,
    create_order_failure_options,
    create_exit_failure_options,
    create_zero_lots_options,
)


class TestConfirmationTypes:
    """Test confirmation type enums."""

    def test_confirmation_types_exist(self):
        """All expected confirmation types are defined."""
        assert ConfirmationType.VALIDATION_FAILED
        assert ConfirmationType.ORDER_FAILED
        assert ConfirmationType.EXIT_FAILED
        assert ConfirmationType.ROLLBACK_FAILED
        assert ConfirmationType.PARTIAL_FILL
        assert ConfirmationType.SLIPPAGE_EXCEEDED
        assert ConfirmationType.ZERO_LOTS
        assert ConfirmationType.MISSING_SYMBOLS

    def test_confirmation_type_values(self):
        """Confirmation types have expected string values."""
        assert ConfirmationType.VALIDATION_FAILED.value == "validation_failed"
        assert ConfirmationType.ORDER_FAILED.value == "order_failed"
        assert ConfirmationType.ROLLBACK_FAILED.value == "rollback_failed"


class TestConfirmationActions:
    """Test confirmation action enums."""

    def test_universal_actions(self):
        """Universal actions are defined."""
        assert ConfirmationAction.CANCEL
        assert ConfirmationAction.RETRY
        assert ConfirmationAction.MANUAL

    def test_validation_actions(self):
        """Validation-specific actions are defined."""
        assert ConfirmationAction.EXECUTE_ANYWAY
        assert ConfirmationAction.REJECT

    def test_order_actions(self):
        """Order-specific actions are defined."""
        assert ConfirmationAction.ACCEPT_SLIPPAGE
        assert ConfirmationAction.MARKET_ORDER
        assert ConfirmationAction.FORCE_ONE_LOT
        assert ConfirmationAction.SKIP


class TestConfirmationOption:
    """Test ConfirmationOption dataclass."""

    def test_basic_option(self):
        """Create a basic confirmation option."""
        opt = ConfirmationOption(
            action=ConfirmationAction.CANCEL,
            label="Cancel"
        )
        assert opt.action == ConfirmationAction.CANCEL
        assert opt.label == "Cancel"
        assert opt.is_default is False

    def test_default_option(self):
        """Create a default confirmation option."""
        opt = ConfirmationOption(
            action=ConfirmationAction.REJECT,
            label="Reject Signal",
            is_default=True
        )
        assert opt.is_default is True


class TestPendingConfirmation:
    """Test PendingConfirmation dataclass."""

    def test_create_pending(self):
        """Create a pending confirmation."""
        options = [
            ConfirmationOption(ConfirmationAction.REJECT, "Reject", is_default=True),
            ConfirmationOption(ConfirmationAction.EXECUTE_ANYWAY, "Execute")
        ]
        pending = PendingConfirmation(
            id="abc123",
            confirmation_type=ConfirmationType.VALIDATION_FAILED,
            context={"instrument": "GOLDM", "reason": "stale"},
            options=options,
            created_at=datetime.now(),
            timeout_seconds=120
        )

        assert pending.id == "abc123"
        assert pending.confirmation_type == ConfirmationType.VALIDATION_FAILED
        assert len(pending.options) == 2
        assert pending.timeout_seconds == 120
        assert pending.result is None
        assert pending.result_source is None


class TestConfirmationResult:
    """Test ConfirmationResult dataclass."""

    def test_create_result(self):
        """Create a confirmation result."""
        result = ConfirmationResult(
            action=ConfirmationAction.EXECUTE_ANYWAY,
            confirmation_id="abc123",
            source="telegram",
            user_id=12345,
            response_time_seconds=5.5
        )

        assert result.action == ConfirmationAction.EXECUTE_ANYWAY
        assert result.confirmation_id == "abc123"
        assert result.source == "telegram"
        assert result.user_id == 12345
        assert result.response_time_seconds == 5.5


class TestOptionFactories:
    """Test convenience option factory functions."""

    def test_validation_options(self):
        """Create validation options with default reject."""
        options = create_validation_options(default_reject=True)

        assert len(options) == 2
        assert options[0].action == ConfirmationAction.REJECT
        assert options[0].is_default is True
        assert options[1].action == ConfirmationAction.EXECUTE_ANYWAY
        assert options[1].is_default is False

    def test_validation_options_default_execute(self):
        """Create validation options with default execute."""
        options = create_validation_options(default_reject=False)

        assert options[0].is_default is False
        assert options[1].is_default is True

    def test_order_failure_options(self):
        """Create order failure options."""
        options = create_order_failure_options()

        assert len(options) == 3
        actions = [o.action for o in options]
        assert ConfirmationAction.RETRY in actions
        assert ConfirmationAction.CANCEL in actions
        assert ConfirmationAction.MANUAL in actions

        # Cancel should be default
        default = next(o for o in options if o.is_default)
        assert default.action == ConfirmationAction.CANCEL

    def test_exit_failure_options(self):
        """Create exit failure options."""
        options = create_exit_failure_options()

        assert len(options) == 3
        actions = [o.action for o in options]
        assert ConfirmationAction.RETRY in actions
        assert ConfirmationAction.MANUAL in actions
        assert ConfirmationAction.CANCEL in actions

    def test_zero_lots_options(self):
        """Create zero lots options."""
        options = create_zero_lots_options()

        assert len(options) == 2
        actions = [o.action for o in options]
        assert ConfirmationAction.FORCE_ONE_LOT in actions
        assert ConfirmationAction.SKIP in actions

        # Skip should be default
        default = next(o for o in options if o.is_default)
        assert default.action == ConfirmationAction.SKIP


class TestDualChannelConfirmationManager:
    """Test DualChannelConfirmationManager."""

    def test_init(self):
        """Initialize confirmation manager."""
        manager = DualChannelConfirmationManager(
            bot_token="test_token",
            chat_id="123456",
            default_timeout=60,
            enable_macos=False,
            enable_telegram=True
        )

        assert manager.bot_token == "test_token"
        assert manager.chat_id == "123456"
        assert manager.default_timeout == 60
        assert manager.enable_telegram is True
        assert manager.pending == {}

    def test_get_default_action(self):
        """Test getting default action from options."""
        manager = DualChannelConfirmationManager(
            bot_token="test",
            chat_id="123"
        )

        options = [
            ConfirmationOption(ConfirmationAction.RETRY, "Retry"),
            ConfirmationOption(ConfirmationAction.CANCEL, "Cancel", is_default=True),
        ]

        default = manager._get_default_action(options)
        assert default == ConfirmationAction.CANCEL

    def test_get_default_action_fallback(self):
        """Test default action falls back to first option if no default."""
        manager = DualChannelConfirmationManager(
            bot_token="test",
            chat_id="123"
        )

        options = [
            ConfirmationOption(ConfirmationAction.RETRY, "Retry"),
            ConfirmationOption(ConfirmationAction.CANCEL, "Cancel"),
        ]

        default = manager._get_default_action(options)
        assert default == ConfirmationAction.RETRY

    def test_format_telegram_message(self):
        """Test Telegram message formatting."""
        manager = DualChannelConfirmationManager(
            bot_token="test",
            chat_id="123"
        )

        pending = PendingConfirmation(
            id="abc123",
            confirmation_type=ConfirmationType.VALIDATION_FAILED,
            context={"Instrument": "GOLDM", "Reason": "Signal Stale"},
            options=[],
            created_at=datetime.now(),
            timeout_seconds=120
        )

        message = manager._format_telegram_message(pending)

        assert "VALIDATION FAILED" in message
        assert "Instrument" in message
        assert "GOLDM" in message
        assert "120" in message

    def test_escape_html(self):
        """Test HTML escaping for Telegram."""
        manager = DualChannelConfirmationManager(
            bot_token="test",
            chat_id="123"
        )

        # Test special characters
        assert manager._escape_html("a < b") == "a &lt; b"
        assert manager._escape_html("a > b") == "a &gt; b"
        assert manager._escape_html("a & b") == "a &amp; b"


class TestSyncConfirmationBridge:
    """Test SyncConfirmationBridge."""

    def test_init(self):
        """Initialize sync bridge."""
        async_manager = MagicMock()
        bridge = SyncConfirmationBridge(async_manager)

        assert bridge.async_manager == async_manager

    def test_stop(self):
        """Test stopping the bridge."""
        async_manager = MagicMock()
        bridge = SyncConfirmationBridge(async_manager)

        # Should not raise even if no loop started
        bridge.stop()


class TestAsyncConfirmations:
    """Async tests for confirmation manager."""

    def test_timeout_channel(self):
        """Test timeout channel returns default action."""
        async def run_test():
            manager = DualChannelConfirmationManager(
                bot_token="test",
                chat_id="123",
                enable_macos=False,
                enable_telegram=False
            )

            options = [
                ConfirmationOption(ConfirmationAction.REJECT, "Reject", is_default=True),
                ConfirmationOption(ConfirmationAction.EXECUTE_ANYWAY, "Execute")
            ]

            pending = PendingConfirmation(
                id="test123",
                confirmation_type=ConfirmationType.VALIDATION_FAILED,
                context={},
                options=options,
                created_at=datetime.now(),
                timeout_seconds=0.1  # Very short timeout for test
            )

            result = await manager._timeout_channel(pending)

            assert result.action == ConfirmationAction.REJECT
            assert result.source == "timeout"

        asyncio.run(run_test())

    def test_request_confirmation_no_channels(self):
        """Test request_confirmation with no channels enabled."""
        async def run_test():
            manager = DualChannelConfirmationManager(
                bot_token="test",
                chat_id="123",
                enable_macos=False,
                enable_telegram=False
            )

            options = [
                ConfirmationOption(ConfirmationAction.CANCEL, "Cancel", is_default=True)
            ]

            result = await manager.request_confirmation(
                confirmation_type=ConfirmationType.VALIDATION_FAILED,
                context={"test": "value"},
                options=options,
                timeout_seconds=1
            )

            # Should return default via timeout since no channels enabled
            assert result.action == ConfirmationAction.CANCEL
            assert result.source in ("none", "timeout")  # Either is valid

        asyncio.run(run_test())
