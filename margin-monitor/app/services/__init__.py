# Services

# Existing Margin Monitor Services
from app.services.openalgo_service import OpenAlgoService, openalgo_service
from app.services.margin_service import MarginService
from app.services.position_service import PositionService
from app.services.analytics_service import AnalyticsService
from app.services.scheduler_service import scheduler_service

# Auto-Hedge Services
from app.services.strategy_scheduler import StrategySchedulerService
from app.services.margin_calculator import MarginCalculatorService
from app.services.hedge_selector import HedgeStrikeSelectorService
from app.services.hedge_executor import HedgeExecutorService
from app.services.telegram_service import TelegramService, telegram_service
from app.services.hedge_orchestrator import AutoHedgeOrchestrator

__all__ = [
    # Margin Monitor
    'OpenAlgoService',
    'openalgo_service',
    'MarginService',
    'PositionService',
    'AnalyticsService',
    'scheduler_service',
    # Auto-Hedge
    'StrategySchedulerService',
    'MarginCalculatorService',
    'HedgeStrikeSelectorService',
    'HedgeExecutorService',
    'TelegramService',
    'telegram_service',
    'AutoHedgeOrchestrator',
]
