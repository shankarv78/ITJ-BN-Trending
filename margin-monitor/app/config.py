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

    # OpenAlgo
    openalgo_base_url: str = "http://127.0.0.1:5000"
    openalgo_api_key: str = ""

    # Trading Defaults
    default_budget_per_basket: float = 1000000.0  # ₹10L per basket
    lot_size_nifty: int = 75
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
