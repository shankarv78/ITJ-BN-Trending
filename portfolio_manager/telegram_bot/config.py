"""
Telegram Bot Configuration

Handles configuration loading and bot initialization.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Default config file location
DEFAULT_CONFIG_PATH = "telegram_config.json"


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""

    # Required settings
    bot_token: str = ""
    chat_id: str = ""

    # Security
    allowed_user_ids: List[int] = field(default_factory=list)  # Empty = allow all

    # Feature flags
    enabled: bool = True
    alerts_enabled: bool = True
    heartbeat_enabled: bool = True
    daily_report_enabled: bool = True

    # Alert settings
    rate_limit_per_minute: int = 20
    alert_queue_size: int = 100

    # Heartbeat settings
    heartbeat_interval_minutes: int = 60

    # Daily report settings
    daily_report_hour: int = 16  # 4 PM
    daily_report_minute: int = 0

    # Market hours (for heartbeat scheduling)
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30
    mcx_close_hour: int = 23
    mcx_close_minute: int = 30

    @classmethod
    def from_file(cls, path: str = DEFAULT_CONFIG_PATH) -> "TelegramConfig":
        """
        Load configuration from JSON file.

        Args:
            path: Path to config file

        Returns:
            TelegramConfig instance
        """
        config_path = Path(path)

        if not config_path.exists():
            logger.warning(f"[TelegramConfig] Config file not found: {path}")
            return cls()

        try:
            with open(config_path) as f:
                data = json.load(f)

            return cls(**data)

        except json.JSONDecodeError as e:
            logger.error(f"[TelegramConfig] Invalid JSON in config file: {e}")
            return cls()
        except TypeError as e:
            logger.error(f"[TelegramConfig] Invalid config structure: {e}")
            return cls()

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        """
        Load configuration from environment variables.

        Environment variables:
        - TELEGRAM_BOT_TOKEN
        - TELEGRAM_CHAT_ID
        - TELEGRAM_ALLOWED_USERS (comma-separated user IDs)
        - TELEGRAM_ENABLED (true/false)
        - TELEGRAM_HEARTBEAT_INTERVAL (minutes)

        Returns:
            TelegramConfig instance
        """
        allowed_users = []
        allowed_users_str = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        if allowed_users_str:
            try:
                allowed_users = [int(uid.strip()) for uid in allowed_users_str.split(",")]
            except ValueError:
                logger.warning("[TelegramConfig] Invalid TELEGRAM_ALLOWED_USERS format")

        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            allowed_user_ids=allowed_users,
            enabled=os.getenv("TELEGRAM_ENABLED", "true").lower() == "true",
            heartbeat_interval_minutes=int(os.getenv("TELEGRAM_HEARTBEAT_INTERVAL", "60"))
        )

    def is_valid(self) -> bool:
        """Check if configuration is valid for bot operation."""
        if not self.bot_token:
            logger.warning("[TelegramConfig] Missing bot_token")
            return False
        if not self.chat_id:
            logger.warning("[TelegramConfig] Missing chat_id")
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "bot_token": self.bot_token[:10] + "..." if self.bot_token else "",
            "chat_id": self.chat_id,
            "allowed_user_ids": self.allowed_user_ids,
            "enabled": self.enabled,
            "alerts_enabled": self.alerts_enabled,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval_minutes": self.heartbeat_interval_minutes
        }


def create_config_template(path: str = DEFAULT_CONFIG_PATH):
    """
    Create a configuration template file.

    Args:
        path: Path to create template at
    """
    template = {
        "bot_token": "YOUR_BOT_TOKEN_FROM_BOTFATHER",
        "chat_id": "YOUR_CHAT_ID",
        "allowed_user_ids": [],
        "enabled": True,
        "alerts_enabled": True,
        "heartbeat_enabled": True,
        "daily_report_enabled": True,
        "rate_limit_per_minute": 20,
        "alert_queue_size": 100,
        "heartbeat_interval_minutes": 60,
        "daily_report_hour": 16,
        "daily_report_minute": 0,
        "market_open_hour": 9,
        "market_open_minute": 15,
        "market_close_hour": 15,
        "market_close_minute": 30,
        "mcx_close_hour": 23,
        "mcx_close_minute": 30
    }

    with open(path, 'w') as f:
        json.dump(template, f, indent=2)

    logger.info(f"[TelegramConfig] Created template at: {path}")


class TelegramBotFactory:
    """
    Factory for creating and initializing Telegram bot components.
    """

    def __init__(self, config: TelegramConfig, db_pool=None, portfolio_manager=None):
        """
        Initialize factory.

        Args:
            config: TelegramConfig instance
            db_pool: psycopg2 connection pool for audit service
            portfolio_manager: PortfolioStateManager for status queries
        """
        self.config = config
        self.db_pool = db_pool
        self.portfolio_manager = portfolio_manager

        self._bot = None
        self._alert_publisher = None
        self._heartbeat_scheduler = None
        self._daily_report_scheduler = None

    def create_audit_service(self):
        """Create SignalAuditService if db_pool available."""
        if not self.db_pool:
            return None

        from core.signal_audit_service import SignalAuditService
        return SignalAuditService(self.db_pool)

    def create_order_logger(self):
        """Create OrderExecutionLogger if db_pool available."""
        if not self.db_pool:
            return None

        from core.order_execution_logger import OrderExecutionLogger
        return OrderExecutionLogger(self.db_pool)

    def create_bot(self):
        """
        Create PortfolioManagerBot.

        Returns:
            PortfolioManagerBot instance or None
        """
        if not self.config.is_valid():
            logger.warning("[TelegramBotFactory] Invalid config, bot not created")
            return None

        if not self.config.enabled:
            logger.info("[TelegramBotFactory] Bot disabled in config")
            return None

        from telegram_bot.bot import PortfolioManagerBot

        audit_service = self.create_audit_service()
        order_logger = self.create_order_logger()

        self._bot = PortfolioManagerBot(
            token=self.config.bot_token,
            audit_service=audit_service,
            order_logger=order_logger,
            portfolio_manager=self.portfolio_manager,
            allowed_user_ids=self.config.allowed_user_ids or None
        )

        logger.info("[TelegramBotFactory] Bot created")
        return self._bot

    def create_alert_publisher(self):
        """
        Create TelegramAlertPublisher.

        Returns:
            TelegramAlertPublisher instance or None
        """
        if not self.config.is_valid():
            return None

        if not self.config.alerts_enabled:
            logger.info("[TelegramBotFactory] Alerts disabled in config")
            return None

        from telegram_bot.alerts import TelegramAlertPublisher

        self._alert_publisher = TelegramAlertPublisher(
            bot_token=self.config.bot_token,
            chat_id=self.config.chat_id,
            enabled=self.config.alerts_enabled,
            queue_size=self.config.alert_queue_size,
            rate_limit_per_minute=self.config.rate_limit_per_minute
        )

        logger.info("[TelegramBotFactory] Alert publisher created")
        return self._alert_publisher

    def create_heartbeat_scheduler(self, get_status_callback=None):
        """
        Create HeartbeatScheduler.

        Args:
            get_status_callback: Callback to get current status

        Returns:
            HeartbeatScheduler instance or None
        """
        if not self._alert_publisher:
            self.create_alert_publisher()

        if not self._alert_publisher:
            return None

        if not self.config.heartbeat_enabled:
            logger.info("[TelegramBotFactory] Heartbeat disabled in config")
            return None

        from telegram_bot.heartbeat import HeartbeatScheduler
        from datetime import time

        self._heartbeat_scheduler = HeartbeatScheduler(
            alert_publisher=self._alert_publisher,
            interval_minutes=self.config.heartbeat_interval_minutes,
            market_open=time(self.config.market_open_hour, self.config.market_open_minute),
            market_close=time(self.config.market_close_hour, self.config.market_close_minute),
            mcx_close=time(self.config.mcx_close_hour, self.config.mcx_close_minute),
            get_status_callback=get_status_callback
        )

        logger.info("[TelegramBotFactory] Heartbeat scheduler created")
        return self._heartbeat_scheduler

    def create_daily_report_scheduler(self, get_report_callback=None):
        """
        Create DailyReportScheduler.

        Args:
            get_report_callback: Callback to get daily report data

        Returns:
            DailyReportScheduler instance or None
        """
        if not self._alert_publisher:
            self.create_alert_publisher()

        if not self._alert_publisher:
            return None

        if not self.config.daily_report_enabled:
            logger.info("[TelegramBotFactory] Daily report disabled in config")
            return None

        from telegram_bot.heartbeat import DailyReportScheduler
        from datetime import time

        self._daily_report_scheduler = DailyReportScheduler(
            alert_publisher=self._alert_publisher,
            report_time=time(self.config.daily_report_hour, self.config.daily_report_minute),
            get_daily_report_callback=get_report_callback
        )

        logger.info("[TelegramBotFactory] Daily report scheduler created")
        return self._daily_report_scheduler

    def create_all(self, get_status_callback=None, get_report_callback=None):
        """
        Create all Telegram components.

        Args:
            get_status_callback: Callback for heartbeat status
            get_report_callback: Callback for daily report

        Returns:
            Dict with all components
        """
        return {
            "bot": self.create_bot(),
            "alert_publisher": self.create_alert_publisher(),
            "heartbeat_scheduler": self.create_heartbeat_scheduler(get_status_callback),
            "daily_report_scheduler": self.create_daily_report_scheduler(get_report_callback)
        }

    @property
    def bot(self):
        """Get bot instance."""
        return self._bot

    @property
    def alert_publisher(self):
        """Get alert publisher instance."""
        return self._alert_publisher

    @property
    def heartbeat_scheduler(self):
        """Get heartbeat scheduler instance."""
        return self._heartbeat_scheduler
