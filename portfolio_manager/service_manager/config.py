"""
Service Manager Configuration

Defines the services managed by this system and their properties.
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Base paths
REPO_ROOT = Path(__file__).parent.parent.parent.absolute()
PM_DIR = REPO_ROOT / "portfolio_manager"
FRONTEND_DIR = REPO_ROOT / "frontend"
MARGIN_MONITOR_DIR = REPO_ROOT / "margin-monitor"
OPENALGO_DIR = Path.home() / "openalgo"


@dataclass
class ServiceConfig:
    """Configuration for a managed service."""
    name: str                          # Display name
    key: str                           # Internal key (used in API)
    port: int                          # Port the service runs on
    health_url: Optional[str]          # Health check URL (None = port check only)
    pid_file: str                      # PID file name (relative to PM_DIR)
    start_cmd: str                     # Command to start the service
    working_dir: Path                  # Working directory for the command
    env_vars: Optional[dict] = None    # Additional environment variables
    description: str = ""              # Service description


# Service definitions
SERVICES = {
    "frontend": ServiceConfig(
        name="Frontend",
        key="frontend",
        port=8080,
        health_url=None,  # Just check if port is listening
        pid_file=".frontend.pid",
        start_cmd="bun run dev",
        working_dir=FRONTEND_DIR,
        description="React dashboard UI"
    ),
    "pm": ServiceConfig(
        name="Portfolio Manager",
        key="pm",
        port=5002,
        health_url="http://127.0.0.1:5002/health",
        pid_file=".pm.pid",
        start_cmd="python3 portfolio_manager.py live --broker zerodha --db-config db_config.json",
        working_dir=PM_DIR,
        env_vars={
            "OPENALGO_API_KEY": os.getenv("OPENALGO_API_KEY", ""),
        },
        description="Trading engine and webhook handler"
    ),
    "margin_monitor": ServiceConfig(
        name="Margin Monitor",
        key="margin_monitor",
        port=5010,
        health_url="http://localhost:5010/api/hedge/status",
        pid_file=".margin_monitor.pid",
        start_cmd="python3 run.py",
        working_dir=MARGIN_MONITOR_DIR,
        env_vars={
            "AUTO_HEDGE_ENABLED": "true",
            "AUTO_HEDGE_DRY_RUN": "true",
            "HEDGE_DEV_MODE": "true",
        },
        description="Auto-hedge system"
    ),
    "openalgo": ServiceConfig(
        name="OpenAlgo",
        key="openalgo",
        port=5000,
        health_url="http://127.0.0.1:5000/api/v1/ping",
        pid_file=".openalgo.pid",
        start_cmd="uv run app.py",
        working_dir=OPENALGO_DIR,
        env_vars={
            "FLASK_PORT": "5000",
            "HOST_SERVER": "http://127.0.0.1:5000",
        },
        description="Broker API bridge"
    ),
}


# API Configuration
SERVICE_MANAGER_PORT = 5003
SERVICE_MANAGER_HOST = "127.0.0.1"  # Localhost only for security

# Get API key from environment (required for restart/stop operations)
SERVICE_MANAGER_API_KEY = os.getenv("SERVICE_MANAGER_API_KEY", "dev-key-change-in-production")

# Timeouts
GRACEFUL_SHUTDOWN_TIMEOUT = 5  # Seconds to wait for graceful shutdown
HEALTH_CHECK_TIMEOUT = 30      # Seconds to wait for service to become healthy
HEALTH_CHECK_INTERVAL = 1      # Seconds between health checks

# Cooldown to prevent rapid restarts
RESTART_COOLDOWN = 10  # Seconds between restart attempts for same service
