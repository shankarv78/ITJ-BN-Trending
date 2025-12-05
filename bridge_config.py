"""
Configuration management for OpenAlgo Bridge
"""
import os
import json
from typing import Dict

CONFIG_FILE = "openalgo_config.json"

DEFAULT_CONFIG = {
    "openalgo_url": "http://localhost:5000",
    "openalgo_api_key": "",
    "broker": "zerodha",
    "risk_percent": 1.5,
    "margin_per_lot": 270000,
    "max_pyramids": 5,
    "bank_nifty_lot_size": 35,
    "strike_interval": 100,
    "execution_mode": "analyzer",
    "enable_telegram": False,
    "market_start_hour": 9,
    "market_start_minute": 15,
    "market_end_hour": 15,
    "market_end_minute": 25,
    "duplicate_window_seconds": 60,
    "order_timeout_seconds": 30,
    "enable_partial_fill_protection": True,
    "use_monthly_expiry": True
}

def load_config() -> Dict:
    """Load configuration from file or return defaults"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                custom_config = json.load(f)
                config = {**DEFAULT_CONFIG, **custom_config}
                return config
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return DEFAULT_CONFIG
    else:
        # Save default config
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG

def get_config() -> Dict:
    """Get current configuration"""
    return load_config()


