"""
Telegram Bot Module for Portfolio Manager

Provides query interface and alerts via Telegram.

Components:
- PortfolioManagerBot: Query bot with command handlers
- TelegramAlertPublisher: Non-blocking alert publisher
- HeartbeatScheduler: Periodic status updates
- DailyReportScheduler: End-of-day reports
- TelegramConfig: Configuration management
- TelegramBotFactory: Component factory
- DualChannelConfirmationManager: Dual-channel confirmations (macOS + Telegram)
- SyncConfirmationBridge: Sync wrapper for confirmation manager
"""

from telegram_bot.bot import PortfolioManagerBot
from telegram_bot.alerts import TelegramAlertPublisher, SyncAlertPublisher, Alert, AlertType
from telegram_bot.heartbeat import HeartbeatScheduler, DailyReportScheduler
from telegram_bot.config import TelegramConfig, TelegramBotFactory, create_config_template
from telegram_bot.confirmations import (
    DualChannelConfirmationManager,
    ConfirmationType,
    ConfirmationAction,
    ConfirmationOption,
    ConfirmationResult
)
from telegram_bot.sync_bridge import (
    SyncConfirmationBridge,
    create_validation_options,
    create_order_failure_options,
    create_exit_failure_options,
    create_zero_lots_options
)

__all__ = [
    'PortfolioManagerBot',
    'TelegramAlertPublisher',
    'SyncAlertPublisher',
    'Alert',
    'AlertType',
    'HeartbeatScheduler',
    'DailyReportScheduler',
    'TelegramConfig',
    'TelegramBotFactory',
    'create_config_template',
    # Dual-channel confirmations
    'DualChannelConfirmationManager',
    'SyncConfirmationBridge',
    'ConfirmationType',
    'ConfirmationAction',
    'ConfirmationOption',
    'ConfirmationResult',
    'create_validation_options',
    'create_order_failure_options',
    'create_exit_failure_options',
    'create_zero_lots_options'
]
