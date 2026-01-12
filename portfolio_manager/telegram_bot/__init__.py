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
"""

from telegram_bot.bot import PortfolioManagerBot
from telegram_bot.alerts import TelegramAlertPublisher, SyncAlertPublisher, Alert, AlertType
from telegram_bot.heartbeat import HeartbeatScheduler, DailyReportScheduler
from telegram_bot.config import TelegramConfig, TelegramBotFactory, create_config_template

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
    'create_config_template'
]
