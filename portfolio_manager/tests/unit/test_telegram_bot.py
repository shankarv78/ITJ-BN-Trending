"""
Tests for Telegram Bot Components

Tests:
- Alert types and Alert dataclass
- TelegramAlertPublisher (mocked HTTP)
- HeartbeatScheduler logic
- TelegramConfig loading
- TelegramBotFactory
"""

import pytest
import asyncio
from datetime import datetime, time
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from telegram_bot.alerts import (
    Alert,
    AlertType,
    TelegramAlertPublisher,
    SyncAlertPublisher
)
from telegram_bot.heartbeat import HeartbeatScheduler, DailyReportScheduler
from telegram_bot.config import TelegramConfig, TelegramBotFactory


class TestAlertType:
    """Test AlertType enum."""

    def test_all_alert_types_defined(self):
        """Verify all expected alert types exist."""
        expected = [
            'signal_received',
            'signal_processed',
            'signal_rejected',
            'order_executed',
            'order_failed',
            'position_opened',
            'position_closed',
            'system_error',
            'system_warning',
            'heartbeat'
        ]
        actual = [a.value for a in AlertType]
        assert set(expected) == set(actual)


class TestAlert:
    """Test Alert dataclass."""

    def test_basic_alert_creation(self):
        """Test creating a basic alert."""
        alert = Alert(
            alert_type=AlertType.SIGNAL_RECEIVED,
            title="Test Signal",
            message="Signal received"
        )
        assert alert.alert_type == AlertType.SIGNAL_RECEIVED
        assert alert.title == "Test Signal"
        assert alert.message == "Signal received"
        assert alert.timestamp is not None

    def test_alert_with_data(self):
        """Test alert with additional data."""
        alert = Alert(
            alert_type=AlertType.ORDER_EXECUTED,
            title="Order Filled",
            message="Buy 3 lots",
            data={"price": 52000.0, "lots": 3}
        )
        assert alert.data["price"] == 52000.0
        assert alert.data["lots"] == 3

    def test_alert_priority(self):
        """Test alert priority."""
        low_priority = Alert(
            alert_type=AlertType.HEARTBEAT,
            title="Status",
            message="Running",
            priority=0
        )
        high_priority = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            title="Error",
            message="Critical",
            priority=2
        )
        assert high_priority.priority > low_priority.priority


class TestTelegramAlertPublisher:
    """Test TelegramAlertPublisher (with mocked HTTP)."""

    def test_publisher_initialization(self):
        """Test publisher initialization."""
        publisher = TelegramAlertPublisher(
            bot_token="test_token",
            chat_id="123456",
            enabled=True
        )
        assert publisher.enabled is True
        assert publisher.bot_token == "test_token"
        assert publisher.chat_id == "123456"

    def test_disabled_publisher(self):
        """Test disabled publisher doesn't queue alerts."""
        publisher = TelegramAlertPublisher(
            bot_token="test_token",
            chat_id="123456",
            enabled=False
        )
        alert = Alert(
            alert_type=AlertType.HEARTBEAT,
            title="Test",
            message="Test message"
        )
        result = publisher.queue_alert(alert)
        assert result is False

    def test_enabled_publisher_queues(self):
        """Test enabled publisher queues alerts."""
        publisher = TelegramAlertPublisher(
            bot_token="test_token",
            chat_id="123456",
            enabled=True
        )
        alert = Alert(
            alert_type=AlertType.HEARTBEAT,
            title="Test",
            message="Test message"
        )
        result = publisher.queue_alert(alert)
        assert result is True
        assert publisher._queue.qsize() == 1

    def test_format_alert(self):
        """Test alert formatting."""
        publisher = TelegramAlertPublisher(
            bot_token="test_token",
            chat_id="123456",
            enabled=True
        )
        alert = Alert(
            alert_type=AlertType.ORDER_EXECUTED,
            title="Order Filled",
            message="Buy 3 lots filled",
            data={"fill_price": 52000.0},
            timestamp=datetime(2025, 1, 6, 10, 30, 0)
        )
        formatted = publisher._format_alert(alert)

        assert "Order Filled" in formatted
        assert "10:30:00" in formatted
        assert "Buy 3 lots filled" in formatted
        # Using HTML parse mode - underscores don't need escaping
        assert "fill_price" in formatted

    def test_convenience_methods(self):
        """Test convenience alert methods."""
        publisher = TelegramAlertPublisher(
            bot_token="test_token",
            chat_id="123456",
            enabled=True
        )

        # Test each convenience method queues an alert
        publisher.alert_signal_received("BANK_NIFTY", "BASE_ENTRY", "LONG", 52000.0)
        assert publisher._queue.qsize() == 1

        publisher.alert_signal_processed("BANK_NIFTY", "BASE_ENTRY", 3, 52000.0)
        assert publisher._queue.qsize() == 2

        publisher.alert_signal_rejected("BANK_NIFTY", "PYRAMID", "divergence_high", "REJECTED_VALIDATION")
        assert publisher._queue.qsize() == 3

        publisher.alert_order_executed("GOLD_MINI", "BUY", 2, 92500.0)
        assert publisher._queue.qsize() == 4

        publisher.alert_heartbeat(5000000.0, 2, 5)
        assert publisher._queue.qsize() == 5


