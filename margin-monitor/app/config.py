"""
Margin Monitor - Configuration Settings
"""

from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server
    mm_port: int = 5010
    mm_host: str = "0.0.0.0"

    # Database
    database_url: str = "postgresql://localhost:5432/portfolio_manager"
    mm_schema: str = "margin_monitor"
    hedge_schema: str = "auto_hedge"

    # OpenAlgo
    openalgo_base_url: str = "http://127.0.0.1:5000"
    openalgo_api_key: str = ""

    # Trading Defaults
    default_budget_per_basket: float = 1000000.0  # ₹10L per basket
    lot_size_nifty: int = 65
    lot_size_sensex: int = 10

    # Scheduler
    baseline_capture_time: str = "09:15:15"
    market_open: str = "09:15"
    market_close: str = "15:30"

    # Auto-shutdown after EOD (at 15:40 IST)
    auto_shutdown_after_eod: bool = False
    shutdown_time: str = "15:40"

    # Frontend CORS - Allow all localhost ports for development
    cors_origins: str = '["*"]'

    # ================================================================
    # AUTO-HEDGE CONFIGURATION
    # ================================================================

    # Telegram Bot (for hedge alerts)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Hedge Thresholds
    hedge_entry_trigger_pct: float = 95.0    # Buy hedge if projected > this
    hedge_entry_target_pct: float = 85.0     # Target utilization after hedge
    hedge_exit_trigger_pct: float = 70.0     # Consider exit if util < this

    # Hedge Timing
    hedge_lookahead_minutes: int = 5         # Check this many mins before entry
    hedge_exit_buffer_minutes: int = 15      # Don't exit if entry within this

    # Hedge Strike Selection
    hedge_min_premium: float = 2.0           # Min LTP for hedge strike
    hedge_max_premium: float = 6.0           # Max LTP for hedge strike

    # Hedge Safety
    hedge_max_cost_per_day: float = 50000.0  # ₹50K max daily spend
    hedge_cooldown_seconds: int = 120        # Min time between actions

    # Auto-hedge toggle (can be disabled globally)
    auto_hedge_enabled: bool = False  # Disabled by default, enable via AUTO_HEDGE_ENABLED=true
    auto_hedge_dry_run: bool = True   # Dry run mode (no real orders) by default

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        try:
            return json.loads(self.cors_origins)
        except (json.JSONDecodeError, TypeError):
            return ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