class TestSyncAlertPublisher:
    """Test SyncAlertPublisher wrapper."""

    def test_sync_wrapper_delegates(self):
        """Test sync wrapper delegates to async publisher."""
        async_publisher = Mock(spec=TelegramAlertPublisher)
        sync_publisher = SyncAlertPublisher(async_publisher)

        sync_publisher.alert_signal_received("BANK_NIFTY", "ENTRY", "LONG", 52000.0)
        async_publisher.alert_signal_received.assert_called_once_with(
            "BANK_NIFTY", "ENTRY", "LONG", 52000.0
        )


class TestHeartbeatScheduler:
    """Test HeartbeatScheduler."""

    @pytest.fixture
    def mock_alert_publisher(self):
        """Create mock alert publisher."""
        publisher = Mock(spec=TelegramAlertPublisher)
        return publisher

    def test_scheduler_initialization(self, mock_alert_publisher):
        """Test scheduler initialization."""
        scheduler = HeartbeatScheduler(
            alert_publisher=mock_alert_publisher,
            interval_minutes=60
        )
        assert scheduler.interval_minutes == 60
        assert scheduler._running is False

    def test_market_hours_check_weekday_in_hours(self, mock_alert_publisher):
        """Test market hours check during weekday trading hours."""
        scheduler = HeartbeatScheduler(
            alert_publisher=mock_alert_publisher,
            market_open=time(9, 15),
            market_close=time(15, 30),
            mcx_close=time(23, 30)
        )

        # Mock datetime to a weekday during market hours
        with patch('telegram_bot.heartbeat.datetime') as mock_dt:
            mock_now = Mock()
            mock_now.weekday.return_value = 1  # Tuesday
            mock_now.time.return_value = time(10, 30)
            mock_dt.now.return_value = mock_now

            assert scheduler.is_market_hours() is True

    def test_market_hours_check_weekend(self, mock_alert_publisher):
        """Test market hours returns False on weekend."""
        scheduler = HeartbeatScheduler(
            alert_publisher=mock_alert_publisher
        )

        with patch('telegram_bot.heartbeat.datetime') as mock_dt:
            mock_now = Mock()
            mock_now.weekday.return_value = 5  # Saturday
            mock_dt.now.return_value = mock_now

            assert scheduler.is_market_hours() is False

    def test_should_send_heartbeat_first_time(self, mock_alert_publisher):
        """Test first heartbeat should send."""
        scheduler = HeartbeatScheduler(
            alert_publisher=mock_alert_publisher,
            interval_minutes=60,
            include_weekends=True
        )
        scheduler._last_heartbeat = None

        with patch('telegram_bot.heartbeat.datetime') as mock_dt:
            mock_now = datetime(2025, 1, 6, 10, 30, 0)  # Monday
            mock_dt.now.return_value = mock_now

            # Mock that we're in market hours
            with patch.object(scheduler, 'is_market_hours', return_value=True):
                # First heartbeat should send (no last_heartbeat)
                result = scheduler._should_send_heartbeat()
                assert result is True


class TestDailyReportScheduler:
    """Test DailyReportScheduler."""

    @pytest.fixture
    def mock_alert_publisher(self):
        """Create mock alert publisher."""
        publisher = Mock(spec=TelegramAlertPublisher)
        return publisher

    def test_scheduler_initialization(self, mock_alert_publisher):
        """Test scheduler initialization."""
        scheduler = DailyReportScheduler(
            alert_publisher=mock_alert_publisher,
            report_time=time(16, 0)
        )
        assert scheduler.report_time == time(16, 0)
        assert scheduler._running is False

    def test_should_send_report_weekend(self, mock_alert_publisher):
        """Test report not sent on weekend."""
        scheduler = DailyReportScheduler(
            alert_publisher=mock_alert_publisher
        )

        # Saturday
        now = Mock()
        now.weekday.return_value = 5

        assert scheduler._should_send_report(now) is False


class TestTelegramConfig:
    """Test TelegramConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TelegramConfig()

        assert config.bot_token == ""
        assert config.chat_id == ""
        assert config.enabled is True
        assert config.alerts_enabled is True
        assert config.heartbeat_enabled is True
        assert config.heartbeat_interval_minutes == 60
        assert config.daily_report_hour == 16

    def test_config_from_values(self):
        """Test creating config with values."""
        config = TelegramConfig(
            bot_token="test_token",
            chat_id="12345",
            enabled=True,
            heartbeat_interval_minutes=30
        )

        assert config.bot_token == "test_token"
        assert config.chat_id == "12345"
        assert config.heartbeat_interval_minutes == 30

    def test_is_valid_with_missing_token(self):
        """Test validation fails with missing token."""
        config = TelegramConfig(
            bot_token="",
            chat_id="12345"
        )
        assert config.is_valid() is False

    def test_is_valid_with_missing_chat_id(self):
        """Test validation fails with missing chat_id."""
        config = TelegramConfig(
            bot_token="test_token",
            chat_id=""
        )
        assert config.is_valid() is False

    def test_is_valid_complete(self):
        """Test validation passes with complete config."""
        config = TelegramConfig(
            bot_token="test_token",
            chat_id="12345"
        )
        assert config.is_valid() is True

    def test_to_dict_masks_token(self):
        """Test to_dict masks the bot token."""
        config = TelegramConfig(
            bot_token="1234567890:ABCdefghijklmno",
            chat_id="12345"
        )
        result = config.to_dict()

        # Token should be truncated/masked
        assert result["bot_token"] == "1234567890..."
        assert result["chat_id"] == "12345"


class TestTelegramBotFactory:
    """Test TelegramBotFactory."""

    @pytest.fixture
    def valid_config(self):
        """Create valid config."""
        return TelegramConfig(
            bot_token="test_token",
            chat_id="12345",
            enabled=True,
            alerts_enabled=True,
            heartbeat_enabled=True
        )

    @pytest.fixture
    def invalid_config(self):
        """Create invalid config."""
        return TelegramConfig(
            bot_token="",
            chat_id=""
        )

    def test_factory_initialization(self, valid_config):
        """Test factory initialization."""
        factory = TelegramBotFactory(valid_config)
        assert factory.config == valid_config
        assert factory._bot is None
        assert factory._alert_publisher is None

    def test_create_alert_publisher_valid(self, valid_config):
        """Test creating alert publisher with valid config."""
        factory = TelegramBotFactory(valid_config)
        publisher = factory.create_alert_publisher()

        assert publisher is not None
        assert factory.alert_publisher is not None

    def test_create_alert_publisher_invalid(self, invalid_config):
        """Test creating alert publisher with invalid config fails."""
        factory = TelegramBotFactory(invalid_config)
        publisher = factory.create_alert_publisher()

        assert publisher is None

    def test_disabled_alerts_config(self):
        """Test factory respects disabled alerts config."""
        config = TelegramConfig(
            bot_token="test_token",
            chat_id="12345",
            enabled=True,
            alerts_enabled=False  # Disabled
        )
        factory = TelegramBotFactory(config)
        publisher = factory.create_alert_publisher()

        assert publisher is None
