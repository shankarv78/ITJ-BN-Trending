#!/usr/bin/env python3
"""
Tom Basso Portfolio Manager - Main Entry Point

Unified system for backtesting and live trading

Usage:
    # Backtest mode
    python portfolio_manager.py backtest --gold signals/gold.csv --bn signals/bn.csv

    # Live trading mode (loads capital from database)
    python portfolio_manager.py live --api-key YOUR_KEY --db-config db_config.json

    # Live trading with manual capital (overrides database)
    python portfolio_manager.py live --api-key YOUR_KEY --capital 5000000
"""
import sys
import os
import argparse
import logging
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from collections import defaultdict
from functools import wraps
from typing import Tuple
from flask_cors import CORS

# Setup logging with rotation (10MB per file, 5 backups)
error_handler = RotatingFileHandler('webhook_errors.log', maxBytes=10*1024*1024, backupCount=5)
error_handler.setLevel(logging.ERROR)  # Set level after creation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('portfolio_manager.log', maxBytes=10*1024*1024, backupCount=5),
        error_handler,  # Use handler with level set separately
        logging.StreamHandler()
    ]
)

# Separate logger for webhook validation
webhook_logger = logging.getLogger('webhook_validation')
webhook_handler = RotatingFileHandler('webhook_validation.log', maxBytes=10*1024*1024, backupCount=5)
webhook_handler.setLevel(logging.WARNING)
webhook_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
webhook_logger.addHandler(webhook_handler)

logger = logging.getLogger(__name__)


# =============================================================================
# Response Cache - Prevents frontend polling from blocking webhook processing
# =============================================================================
class ResponseCache:
    """Simple time-based cache for frequently polled endpoints"""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key: str, max_age_seconds: float = 2.0):
        """Get cached response if not expired"""
        with self._lock:
            if key in self._cache:
                cached_time, data = self._cache[key]
                if time.time() - cached_time < max_age_seconds:
                    return data
        return None

    def set(self, key: str, data):
        """Cache a response"""
        with self._lock:
            self._cache[key] = (time.time(), data)

    def invalidate(self, key: str = None):
        """Invalidate cache entry or all entries"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

# Global response cache instance
response_cache = ResponseCache()


class RolloverScheduler:
    """Background scheduler for daily rollover checks"""

    def __init__(self, engine, check_interval_hours: float = 1.0):
        """
        Initialize scheduler

        Args:
            engine: LiveTradingEngine instance
            check_interval_hours: How often to check for rollovers (default: 1 hour)
        """
        self.engine = engine
        self.check_interval = check_interval_hours * 3600  # Convert to seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread = None
        self._last_check: datetime = None

    def start(self):
        """Start the background scheduler"""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Rollover scheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Rollover scheduler started (check every {self.check_interval/3600:.1f} hours)")

    def stop(self):
        """Stop the background scheduler"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("Rollover scheduler stopped")

    def _run(self):
        """Background thread main loop"""
        while not self._stop_event.is_set():
            try:
                # Check if it's time to run rollover check
                now = datetime.now()

                # Only check during market hours (roughly 9 AM - 11:30 PM for MCX coverage)
                hour = now.hour
                is_weekday = now.weekday() < 5

                if is_weekday and 9 <= hour <= 23:
                    # Check if enough time has passed since last check
                    if (self._last_check is None or
                        (now - self._last_check).total_seconds() >= self.check_interval):

                        logger.info("Running scheduled rollover check...")
                        try:
                            result = self.engine.check_and_rollover_positions(dry_run=False)
                            self._last_check = now

                            if result.total_positions > 0:
                                logger.info(
                                    f"Scheduled rollover: {result.successful}/{result.total_positions} "
                                    f"positions rolled"
                                )
                        except Exception as e:
                            logger.error(f"Rollover check failed: {e}")

                # Sleep for a bit before next iteration
                # Use shorter sleep to be responsive to stop requests
                for _ in range(60):  # Check stop every second for 60 seconds
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Rollover scheduler error: {e}")
                time.sleep(60)  # Wait a minute on error

    def force_check(self) -> dict:
        """Force an immediate rollover check (for manual trigger)"""
        logger.info("Forcing immediate rollover check...")
        result = self.engine.check_and_rollover_positions(dry_run=False)
        self._last_check = datetime.now()
        return {
            'timestamp': self._last_check.isoformat(),
            'total_positions': result.total_positions,
            'successful': result.successful,
            'failed': result.failed,
            'cost': result.total_rollover_cost
        }

    def dry_run_check(self) -> dict:
        """Run rollover check in dry-run mode (no actual orders)"""
        logger.info("Running dry-run rollover check...")
        result = self.engine.check_and_rollover_positions(dry_run=True)
        return {
            'timestamp': datetime.now().isoformat(),
            'dry_run': True,
            'positions_would_roll': result.total_positions,
            'candidates': [r.position_id for r in result.results]
        }

def run_backtest(args):
    """Run portfolio backtest"""
    from backtest.engine import PortfolioBacktestEngine
    from backtest.signal_loader import SignalLoader

    logger.info("=" * 60)
    logger.info("TOM BASSO PORTFOLIO BACKTEST")
    logger.info("=" * 60)

    # Load signals
    loader = SignalLoader()

    gold_signals = []
    if args.gold:
        gold_signals = loader.load_signals_from_csv(args.gold, "GOLD_MINI")
        logger.info(f"Loaded {len(gold_signals)} Gold signals")

    bn_signals = []
    if args.bn:
        bn_signals = loader.load_signals_from_csv(args.bn, "BANK_NIFTY")
        logger.info(f"Loaded {len(bn_signals)} Bank Nifty signals")

    # Merge chronologically
    all_signals = loader.merge_signals_chronologically(gold_signals, bn_signals)

    if not all_signals:
        logger.error("No signals loaded!")
        return 1

    # Run backtest
    engine = PortfolioBacktestEngine(initial_capital=args.capital)
    results = engine.run_backtest(all_signals)

    # Display results
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Initial Capital: ₹{results['initial_capital']:,.0f}")
    logger.info(f"Final Equity: ₹{results['final_equity']:,.0f}")
    logger.info(f"Total P&L: ₹{results['total_pnl']:,.0f}")
    logger.info(f"Return: {(results['total_pnl']/results['initial_capital']*100):.2f}%")
    logger.info("")
    logger.info("Statistics:")
    for key, value in results['stats'].items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 60)

    return 0

def run_live(args):
    """Run live trading"""
    from live.engine import LiveTradingEngine
    from flask import Flask, request, jsonify
    from psycopg2.extras import RealDictCursor
    from core.webhook_parser import (
        DuplicateDetector, validate_json_structure, parse_webhook_signal,
        is_eod_monitor_signal, parse_eod_monitor_signal, parse_any_signal
    )
    from core.models import Signal, EODMonitorSignal
    from core.eod_scheduler import EODScheduler
    import json

    logger.info("=" * 60)
    logger.info("TOM BASSO PORTFOLIO - LIVE TRADING")
    logger.info("=" * 60)
    logger.info(f"Broker: {args.broker}")
    logger.info(f"Mode: {'🧪 TEST MODE (1 lot only)' if args.test_mode else 'LIVE'}")
    logger.info(f"Auto Rollover: {'Enabled' if not args.disable_rollover else 'Disabled'}")
    logger.info(f"Voice: {'🔇 SILENT MODE (visual alerts only)' if args.silent else 'Enabled'}")
    if args.test_mode:
        logger.warning("🧪 TEST MODE ACTIVE: All entries will place 1 lot only")
        logger.warning("🧪 TEST MODE ACTIVE: Actual calculated lots will be logged")
        logger.warning("🧪 TEST MODE ACTIVE: Use /test/clear to erase test positions")
    if args.silent:
        logger.info("🔇 SILENT MODE: Voice disabled, using macOS visual alerts")
        logger.info("🔇 Critical errors → Modal dialog with OK button")
        logger.info("🔇 Non-critical alerts → Auto-dismiss notification (15s)")
    logger.info("=" * 60)

    # Initialize database manager if config provided
    db_manager = None
    if args.db_config:
        try:
            from core.db_state_manager import DatabaseStateManager

            with open(args.db_config, 'r') as f:
                db_config = json.load(f)

            # Use 'local' or 'production' environment
            env = getattr(args, 'db_env', 'local')
            connection_config = db_config.get(env, db_config.get('local', {}))

            if connection_config:
                db_manager = DatabaseStateManager(connection_config)
                logger.info(f"Database persistence enabled ({env} environment)")
            else:
                logger.warning(f"Database config not found for environment '{env}', continuing without persistence")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.warning("Continuing without database persistence")
            db_manager = None
    else:
        logger.info("Database persistence disabled (no --db-config provided)")

    # Initialize Strategy Manager for multi-strategy P&L tracking
    strategy_manager = None
    if db_manager:
        try:
            from core.strategy_manager import StrategyManager
            strategy_manager = StrategyManager(db_manager)
            logger.info("Strategy manager initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize strategy manager: {e}")

    # Determine initial capital: from args, database, or default
    initial_capital = args.capital
    if initial_capital is None:
        if db_manager:
            # Try to load from database
            db_state = db_manager.get_portfolio_state()
            if db_state and db_state.get('initial_capital'):
                initial_capital = float(db_state['initial_capital'])
                logger.info(f"Loaded initial_capital from database: ₹{initial_capital:,.0f}")
            else:
                initial_capital = 5000000.0  # Default fallback
                logger.warning(f"No capital in database, using default: ₹{initial_capital:,.0f}")
        else:
            initial_capital = 5000000.0  # Default fallback
            logger.warning(f"No --capital specified and no database, using default: ₹{initial_capital:,.0f}")

    # Initialize broker client using factory
    try:
        from brokers.factory import create_broker_client

        # Load OpenAlgo config if available
        openalgo_config_path = Path(__file__).parent / 'openalgo_config.json'
        broker_config = {}

        if openalgo_config_path.exists():
            logger.info(f"Loading OpenAlgo config from {openalgo_config_path}")
            with open(openalgo_config_path, 'r') as f:
                broker_config = json.load(f)
        else:
            logger.warning(f"OpenAlgo config not found at {openalgo_config_path}")
            logger.warning("Using command-line arguments for broker configuration")
            # Fallback to command-line args
            broker_config = {
                'openalgo_url': 'http://127.0.0.1:5000',
                'openalgo_api_key': args.api_key,
                'broker': args.broker,
                'execution_mode': 'analyzer'  # Default to analyzer for safety
            }

        # Determine broker type: use 'openalgo' for real broker, 'mock' for testing
        broker_type = 'openalgo' if args.broker in ['zerodha', 'dhan'] else 'mock'

        # Override API key from command line if provided
        if args.api_key:
            broker_config['openalgo_api_key'] = args.api_key

        execution_mode = broker_config.get('execution_mode', 'live')
        logger.info(f"Creating broker client: type={broker_type}, broker={args.broker}, execution_mode={execution_mode}")
        openalgo = create_broker_client(broker_type, broker_config)
        logger.info("✓ Broker client initialized successfully")

        # Prominent warning for analyzer mode
        if execution_mode == 'analyzer':
            logger.warning("=" * 70)
            logger.warning("⚠️  ANALYZER MODE: Orders will be SIMULATED, not executed!")
            logger.warning("⚠️  Change execution_mode to 'live' in openalgo_config.json for real trading")
            logger.warning("=" * 70)

    except Exception as e:
        logger.error(f"Failed to initialize broker client: {e}", exc_info=True)
        logger.error("Falling back to mock client for testing")
        # Fallback to mock client
        class MockOpenAlgoClient:
            def get_funds(self):
                return {'availablecash': initial_capital}

            def get_quote(self, symbol):
                return {'ltp': 52000, 'bid': 51990, 'ask': 52010}

            def place_order(self, symbol, action, quantity, order_type="MARKET", price=0.0):
                return {'status': 'success', 'orderid': f'MOCK_{symbol}_{action}'}

            def get_order_status(self, order_id):
                return {'status': 'COMPLETE', 'price': 52000}

            def modify_order(self, order_id, new_price):
                return {'status': 'success'}

            def cancel_order(self, order_id):
                return {'status': 'success'}

        openalgo = MockOpenAlgoClient()

    # Initialize Holiday Calendar (needed by expiry calendar and symbol mapper)
    holiday_calendar = None
    try:
        from core.holiday_calendar import init_holiday_calendar
        holiday_calendar = init_holiday_calendar(data_dir='.taskmaster/data')

        # Add known 2025 holidays
        from datetime import date as dt_date
        holiday_calendar.add_holiday(dt_date(2025, 12, 25), "NSE", "Christmas")
        holiday_calendar.add_holiday(dt_date(2025, 12, 25), "MCX", "Christmas")

        # Check if today is a holiday
        today = dt_date.today()
        nse_holiday, nse_reason = holiday_calendar.is_holiday(today, "NSE")
        mcx_holiday, mcx_reason = holiday_calendar.is_holiday(today, "MCX")

        if nse_holiday or mcx_holiday:
            logger.warning(f"[PM] TODAY IS HOLIDAY - NSE: {nse_reason}, MCX: {mcx_reason}")

        logger.info(f"Holiday calendar initialized ({holiday_calendar.get_status()['total_holidays']} holidays loaded)")
    except Exception as e:
        logger.warning(f"Failed to initialize holiday calendar: {e}")

    # Initialize Expiry Calendar with Holiday Calendar (needed by symbol mapper)
    expiry_calendar = None
    try:
        from core.expiry_calendar import init_expiry_calendar
        expiry_calendar = init_expiry_calendar(holiday_calendar=holiday_calendar)
        logger.info("Expiry calendar initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize expiry calendar: {e}")

    # Initialize Symbol Mapper (MUST be before LiveTradingEngine for SyntheticFuturesExecutor)
    symbol_mapper = None
    try:
        from core.symbol_mapper import init_symbol_mapper
        symbol_mapper = init_symbol_mapper(
            expiry_calendar=expiry_calendar,
            holiday_calendar=holiday_calendar,
            price_provider=lambda sym: openalgo.get_quote(sym).get('ltp', 0) if openalgo else 0
        )
        logger.info("Symbol mapper initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize symbol mapper: {e}")

    # Initialize live engine with database manager
    # NOTE: Must be after symbol mapper init for SyntheticFuturesExecutor to work
    engine = LiveTradingEngine(
        initial_capital=initial_capital,
        openalgo_client=openalgo,
        db_manager=db_manager,
        test_mode=args.test_mode,
        strategy_manager=strategy_manager
    )

    # Initialize voice announcer for trade notifications
    voice_announcer = None
    try:
        from core.voice_announcer import init_announcer
        voice_announcer = init_announcer(
            enabled=True,
            rate=180,  # Words per minute (slightly faster for clarity)
            volume=1.0,  # Maximum volume
            error_repeat_interval=15.0,  # Repeat unacknowledged errors every 15 seconds
            silent_mode=args.silent  # Silent mode: visual alerts only
        )
        if args.silent:
            logger.info("Voice announcer initialized in SILENT MODE (visual alerts only)")
            logger.info("Critical errors → macOS dialog, Non-critical → auto-dismiss notification")
        else:
            logger.info("Voice announcer initialized (rate: 180 wpm, error repeat: 15s)")
            logger.info("Errors will show macOS popup dialog for acknowledgment")
    except ImportError:
        logger.info("Voice announcer not available")
    except Exception as e:
        logger.warning(f"Failed to initialize voice announcer: {e}")

    # Initialize Telegram notifier for mobile alerts
    telegram_notifier = None
    telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if telegram_bot_token and telegram_chat_id:
        try:
            from core.telegram_notifier import init_telegram_notifier
            telegram_notifier = init_telegram_notifier(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id,
                enabled=True,
                engine=engine
            )
            logger.info(f"Telegram notifier initialized (chat_id: {telegram_chat_id})")
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram notifier: {e}")
    else:
        logger.info("Telegram notifier disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable)")

    # Initialize Safety Manager
    safety_manager = None
    try:
        from core.safety_manager import init_safety_manager
        safety_manager = init_safety_manager(
            portfolio_state_manager=engine.portfolio,
            voice_announcer=voice_announcer,
            telegram_notifier=telegram_notifier,
            holiday_calendar=holiday_calendar
        )
        logger.info("Safety manager initialized (margin warning: 50%, critical: 80%, holidays: enabled)")
    except Exception as e:
        logger.warning(f"Failed to initialize safety manager: {e}")

    # Initialize Broker Sync Manager
    broker_sync = None
    try:
        from core.broker_sync import init_broker_sync
        broker_sync = init_broker_sync(
            portfolio_state_manager=engine.portfolio,
            openalgo_client=openalgo,
            telegram_notifier=telegram_notifier,
            voice_announcer=voice_announcer,
            sync_interval_seconds=300  # 5 minutes
        )
        # Perform startup reconciliation
        logger.info("Performing startup reconciliation with broker...")
        sync_result = broker_sync.startup_reconciliation()
        if sync_result.discrepancies:
            logger.warning(f"Startup reconciliation found {len(sync_result.discrepancies)} discrepancies!")
        # Start background sync
        broker_sync.start_background_sync()
        logger.info("Broker sync started (interval: 5 minutes)")
    except Exception as e:
        logger.warning(f"Failed to initialize broker sync: {e}")

    # Initialize duplicate detector for webhook signals
    duplicate_detector = DuplicateDetector(window_seconds=60)
    logger.info("Duplicate detector initialized (60s window)")

    # Initialize Redis coordinator for leader election (if Redis config available)
    coordinator = None
    if hasattr(args, 'redis_config') and args.redis_config:
        try:
            from core.redis_coordinator import RedisCoordinator
            import json

            with open(args.redis_config, 'r') as f:
                redis_config = json.load(f)

            coordinator = RedisCoordinator(redis_config, db_manager=db_manager)
            coordinator.start_heartbeat()
            logger.info("Redis coordinator initialized - leader election enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis coordinator: {e}")
            logger.warning("Continuing without leader election (single instance mode)")
            coordinator = None
    else:
        logger.info("Redis coordinator disabled (no --redis-config provided)")

    # Crash Recovery: Load state from database if available
    if db_manager:
        try:
            from live.recovery import CrashRecoveryManager

            recovery_manager = CrashRecoveryManager(db_manager)
            success, error_code = recovery_manager.load_state(
                portfolio_manager=engine.portfolio,
                trading_engine=engine,
                coordinator=coordinator
            )

            if not success:
                if error_code == CrashRecoveryManager.VALIDATION_FAILED:
                    logger.critical(
                        "🚨 CRITICAL: State corruption detected during recovery - "
                        "HALTING STARTUP to prevent financial loss"
                    )
                    logger.critical(
                        "Action required: Review database state manually before restarting"
                    )
                    return 1  # Exit with error code
                elif error_code == CrashRecoveryManager.DB_UNAVAILABLE:
                    logger.error(
                        "Database unavailable during recovery - "
                        "Application will start with empty state"
                    )
                    logger.warning(
                        "⚠️  WARNING: If positions exist in database, they will not be tracked. "
                        "This may lead to duplicate positions or missed exits."
                    )
                    # Continue startup but log warning - allows manual intervention
                elif error_code == CrashRecoveryManager.DATA_CORRUPT:
                    logger.critical(
                        "🚨 CRITICAL: Data corruption detected during recovery - "
                        "HALTING STARTUP to prevent financial loss"
                    )
                    logger.critical(
                        "Action required: Review database state manually before restarting"
                    )
                    return 1  # Exit with error code
                else:
                    logger.error(f"Recovery failed with unknown error code: {error_code}")
                    logger.warning("Continuing startup with empty state")
            else:
                logger.info("✅ Crash recovery completed successfully - state restored")
        except Exception as e:
            logger.exception(f"Unexpected error during crash recovery: {e}")
            logger.critical(
                "🚨 CRITICAL: Crash recovery failed with unexpected error - "
                "HALTING STARTUP to prevent financial loss"
            )
            return 1  # Exit with error code
    else:
        logger.info("Crash recovery skipped (database persistence disabled)")

    # Initialize rollover scheduler
    rollover_scheduler = None
    if not args.disable_rollover:
        rollover_scheduler = RolloverScheduler(
            engine=engine,
            check_interval_hours=1.0  # Check every hour
        )
        rollover_scheduler.start()

    # Initialize EOD (End-of-Day) pre-close scheduler
    eod_scheduler = None
    if engine.config.eod_enabled and not getattr(args, 'disable_eod', False):
        try:
            eod_scheduler = EODScheduler(engine.config)
            eod_scheduler.set_callbacks(
                condition_check=engine.eod_condition_check,
                execution=engine.eod_execute,
                tracking=engine.eod_track
            )
            eod_scheduler.start()
            logger.info("EOD pre-close scheduler started")
        except ImportError as e:
            logger.warning(f"EOD scheduler not available (APScheduler not installed): {e}")
        except Exception as e:
            logger.error(f"Failed to start EOD scheduler: {e}")

    # Setup Flask webhook receiver
    app = Flask(__name__)

    # Disable werkzeug request logging (too noisy from frontend polling)
    import logging as std_logging
    std_logging.getLogger('werkzeug').setLevel(std_logging.WARNING)

    # CORS: Allow Lovable frontend (both production and preview domains) and localhost
    CORS(app, origins=[
        "https://67e5f3ed-4aa2-4971-859d-cdf8c8cacc46.lovableproject.com",  # Lovable production
        "https://*.lovableproject.com",  # Any Lovable production subdomain
        "https://id-preview--67e5f3ed-4aa2-4971-859d-cdf8c8cacc46.lovable.app",  # Lovable preview
        "https://*.lovable.app",  # Any Lovable preview subdomain
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://localhost:8080",  # Vite dev server (alternative port)
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080"
    ])
    logger.info("CORS enabled for Lovable frontend (lovableproject.com + lovable.app)")

    # Rate limiting: Track requests per IP (simple in-memory implementation)
    # For production, consider using Flask-Limiter or Redis-based solution
    rate_limit_store = defaultdict(list)  # IP -> list of timestamps
    RATE_LIMIT_REQUESTS = 100  # Max requests per window
    RATE_LIMIT_WINDOW_SECONDS = 60  # 1 minute window
    MAX_PAYLOAD_SIZE = 10 * 1024  # 10KB max payload size

    def check_rate_limit(ip_address: str) -> Tuple[bool, str]:
        """Check if IP has exceeded rate limit"""
        now = time.time()
        # Clean old entries
        rate_limit_store[ip_address] = [
            ts for ts in rate_limit_store[ip_address]
            if now - ts < RATE_LIMIT_WINDOW_SECONDS
        ]

        if len(rate_limit_store[ip_address]) >= RATE_LIMIT_REQUESTS:
            return False, f"Rate limit exceeded: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds"

        rate_limit_store[ip_address].append(now)
        return True, ""

    def generate_request_id() -> str:
        """Generate unique request ID for correlation"""
        return str(uuid.uuid4())[:8]  # Short ID for readability

    @app.route('/webhook', methods=['POST'])
    def webhook():
        """
        Receive TradingView webhooks

        6-Step Processing Pipeline:
        1. Receive JSON - Get request.json, validate not None
        2. Validate structure - Call validate_json_structure()
        3. Parse to Signal - Call parse_webhook_signal() → Signal.from_dict()
        4. Check duplicates - Call duplicate_detector.is_duplicate()
        5. Process signal - Call engine.process_signal(signal)
        6. Return response - Appropriate HTTP status and JSON
        """
        # Generate request ID for correlation
        request_id = generate_request_id()
        client_ip = request.remote_addr or 'unknown'

        # Rate limiting check
        rate_ok, rate_error = check_rate_limit(client_ip)
        if not rate_ok:
            webhook_logger.warning(f"[{request_id}] Rate limit exceeded from {client_ip}")
            return jsonify({
                'status': 'error',
                'error_type': 'rate_limit_error',
                'message': rate_error,
                'request_id': request_id
            }), 429  # Too Many Requests

        # Payload size check
        if request.content_length and request.content_length > MAX_PAYLOAD_SIZE:
            webhook_logger.warning(f"[{request_id}] Payload too large: {request.content_length} bytes")
            return jsonify({
                'status': 'error',
                'error_type': 'validation_error',
                'message': f'Payload size exceeds maximum: {MAX_PAYLOAD_SIZE} bytes',
                'request_id': request_id
            }), 413  # Payload Too Large

        # Step 1: Receive JSON
        # Handle case where Flask couldn't parse JSON (returns None)
        # Use force=True because TradingView webhooks may not set Content-Type header
        try:
            data = request.get_json(force=True)
            if data is None:
                # Check if request has data but couldn't be parsed
                if request.data:
                    webhook_logger.error(f"[{request_id}] Webhook received with invalid JSON format")
                    return jsonify({
                        'status': 'error',
                        'error_type': 'validation_error',
                        'message': 'Invalid JSON format',
                        'request_id': request_id
                    }), 400
                else:
                    webhook_logger.error(f"[{request_id}] Webhook received with no JSON data")
                    return jsonify({
                        'status': 'error',
                        'error_type': 'validation_error',
                        'message': 'No JSON data received',
                        'request_id': request_id
                    }), 400
        except Exception as e:
            # Flask couldn't parse JSON at all
            webhook_logger.error(f"[{request_id}] Webhook JSON parsing error: {e}")
            return jsonify({
                'status': 'error',
                'error_type': 'validation_error',
                'message': 'Invalid JSON format',
                'request_id': request_id
            }), 400

        logger.info(f"[{request_id}] Webhook received: {data.get('type')} {data.get('position')} @ {data.get('price')}")

        try:
            # Check if this is an EOD_MONITOR signal (different processing path)
            if is_eod_monitor_signal(data):
                logger.info(f"[{request_id}] EOD_MONITOR signal detected")

                # Parse EOD signal
                eod_signal, eod_error = parse_eod_monitor_signal(data)
                if eod_signal is None:
                    webhook_logger.warning(f"[{request_id}] EOD signal parsing failed: {eod_error}")
                    return jsonify({
                        'status': 'error',
                        'error_type': 'validation_error',
                        'message': eod_error,
                        'request_id': request_id
                    }), 400

                # Leadership check for EOD signals
                if coordinator and not coordinator.is_leader:
                    webhook_logger.warning(
                        f"[{request_id}] Rejecting EOD signal - not leader"
                    )
                    return jsonify({
                        'status': 'rejected',
                        'reason': 'not_leader',
                        'request_id': request_id
                    }), 200

                # Process EOD signal through engine
                result = engine.process_eod_monitor_signal(eod_signal)

                return jsonify({
                    'status': 'processed',
                    'signal_type': 'eod_monitor',
                    'request_id': request_id,
                    'result': result
                }), 200

            # Regular signal processing continues below
            # Step 2: Validate structure
            is_valid, structure_error = validate_json_structure(data)
            if not is_valid:
                webhook_logger.warning(f"[{request_id}] Invalid JSON structure: {structure_error}")
                return jsonify({
                    'status': 'error',
                    'error_type': 'validation_error',
                    'message': structure_error,
                    'request_id': request_id
                }), 400

            # Step 3: Parse to Signal
            signal, parse_error = parse_webhook_signal(data)
            if signal is None:
                webhook_logger.warning(f"[{request_id}] Signal parsing failed: {parse_error}")
                return jsonify({
                    'status': 'error',
                    'error_type': 'validation_error',
                    'message': parse_error,
                    'request_id': request_id
                }), 400

            logger.info(f"[{request_id}] Signal parsed: {signal.signal_type.value} {signal.position} @ ₹{signal.price}")

            # Step 3.5: Initial leadership check (CRITICAL for trading - prevents duplicate execution)
            if coordinator and not coordinator.is_leader:
                webhook_logger.warning(
                    f"[{request_id}] Rejecting signal - not leader (instance: {coordinator.instance_id})"
                )
                return jsonify({
                    'status': 'rejected',
                    'reason': 'not_leader',
                    'message': f'Signal rejected: instance {coordinator.instance_id} is not the leader',
                    'request_id': request_id
                }), 200

            # Step 4: Check duplicates
            if duplicate_detector.is_duplicate(signal):
                webhook_logger.warning(
                    f"[{request_id}] Duplicate signal ignored: {signal.signal_type.value} {signal.position} "
                    f"@ {signal.timestamp.isoformat()}"
                )
                return jsonify({
                    'status': 'ignored',
                    'error_type': 'duplicate',
                    'message': 'Signal already processed within last 60 seconds',
                    'request_id': request_id,
                    'details': {
                        'instrument': signal.instrument,
                        'position': signal.position,
                        'timestamp': signal.timestamp.isoformat()
                    }
                }), 200

            # Step 4.5: RE-CHECK leadership (race condition protection)
            # Critical: Leadership might have been lost during duplicate check
            if coordinator and not coordinator.is_leader:
                webhook_logger.warning(
                    f"[{request_id}] Lost leadership during signal processing - aborting"
                )
                return jsonify({
                    'status': 'rejected',
                    'reason': 'lost_leadership',
                    'message': 'Signal processing aborted: leadership lost during processing',
                    'request_id': request_id
                }), 200

            # Step 4.6: SAFETY CHECK - Trading pause, market hours, price sanity
            if safety_manager:
                # Check if trading is paused (kill switch)
                paused, pause_reason = safety_manager.is_trading_paused()
                if paused:
                    webhook_logger.warning(
                        f"[{request_id}] Signal rejected - trading paused: {pause_reason}"
                    )
                    return jsonify({
                        'status': 'rejected',
                        'reason': 'trading_paused',
                        'message': f'Trading is paused: {pause_reason}',
                        'request_id': request_id
                    }), 503  # Service Unavailable

                # Pre-order safety check (market hours, price sanity)
                # Note: Margin check happens in engine during position sizing
                safe, safety_msg = safety_manager.pre_order_safety_check(
                    instrument=signal.instrument,
                    signal_price=signal.price,
                    estimated_margin=0,  # Will be calculated by sizer
                    override=False
                )
                if not safe:
                    webhook_logger.warning(
                        f"[{request_id}] Signal rejected by safety check: {safety_msg}"
                    )
                    return jsonify({
                        'status': 'rejected',
                        'reason': 'safety_check_failed',
                        'message': safety_msg,
                        'request_id': request_id
                    }), 200

            # Step 5: Process signal (pass coordinator for additional verification)
            result = engine.process_signal(signal, coordinator=coordinator)

            # Step 5.5: Log signal to database (audit trail)
            if db_manager:
                import hashlib
                # Create fingerprint for deduplication
                fingerprint = hashlib.sha256(
                    f"{signal.instrument}:{signal.signal_type.value}:{signal.position}:{signal.timestamp.isoformat()}".encode()
                ).hexdigest()

                signal_data = {
                    'instrument': signal.instrument,
                    'type': signal.signal_type.value,
                    'position': signal.position,
                    'timestamp': signal.timestamp.isoformat(),
                    'price': signal.price,
                    'stop': signal.stop,
                    'atr': signal.atr,
                    'suggested_lots': signal.suggested_lots
                }

                instance_id = coordinator.instance_id if coordinator else 'standalone'
                db_manager.log_signal(signal_data, fingerprint, instance_id, result.get('status', 'unknown'))

            # Step 6: Return response
            if result.get('status') == 'executed':
                logger.info(f"[{request_id}] Signal executed: {signal.signal_type.value} {signal.position}")
                return jsonify({
                    'status': 'processed',
                    'request_id': request_id,
                    'result': result
                }), 200
            elif result.get('status') == 'blocked':
                logger.info(f"[{request_id}] Signal blocked: {result.get('reason')}")
                return jsonify({
                    'status': 'processed',
                    'request_id': request_id,
                    'result': result
                }), 200
            else:
                # Error in processing - remove from duplicate history so signal can be retried
                # This is critical for EXIT signals that fail due to "no positions" but
                # should succeed later when positions exist
                duplicate_detector.remove_failed_signal(signal)

                logger.error(f"[{request_id}] Signal processing error: {result.get('reason', 'Unknown error')}")
                return jsonify({
                    'status': 'error',
                    'error_type': 'processing_error',
                    'message': result.get('reason', 'Unknown processing error'),
                    'request_id': request_id,
                    'details': result
                }), 500

        except Exception as e:
            # Remove from duplicate history on exception too
            if 'signal' in locals():
                duplicate_detector.remove_failed_signal(signal)

            logger.exception(f"[{request_id}] Unexpected error processing webhook: {e}")
            webhook_logger.error(f"[{request_id}] Webhook processing exception: {e}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error_type': 'processing_error',
                'message': 'Internal server error',
                'request_id': request_id,
                'details': {'exception': str(e)} if logger.level <= logging.DEBUG else {}
            }), 500

    @app.route('/webhook/stats', methods=['GET'])
    def webhook_stats():
        """
        Get webhook processing statistics

        Returns separate metrics for:
        - Webhook-level stats (parsing, validation, duplicates)
        - Engine-level stats (execution, gates, orders)
        """
        # Track webhook-level stats (we'll track these in the endpoint)
        webhook_stats_data = {
            'duplicate_detector': duplicate_detector.get_stats(),
            'total_received': engine.stats.get('signals_received', 0),
            'validation_errors': 0,  # Could track this if needed
            'duplicates_ignored': duplicate_detector.get_stats()['duplicates_found']
        }

        return jsonify({
            'webhook': webhook_stats_data,
            'execution': {
                'entries_executed': engine.stats.get('entries_executed', 0),
                'pyramids_executed': engine.stats.get('pyramids_executed', 0),
                'exits_executed': engine.stats.get('exits_executed', 0),
                'entries_blocked': engine.stats.get('entries_blocked', 0),
                'pyramids_blocked': engine.stats.get('pyramids_blocked', 0)
            }
        }), 200

    @app.route('/db/status', methods=['GET'])
    def db_status():
        """Get database connection status"""
        if not db_manager:
            return jsonify({
                'status': 'disabled',
                'message': 'Database persistence not configured'
            }), 200

        try:
            # Test connection
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()

            # Get basic stats
            portfolio_state = db_manager.get_portfolio_state()
            open_positions = db_manager.get_all_open_positions()

            return jsonify({
                'status': 'connected',
                'connection': 'healthy',
                'open_positions': len(open_positions),
                'closed_equity': portfolio_state.get('closed_equity') if portfolio_state else None
            }), 200
        except Exception as e:
            logger.error(f"Database status check failed: {e}")
            return jsonify({
                'status': 'error',
                'connection': 'unhealthy',
                'error': str(e)
            }), 503

    # ===== CAPITAL MANAGEMENT ENDPOINTS =====

    @app.route('/capital/inject', methods=['POST'])
    def capital_inject():
        """
        Inject capital (deposit) or withdraw from portfolio

        Request body:
        {
            "type": "DEPOSIT" or "WITHDRAW",
            "amount": 500000,
            "notes": "Optional notes"
        }

        Returns:
        {
            "status": "success",
            "transaction": { ... transaction details ... }
        }
        """
        if not db_manager:
            return jsonify({
                'status': 'error',
                'message': 'Database persistence not configured'
            }), 400

        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'Request body required'
                }), 400

            transaction_type = data.get('type')
            amount = data.get('amount')
            notes = data.get('notes')

            if not transaction_type:
                return jsonify({
                    'status': 'error',
                    'message': 'type is required (DEPOSIT or WITHDRAW)'
                }), 400

            if not amount or amount <= 0:
                return jsonify({
                    'status': 'error',
                    'message': 'amount must be a positive number'
                }), 400

            # Execute the capital transaction
            result = db_manager.inject_capital(
                transaction_type=transaction_type.upper(),
                amount=float(amount),
                notes=notes,
                created_by='API'
            )

            # Reload equity in PortfolioStateManager
            engine.portfolio.reload_equity_from_db()

            return jsonify({
                'status': 'success',
                'transaction': result,
                'message': f"Successfully processed {transaction_type} of ₹{amount:,.2f}"
            }), 200

        except ValueError as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400
        except RuntimeError as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400
        except Exception as e:
            logger.error(f"Capital injection failed: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Internal error: {str(e)}'
            }), 500

    @app.route('/capital/transactions', methods=['GET'])
    def capital_transactions():
        """
        Get capital transaction history

        Query params:
        - limit: Maximum number of transactions (default 50)
        - type: Filter by DEPOSIT or WITHDRAW
        """
        if not db_manager:
            return jsonify({
                'status': 'error',
                'message': 'Database persistence not configured'
            }), 400

        try:
            limit = request.args.get('limit', 50, type=int)
            transaction_type = request.args.get('type')

            transactions = db_manager.get_capital_transactions(
                limit=limit,
                transaction_type=transaction_type.upper() if transaction_type else None
            )

            # Convert Decimal to float for JSON serialization
            for tx in transactions:
                tx['amount'] = float(tx['amount'])
                tx['equity_before'] = float(tx['equity_before'])
                tx['equity_after'] = float(tx['equity_after'])
                if tx.get('created_at'):
                    tx['created_at'] = tx['created_at'].isoformat()

            return jsonify({
                'status': 'success',
                'transactions': transactions,
                'count': len(transactions)
            }), 200

        except Exception as e:
            logger.error(f"Failed to get capital transactions: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    @app.route('/capital/summary', methods=['GET'])
    def capital_summary():
        """Get summary of all capital transactions"""
        if not db_manager:
            return jsonify({
                'status': 'error',
                'message': 'Database persistence not configured'
            }), 400

        try:
            summary = db_manager.get_capital_summary()
            return jsonify({
                'status': 'success',
                'summary': summary
            }), 200

        except Exception as e:
            logger.error(f"Failed to get capital summary: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    @app.route('/status', methods=['GET'])
    def status():
        """Get current portfolio status with full details (cached for 2 seconds)"""
        # Check cache first - reduces load during frontend polling
        cached = response_cache.get('status', max_age_seconds=2.0)
        if cached:
            return jsonify(cached), 200

        state = engine.portfolio.get_current_state()
        response_data = {
            # Equity breakdown
            'equity': state.equity,
            'closedEquity': state.closed_equity,
            'openEquity': state.open_equity,
            'blendedEquity': state.blended_equity,

            # Position summary
            'positionCount': len(state.get_open_positions()),

            # Risk metrics
            'totalRiskAmount': state.total_risk_amount,
            'totalRiskPercent': state.total_risk_percent,
            'goldRiskPercent': state.gold_risk_percent,
            'bankniftyRiskPercent': state.banknifty_risk_percent,

            # Volatility metrics
            'totalVolAmount': state.total_vol_amount,
            'totalVolPercent': state.total_vol_percent,
            'goldVolPercent': state.gold_vol_percent,
            'bankniftyVolPercent': state.banknifty_vol_percent,

            # Margin metrics
            'marginUsed': state.margin_used,
            'marginAvailable': state.margin_available,
            'marginUtilizationPercent': state.margin_utilization_percent,

            # Trading stats
            'stats': engine.stats,

            # Timestamp
            'timestamp': state.timestamp.isoformat() if state.timestamp else datetime.now().isoformat()
        }

        # Cache the response
        response_cache.set('status', response_data)
        return jsonify(response_data), 200

    @app.route('/positions', methods=['GET'])
    def positions():
        """Get all open positions"""
        state = engine.portfolio.get_current_state()
        positions_data = {}
        for pos_id, pos in state.get_open_positions().items():
            positions_data[pos_id] = {
                'instrument': pos.instrument,
                'lots': pos.lots,
                'entry_price': pos.entry_price,
                'current_stop': pos.current_stop,
                'expiry': pos.expiry,
                'strike': pos.strike,
                'rollover_status': pos.rollover_status,
                'rollover_count': pos.rollover_count
            }
        return jsonify({'positions': positions_data}), 200

    @app.route('/signals', methods=['GET'])
    def signals():
        """
        Get signal history from database

        Query params:
        - limit: Max number of signals (default: 50, max: 200)
        - instrument: Filter by instrument (GOLD_MINI, BANK_NIFTY)
        - status: Filter by processing status (executed, blocked, rejected)
        """
        limit = min(int(request.args.get('limit', 50)), 200)
        instrument_filter = request.args.get('instrument')
        status_filter = request.args.get('status')

        if not db_manager:
            return jsonify({
                'signals': [],
                'message': 'Database not configured - no signal history available'
            }), 200

        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                query = """
                    SELECT id, instrument, signal_type, position, signal_timestamp,
                           processing_status, processed_at, payload
                    FROM signal_log
                    WHERE 1=1
                """
                params = []

                if instrument_filter:
                    query += " AND instrument = %s"
                    params.append(instrument_filter)

                if status_filter:
                    query += " AND processing_status = %s"
                    params.append(status_filter)

                query += " ORDER BY processed_at DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                signals_data = []
                for row in rows:
                    # Extract payload data safely
                    payload = row['payload'] if row['payload'] else {}

                    signal = {
                        'id': row['id'],
                        'instrument': row['instrument'],
                        'signal_type': row['signal_type'],
                        'position': row['position'],
                        # Use 'timestamp' to match frontend SignalRecord interface
                        'timestamp': row['signal_timestamp'].isoformat() if row['signal_timestamp'] else None,
                        'status': row['processing_status'],
                        'processedAt': row['processed_at'].isoformat() if row['processed_at'] else None,
                        'price': payload.get('price', 0),
                        'stop': payload.get('stop', 0),
                        # Try 'lots' first, then 'suggested_lots' as fallback
                        'lots': payload.get('lots') or payload.get('suggested_lots', 0)
                    }
                    signals_data.append(signal)

                return jsonify({
                    'signals': signals_data,
                    'count': len(signals_data),
                    'limit': limit
                }), 200

        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            return jsonify({
                'signals': [],
                'error': str(e)
            }), 500

    @app.route('/trades', methods=['GET'])
    def trades():
        """
        Get trade/position history from database

        Query params:
        - limit: Max number of trades (default: 50, max: 200)
        - instrument: Filter by instrument (GOLD_MINI, BANK_NIFTY)
        - status: Filter by status (open, closed)
        """
        limit = min(int(request.args.get('limit', 50)), 200)
        instrument_filter = request.args.get('instrument')
        status_filter = request.args.get('status', 'closed')  # Default to closed trades

        if not db_manager:
            return jsonify({
                'trades': [],
                'message': 'Database not configured - no trade history available'
            }), 200

        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                query = """
                    SELECT position_id, instrument, status, entry_timestamp, entry_price,
                           lots, quantity, initial_stop, current_stop, highest_close,
                           unrealized_pnl, realized_pnl, atr, is_base_position,
                           rollover_status, rollover_count, expiry, strike,
                           futures_symbol, contract_month, created_at, updated_at,
                           exit_timestamp, exit_price, exit_reason
                    FROM portfolio_positions
                    WHERE 1=1
                """
                params = []

                if instrument_filter:
                    query += " AND instrument = %s"
                    params.append(instrument_filter)

                if status_filter:
                    query += " AND status = %s"
                    params.append(status_filter)

                query += " ORDER BY entry_timestamp DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                trades_data = []
                for row in rows:
                    trade = {
                        'id': row['position_id'],
                        'instrument': row['instrument'],
                        'status': row['status'],
                        'entryTimestamp': row['entry_timestamp'].isoformat() if row['entry_timestamp'] else None,
                        'entryPrice': float(row['entry_price']) if row['entry_price'] else None,
                        'lots': row['lots'],
                        'quantity': row['quantity'],
                        'initialStop': float(row['initial_stop']) if row['initial_stop'] else None,
                        'currentStop': float(row['current_stop']) if row['current_stop'] else None,
                        'highestClose': float(row['highest_close']) if row['highest_close'] else None,
                        'unrealizedPnl': float(row['unrealized_pnl']) if row['unrealized_pnl'] else 0,
                        'realizedPnl': float(row['realized_pnl']) if row['realized_pnl'] else 0,
                        'atr': float(row['atr']) if row['atr'] else None,
                        'isBasePosition': row['is_base_position'],
                        'rolloverStatus': row['rollover_status'],
                        'rolloverCount': row['rollover_count'],
                        'expiry': row['expiry'],
                        'strike': row['strike'],
                        'futuresSymbol': row['futures_symbol'],
                        'contractMonth': row['contract_month'],
                        'createdAt': row['created_at'].isoformat() if row['created_at'] else None,
                        'updatedAt': row['updated_at'].isoformat() if row['updated_at'] else None,
                        # Exit data (for closed positions)
                        'exitTimestamp': row['exit_timestamp'].isoformat() if row.get('exit_timestamp') else None,
                        'exitPrice': float(row['exit_price']) if row.get('exit_price') else None,
                        'exitReason': row.get('exit_reason')
                    }
                    trades_data.append(trade)

                return jsonify({
                    'trades': trades_data,
                    'count': len(trades_data),
                    'limit': limit
                }), 200

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return jsonify({
                'trades': [],
                'error': str(e)
            }), 500

    # =========================================================================
    # STRATEGY MANAGEMENT ENDPOINTS
    # =========================================================================

    @app.route('/strategies', methods=['GET'])
    def list_strategies():
        """
        Get all trading strategies

        Query params:
        - include_inactive: Include inactive strategies (default: false)
        """
        if not strategy_manager:
            return jsonify({
                'strategies': [],
                'message': 'Strategy manager not initialized'
            }), 200

        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

        try:
            strategies = strategy_manager.get_all_strategies(include_inactive=include_inactive)
            return jsonify({
                'strategies': [s.to_dict() for s in strategies],
                'count': len(strategies)
            }), 200
        except Exception as e:
            logger.error(f"Error fetching strategies: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/strategies', methods=['POST'])
    def create_strategy():
        """
        Create a new trading strategy

        Body: { "name": "Strategy Name", "description": "Optional", "allocated_capital": 0 }
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        data = request.json
        if not data or not data.get('name'):
            return jsonify({'error': 'Missing required field: name'}), 400

        try:
            strategy = strategy_manager.create_strategy(
                name=data['name'],
                description=data.get('description'),
                allocated_capital=data.get('allocated_capital', 0.0)
            )
            return jsonify({
                'success': True,
                'strategy': strategy.to_dict()
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 409  # Conflict (duplicate name)
        except Exception as e:
            logger.error(f"Error creating strategy: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/strategies/<int:strategy_id>', methods=['GET'])
    def get_strategy(strategy_id):
        """Get a specific strategy by ID"""
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        strategy = strategy_manager.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': f'Strategy {strategy_id} not found'}), 404

        return jsonify({'strategy': strategy.to_dict()}), 200

    @app.route('/strategies/<int:strategy_id>', methods=['PUT'])
    def update_strategy(strategy_id):
        """
        Update a strategy

        Body: { "name": "New Name", "description": "New desc", "allocated_capital": 1000000, "is_active": true }
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        data = request.json or {}

        try:
            strategy = strategy_manager.update_strategy(
                strategy_id=strategy_id,
                name=data.get('name'),
                description=data.get('description'),
                allocated_capital=data.get('allocated_capital'),
                is_active=data.get('is_active')
            )
            if not strategy:
                return jsonify({'error': f'Strategy {strategy_id} not found'}), 404

            return jsonify({
                'success': True,
                'strategy': strategy.to_dict()
            }), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error updating strategy: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/strategies/<int:strategy_id>', methods=['DELETE'])
    def delete_strategy(strategy_id):
        """
        Delete a strategy

        Query params:
        - force: Reassign positions to 'unknown' before deleting (default: false)
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        force = request.args.get('force', 'false').lower() == 'true'

        try:
            success = strategy_manager.delete_strategy(strategy_id, force=force)
            if success:
                return jsonify({'success': True, 'message': f'Strategy {strategy_id} deleted'}), 200
            else:
                return jsonify({'error': f'Strategy {strategy_id} not found'}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error deleting strategy: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/strategies/<int:strategy_id>/positions', methods=['GET'])
    def get_strategy_positions(strategy_id):
        """
        Get positions for a strategy (both PM positions and tagged broker positions)

        Query params:
        - status: Filter by status (open, closed, all) - default: open
        - include_broker: Include tagged broker positions (default: true)
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        status = request.args.get('status', 'open')
        include_broker = request.args.get('include_broker', 'true').lower() == 'true'

        try:
            # Get PM positions for this strategy
            pm_positions = strategy_manager.get_positions_for_strategy(strategy_id, status=status)

            # Get tagged broker positions if requested
            broker_positions = []
            if include_broker and db_manager:
                from psycopg2.extras import RealDictCursor

                with db_manager.get_connection() as conn:
                    cursor = conn.cursor(cursor_factory=RealDictCursor)

                    query = """
                        SELECT
                            bpt.id as tag_id, bpt.symbol, bpt.instrument,
                            bpt.quantity, bpt.entry_price, bpt.tagged_at,
                            bpt.is_active, bpt.closed_at, bpt.exit_price, bpt.realized_pnl
                        FROM broker_position_tags bpt
                        WHERE bpt.strategy_id = %s
                    """
                    params = [strategy_id]

                    if status == 'open':
                        query += " AND bpt.is_active = TRUE"
                    elif status == 'closed':
                        query += " AND bpt.is_active = FALSE"

                    query += " ORDER BY bpt.tagged_at DESC"
                    cursor.execute(query, params)

                    # Get live prices from broker
                    live_prices = {}
                    if broker_sync:
                        bp = broker_sync._fetch_broker_positions()
                        if bp:
                            live_prices = bp

                    for row in cursor.fetchall():
                        pos = dict(row)
                        pos['source'] = 'broker_tag'
                        pos['tagged_at'] = pos['tagged_at'].isoformat() if pos['tagged_at'] else None
                        pos['closed_at'] = pos['closed_at'].isoformat() if pos['closed_at'] else None

                        # Add live data if available
                        if pos['symbol'] in live_prices and pos['is_active']:
                            bp = live_prices[pos['symbol']]
                            pos['current_price'] = bp.get('ltp', 0)
                            pos['broker_pnl'] = bp.get('pnl', 0)
                            pos['current_quantity'] = bp.get('quantity', 0)
                        else:
                            pos['current_price'] = None
                            pos['broker_pnl'] = None
                            pos['current_quantity'] = None

                        broker_positions.append(pos)

            # Mark PM positions with source
            for p in pm_positions:
                p['source'] = 'pm'

            return jsonify({
                'strategy_id': strategy_id,
                'pm_positions': pm_positions,
                'broker_positions': broker_positions,
                'pm_count': len(pm_positions),
                'broker_count': len(broker_positions),
                'total_count': len(pm_positions) + len(broker_positions)
            }), 200
        except Exception as e:
            logger.error(f"Error fetching strategy positions: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/strategies/<int:strategy_id>/pnl', methods=['GET'])
    def get_strategy_pnl(strategy_id):
        """Get P&L summary for a strategy"""
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        # Get open positions for unrealized P&L calculation
        open_positions = engine.portfolio.positions if engine else {}

        pnl = strategy_manager.get_strategy_pnl(strategy_id, open_positions)
        if not pnl:
            return jsonify({'error': f'Strategy {strategy_id} not found'}), 404

        return jsonify({'pnl': pnl.to_dict()}), 200

    @app.route('/strategies/<int:strategy_id>/trades', methods=['GET'])
    def get_strategy_trades(strategy_id):
        """
        Get trade history for a strategy

        Query params:
        - limit: Max trades to return (default: 100)
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        limit = min(int(request.args.get('limit', 100)), 500)

        try:
            trades = strategy_manager.get_trade_history(strategy_id, limit=limit)
            return jsonify({
                'strategy_id': strategy_id,
                'trades': [t.to_dict() for t in trades],
                'count': len(trades)
            }), 200
        except Exception as e:
            logger.error(f"Error fetching strategy trades: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/positions/<position_id>/strategy', methods=['PUT'])
    def reassign_position_strategy(position_id):
        """
        Reassign a position to a different strategy

        Body: { "strategy_id": 2 }
        """
        if not strategy_manager:
            return jsonify({'error': 'Strategy manager not initialized'}), 500

        data = request.json
        if not data or 'strategy_id' not in data:
            return jsonify({'error': 'Missing required field: strategy_id'}), 400

        try:
            success = strategy_manager.reassign_position(position_id, data['strategy_id'])
            if success:
                # Invalidate cache
                response_cache.invalidate()
                return jsonify({
                    'success': True,
                    'message': f'Position {position_id} reassigned to strategy {data["strategy_id"]}'
                }), 200
            else:
                return jsonify({'error': f'Position {position_id} not found'}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error reassigning position: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/analyzer/orders', methods=['GET'])
    def analyzer_orders():
        """Get simulated orders (analyzer mode only)"""
        from brokers.factory import AnalyzerBrokerWrapper

        if isinstance(openalgo, AnalyzerBrokerWrapper):
            orders = openalgo.get_simulated_orders()
            summary = openalgo.get_simulated_orders_summary()
            return jsonify({
                'mode': 'analyzer',
                'total_orders': len(orders),
                'orders': orders,
                'summary': summary
            }), 200
        else:
            return jsonify({
                'mode': 'live',
                'message': 'Not in analyzer mode - no simulated orders',
                'orders': []
            }), 200

    # Rollover endpoints
    @app.route('/rollover/status', methods=['GET'])
    def rollover_status():
        """Get rollover status"""
        return jsonify(engine.get_rollover_status()), 200

    @app.route('/rollover/scan', methods=['GET'])
    def rollover_scan():
        """Scan for rollover candidates (no execution)"""
        scan_result = engine.scan_rollover_candidates()
        return jsonify({
            'timestamp': scan_result.scan_timestamp.isoformat(),
            'total_positions': scan_result.total_positions,
            'positions_to_roll': scan_result.positions_to_roll,
            'candidates': [
                {
                    'position_id': c.position.position_id,
                    'instrument': c.instrument,
                    'days_to_expiry': c.days_to_expiry,
                    'current_expiry': c.current_expiry,
                    'next_expiry': c.next_expiry,
                    'reason': c.reason
                }
                for c in scan_result.candidates
            ],
            'errors': scan_result.errors
        }), 200

    @app.route('/rollover/execute', methods=['POST'])
    def rollover_execute():
        """Execute rollover for all candidates"""
        dry_run = request.json.get('dry_run', False) if request.json else False

        if rollover_scheduler:
            if dry_run:
                result = rollover_scheduler.dry_run_check()
            else:
                result = rollover_scheduler.force_check()
            return jsonify(result), 200
        else:
            # Rollover disabled, run directly
            batch_result = engine.check_and_rollover_positions(dry_run=dry_run)
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'dry_run': dry_run,
                'total_positions': batch_result.total_positions,
                'successful': batch_result.successful,
                'failed': batch_result.failed,
                'cost': batch_result.total_rollover_cost
            }), 200

    @app.route('/eod/status', methods=['GET'])
    def eod_status():
        """Get EOD pre-close execution status"""
        engine_status = engine.get_eod_status()

        scheduler_status = {}
        if eod_scheduler:
            scheduler_status = eod_scheduler.get_status()

        return jsonify({
            'enabled': engine.config.eod_enabled,
            'scheduler': scheduler_status,
            'engine': engine_status
        }), 200

    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint with real service statuses"""
        # Check if trading is paused
        trading_paused = False
        pause_reason = None
        if safety_manager:
            trading_paused, pause_reason = safety_manager.is_trading_paused()

        # Determine voice announcer status
        voice_status = 'disabled'
        if voice_announcer:
            voice_status = 'silent_mode' if voice_announcer.silent_mode else 'enabled'

        # === REAL SERVICE STATUS CHECKS ===

        # 1. Database status
        database_status = 'offline'
        if db_manager:
            try:
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                database_status = 'online'
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                database_status = 'offline'
        else:
            database_status = 'disabled'

        # 2. Broker status (OpenAlgo connectivity)
        broker_status = 'disconnected'
        broker_error = None
        if openalgo and hasattr(openalgo, 'check_connection'):
            try:
                broker_check = openalgo.check_connection()
                if broker_check.get('connected'):
                    broker_status = 'connected'
                else:
                    broker_status = 'disconnected'
                    broker_error = broker_check.get('error')
            except Exception as e:
                logger.warning(f"Broker health check failed: {e}")
                broker_status = 'disconnected'
                broker_error = str(e)
        elif openalgo:
            # Fallback: assume connected if client exists but no check_connection method
            broker_status = 'connected'
        else:
            broker_status = 'disabled'

        # 3. Webhook status (based on last signal timestamp)
        webhook_status = 'inactive'
        last_signal_timestamp = engine.stats.get('last_signal_timestamp')
        if last_signal_timestamp:
            try:
                last_signal_dt = datetime.fromisoformat(last_signal_timestamp)
                # Consider webhook active if signal received in last 24 hours
                hours_since_signal = (datetime.now() - last_signal_dt).total_seconds() / 3600
                if hours_since_signal < 24:
                    webhook_status = 'active'
                else:
                    webhook_status = 'inactive'
            except Exception:
                webhook_status = 'inactive'
        else:
            # No signals received yet - webhook endpoint exists but no traffic
            webhook_status = 'active'  # Endpoint is available, just no signals

        # Determine overall status
        overall_status = 'healthy'
        if database_status == 'offline' or broker_status == 'disconnected':
            overall_status = 'unhealthy'
        elif database_status == 'disabled' or broker_status == 'disabled':
            overall_status = 'degraded'

        return jsonify({
            'status': overall_status,
            'timestamp': datetime.now().isoformat(),
            # Real service statuses for frontend SystemHealth component
            'database': database_status,
            'broker': broker_status,
            'broker_error': broker_error,
            'webhook': webhook_status,
            'last_signal_timestamp': last_signal_timestamp,
            # Existing fields
            'test_mode': engine.test_mode,
            'silent_mode': voice_announcer.silent_mode if voice_announcer else False,
            'rollover_scheduler': 'running' if rollover_scheduler else 'disabled',
            'eod_scheduler': 'running' if (eod_scheduler and eod_scheduler.is_running()) else 'disabled',
            'voice_announcer': voice_status,
            'telegram_notifier': 'enabled' if telegram_notifier else 'disabled',
            'safety_manager': 'enabled' if safety_manager else 'disabled',
            'broker_sync': 'running' if (broker_sync and broker_sync._sync_thread and broker_sync._sync_thread.is_alive()) else 'disabled',
            'trading_paused': trading_paused,
            'pause_reason': pause_reason
        }), 200

    # =========================================================================
    # TEST MODE ENDPOINTS
    # =========================================================================

    @app.route('/test/status', methods=['GET'])
    def test_status():
        """Get test mode status and test positions"""
        test_positions = []
        for pos_id, pos in engine.portfolio.positions.items():
            if hasattr(pos, 'is_test') and pos.is_test:
                test_positions.append({
                    'position_id': pos_id,
                    'instrument': pos.instrument,
                    'lots': pos.lots,
                    'original_lots': pos.original_lots,
                    'entry_price': pos.entry_price,
                    'entry_timestamp': pos.entry_timestamp.isoformat() if pos.entry_timestamp else None,
                    'unrealized_pnl': pos.unrealized_pnl
                })

        return jsonify({
            'test_mode': engine.test_mode,
            'test_positions_count': len(test_positions),
            'test_positions': test_positions
        }), 200

    @app.route('/test/clear', methods=['POST'])
    def test_clear():
        """Clear all test positions from portfolio and database"""
        if not engine.test_mode:
            return jsonify({
                'success': False,
                'error': 'Not in test mode. Start PM with --test-mode to use this endpoint.'
            }), 400

        cleared_positions = []
        positions_to_remove = []

        # Find all test positions
        for pos_id, pos in list(engine.portfolio.positions.items()):
            if hasattr(pos, 'is_test') and pos.is_test:
                positions_to_remove.append(pos_id)
                cleared_positions.append({
                    'position_id': pos_id,
                    'instrument': pos.instrument,
                    'lots': pos.lots,
                    'original_lots': pos.original_lots
                })

        # Remove from portfolio
        for pos_id in positions_to_remove:
            if pos_id in engine.portfolio.positions:
                del engine.portfolio.positions[pos_id]
            # Also clear from base_positions if present
            # Position ID format: {instrument}_{layer} e.g., BANK_NIFTY_Long_1, GOLD_MINI_Long_2
            if 'BANK_NIFTY' in pos_id:
                instrument = 'BANK_NIFTY'
            elif 'GOLD_MINI' in pos_id:
                instrument = 'GOLD_MINI'
            else:
                instrument = None
            if instrument and instrument in engine.base_positions:
                if engine.base_positions[instrument].position_id == pos_id:
                    del engine.base_positions[instrument]
                    if instrument in engine.last_pyramid_price:
                        del engine.last_pyramid_price[instrument]

        # Clear from database
        if db_manager:
            try:
                # Delete test positions from database
                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM portfolio_positions WHERE is_test = TRUE"
                        )
                        deleted_count = cur.rowcount
                    conn.commit()
                logger.info(f"Cleared {deleted_count} test positions from database")
            except Exception as e:
                logger.warning(f"Failed to clear test positions from database: {e}")

        logger.warning(f"🧪 [TEST MODE] Cleared {len(cleared_positions)} test positions")

        return jsonify({
            'success': True,
            'cleared_count': len(cleared_positions),
            'cleared_positions': cleared_positions,
            'message': f'Cleared {len(cleared_positions)} test positions'
        }), 200

    # =========================================================================
    # VOICE ANNOUNCER ENDPOINTS
    # =========================================================================

    @app.route('/voice/status', methods=['GET'])
    def voice_status():
        """Get voice announcer status and pending errors"""
        if not voice_announcer:
            return jsonify({
                'enabled': False,
                'silentMode': False,
                'message': 'Voice announcer not initialized'
            }), 200

        return jsonify({
            'enabled': voice_announcer.enabled,
            'silentMode': voice_announcer.silent_mode,
            'pendingErrors': [
                {
                    'id': e['id'],
                    'message': e['message'],
                    'type': e['type'],
                    'timestamp': e['timestamp'].isoformat()
                }
                for e in voice_announcer.get_pending_errors()
            ],
            'errorRepeatInterval': voice_announcer.error_repeat_interval
        }), 200

    @app.route('/voice/acknowledge', methods=['POST'])
    def voice_acknowledge():
        """
        Acknowledge errors to stop repeat announcements

        Body: { "errorId": "optional_specific_id" }
        If errorId not provided, acknowledges ALL pending errors
        """
        if not voice_announcer:
            return jsonify({
                'success': False,
                'message': 'Voice announcer not initialized'
            }), 400

        error_id = request.json.get('errorId') if request.json else None

        success = voice_announcer.acknowledge_error(error_id)

        return jsonify({
            'success': success,
            'acknowledged': error_id or 'all',
            'remainingErrors': len(voice_announcer.get_pending_errors())
        }), 200

    @app.route('/voice/test', methods=['POST'])
    def voice_test():
        """Test voice announcement"""
        if not voice_announcer:
            return jsonify({
                'success': False,
                'message': 'Voice announcer not initialized'
            }), 400

        test_type = request.json.get('type', 'info') if request.json else 'info'

        if test_type == 'pre_trade':
            voice_announcer.announce_pre_trade(
                instrument='GOLD_MINI',
                position='Long_1',
                signal_type='BASE_ENTRY',
                lots=2,
                price=78500,
                stop=77800,
                risk_amount=14000,
                risk_percent=0.28
            )
        elif test_type == 'post_trade':
            voice_announcer.announce_trade_executed(
                instrument='GOLD_MINI',
                position='Long_1',
                signal_type='BASE_ENTRY',
                lots=2,
                price=78500
            )
        elif test_type == 'error':
            voice_announcer.announce_error(
                'Test error message. This is a test.',
                error_type='test'
            )
        else:
            voice_announcer._speak('Voice announcer is working correctly.', voice="Alex")

        return jsonify({
            'success': True,
            'message': f'Test announcement ({test_type}) triggered'
        }), 200

    @app.route('/voice/silent-mode', methods=['POST'])
    def toggle_silent_mode():
        """
        Toggle or set silent mode for voice announcements.

        Request body:
        - enabled: bool (optional) - If provided, sets silent mode to this value.
                   If not provided, toggles current state.

        Returns:
        - silentMode: Current state after change
        - message: Description of action taken
        """
        if not voice_announcer:
            return jsonify({
                'success': False,
                'message': 'Voice announcer not initialized'
            }), 400

        data = request.json or {}

        current_state = voice_announcer.silent_mode
        logger.info(f"Silent mode toggle: current={current_state}, request={data}")

        if 'enabled' in data:
            # Set to specific value
            new_state = bool(data['enabled'])
        else:
            # Toggle current state
            new_state = not voice_announcer.silent_mode

        logger.info(f"Silent mode toggle: new_state={new_state}")

        # Announce the change
        if new_state:
            # Enabling silent mode - announce first, then go silent
            voice_announcer._speak("Silent mode enabled. Going quiet now.")
            voice_announcer.silent_mode = True
            voice_announcer.enabled = False
        else:
            # Disabling silent mode - enable first, then announce
            voice_announcer.silent_mode = False
            voice_announcer.enabled = True  # Re-enable TTS
            voice_announcer._speak("Voice announcements activated.")

        action = 'enabled' if new_state else 'disabled'
        logger.info(f"Silent mode {action} via API")

        return jsonify({
            'success': True,
            'silentMode': new_state,
            'message': f'Silent mode {action}'
        }), 200

    # =========================================================================
    # HOLIDAY CALENDAR ENDPOINTS
    # =========================================================================

    @app.route('/holidays/status', methods=['GET'])
    def holiday_status():
        """Get current holiday status for today"""
        if not holiday_calendar:
            return jsonify({'error': 'Holiday calendar not initialized'}), 500

        return jsonify(holiday_calendar.get_status()), 200

    @app.route('/holidays/<exchange>', methods=['GET'])
    def get_holidays(exchange):
        """
        Get holidays for an exchange.

        Query params:
        - year: Filter by year (optional)
        """
        if not holiday_calendar:
            return jsonify({'error': 'Holiday calendar not initialized'}), 500

        exchange = exchange.upper()
        if exchange not in ['NSE', 'MCX']:
            return jsonify({'error': f'Invalid exchange: {exchange}'}), 400

        year = request.args.get('year', type=int)
        holidays = holiday_calendar.get_holidays(exchange=exchange, year=year)

        return jsonify({
            'exchange': exchange,
            'year': year,
            'count': len(holidays),
            'holidays': [h.to_dict() for h in holidays]
        }), 200

    @app.route('/holidays/<exchange>', methods=['POST'])
    def add_holiday(exchange):
        """
        Add a holiday.

        Body: { "date": "2025-12-25", "description": "Christmas" }
        """
        if not holiday_calendar:
            return jsonify({'error': 'Holiday calendar not initialized'}), 500

        exchange = exchange.upper()
        if exchange not in ['NSE', 'MCX']:
            return jsonify({'error': f'Invalid exchange: {exchange}'}), 400

        data = request.json
        if not data or 'date' not in data:
            return jsonify({'error': 'Missing date field'}), 400

        try:
            from datetime import date as dt_date
            holiday_date = dt_date.fromisoformat(data['date'])
            description = data.get('description', '')

            success = holiday_calendar.add_holiday(holiday_date, exchange, description)

            if success:
                return jsonify({
                    'success': True,
                    'message': f'Holiday added: {holiday_date} {exchange}'
                }), 201
            else:
                return jsonify({
                    'success': False,
                    'message': 'Holiday already exists'
                }), 409
        except ValueError as e:
            return jsonify({'error': f'Invalid date format: {e}'}), 400

    @app.route('/holidays/<exchange>/<date_str>', methods=['DELETE'])
    def remove_holiday(exchange, date_str):
        """Remove a holiday."""
        if not holiday_calendar:
            return jsonify({'error': 'Holiday calendar not initialized'}), 500

        exchange = exchange.upper()
        if exchange not in ['NSE', 'MCX']:
            return jsonify({'error': f'Invalid exchange: {exchange}'}), 400

        try:
            from datetime import date as dt_date
            holiday_date = dt_date.fromisoformat(date_str)

            success = holiday_calendar.remove_holiday(holiday_date, exchange)

            if success:
                return jsonify({
                    'success': True,
                    'message': f'Holiday removed: {holiday_date} {exchange}'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'Holiday not found'
                }), 404
        except ValueError as e:
            return jsonify({'error': f'Invalid date format: {e}'}), 400

    @app.route('/holidays/upload', methods=['POST'])
    def upload_holidays():
        """
        Upload holidays from CSV.

        Body: { "exchange": "NSE", "csv_path": "/path/to/holidays.csv" }
        Or multipart form with 'file' and 'exchange'
        """
        if not holiday_calendar:
            return jsonify({'error': 'Holiday calendar not initialized'}), 500

        # Handle JSON body
        if request.is_json:
            data = request.json
            csv_path = data.get('csv_path')
            exchange = data.get('exchange', '').upper() or None

            if not csv_path:
                return jsonify({'error': 'Missing csv_path'}), 400

            count = holiday_calendar.load_from_csv(csv_path, exchange=exchange)

            return jsonify({
                'success': True,
                'message': f'Loaded {count} holidays from CSV',
                'count': count
            }), 200

        return jsonify({'error': 'JSON body required'}), 400

    @app.route('/config', methods=['GET'])
    def get_config():
        """
        Get current configuration (read-only)

        Returns all trading configuration including:
        - Instrument settings (lot sizes, margins, ATR multipliers)
        - Portfolio risk parameters (Tom Basso limits)
        - Pyramid gate thresholds
        - Rollover settings
        - EOD execution settings
        """
        from core.config import INSTRUMENT_CONFIGS, PortfolioConfig
        from core.models import InstrumentType

        config = engine.config if engine else PortfolioConfig()

        # Build instrument configs
        instruments = {}
        for inst_type, inst_config in INSTRUMENT_CONFIGS.items():
            instruments[inst_type.value] = {
                'name': inst_config.name,
                'lotSize': inst_config.lot_size,
                'pointValue': inst_config.point_value,
                'marginPerLot': inst_config.margin_per_lot,
                'initialRiskPercent': inst_config.initial_risk_percent,
                'ongoingRiskPercent': inst_config.ongoing_risk_percent,
                'initialVolPercent': inst_config.initial_vol_percent,
                'ongoingVolPercent': inst_config.ongoing_vol_percent,
                'initialAtrMult': inst_config.initial_atr_mult,
                'trailingAtrMult': inst_config.trailing_atr_mult,
                'maxPyramids': inst_config.max_pyramids
            }

        return jsonify({
            'instruments': instruments,
            'portfolio': {
                'maxPortfolioRiskPercent': config.max_portfolio_risk_percent,
                'maxPortfolioVolPercent': config.max_portfolio_vol_percent,
                'maxMarginUtilizationPercent': config.max_margin_utilization_percent
            },
            'pyramidGates': {
                'riskWarning': config.pyramid_risk_warning,
                'riskBlock': config.pyramid_risk_block,
                'volBlock': config.pyramid_vol_block,
                'use1RGate': config.use_1r_gate,
                'atrPyramidSpacing': config.atr_pyramid_spacing
            },
            'equity': {
                'mode': config.equity_mode,
                'blendedUnrealizedWeight': config.blended_unrealized_weight
            },
            'rollover': {
                'enabled': config.enable_auto_rollover,
                'bankNiftyDays': config.banknifty_rollover_days,
                'goldMiniDays': config.gold_mini_rollover_days,
                'initialBufferPct': config.rollover_initial_buffer_pct,
                'incrementPct': config.rollover_increment_pct,
                'maxRetries': config.rollover_max_retries,
                'retryIntervalSec': config.rollover_retry_interval_sec,
                'strikeInterval': config.rollover_strike_interval,
                'prefer1000s': config.rollover_prefer_1000s
            },
            'marketHours': {
                'nseStart': config.nse_market_start,
                'nseEnd': config.nse_market_end,
                'mcxStart': config.mcx_market_start,
                'mcxEnd': config.mcx_market_end,
                'mcxSummerClose': config.mcx_summer_close,
                'mcxWinterClose': config.mcx_winter_close
            },
            'eod': {
                'enabled': config.eod_enabled,
                'monitoringStartMinutes': config.eod_monitoring_start_minutes,
                'conditionCheckSeconds': config.eod_condition_check_seconds,
                'executionSeconds': config.eod_execution_seconds,
                'trackingSeconds': config.eod_tracking_seconds,
                'orderTimeout': config.eod_order_timeout,
                'trackingPollInterval': config.eod_tracking_poll_interval,
                'limitBufferPct': config.eod_limit_buffer_pct,
                'fallbackToMarket': config.eod_fallback_to_market,
                'fallbackSeconds': config.eod_fallback_seconds,
                'maxSignalAgeSeconds': config.eod_max_signal_age_seconds,
                'marketCloseTimes': config.market_close_times,
                'instrumentsEnabled': config.eod_instruments_enabled
            },
            'execution': {
                'strategy': config.execution_strategy,
                'signalValidationEnabled': config.signal_validation_enabled,
                'partialFillStrategy': config.partial_fill_strategy,
                'partialFillWaitTimeout': config.partial_fill_wait_timeout
            },
            'peelOff': {
                'enabled': config.enable_peel_off,
                'checkInterval': config.peel_off_check_interval
            },
            '_meta': {
                'readOnly': True,
                'note': 'Configuration changes require backend restart. Edit core/config.py directly.',
                'timestamp': datetime.now().isoformat()
            }
        }), 200

    # =========================================================================
    # Emergency / Kill Switch Endpoints
    # =========================================================================

    @app.route('/emergency/stop', methods=['POST'])
    def emergency_stop():
        """
        KILL SWITCH - Pause all trading

        Trading will be paused and all new signals rejected until resumed.
        Requires X-API-KEY header matching EMERGENCY_API_KEY env var.
        """
        # Authentication check
        api_key = request.headers.get('X-API-KEY')
        expected_key = os.environ.get('EMERGENCY_API_KEY')
        if not expected_key or api_key != expected_key:
            return jsonify({'error': 'Unauthorized', 'message': 'Valid X-API-KEY header required'}), 401

        reason = request.json.get('reason', 'Manual stop via API') if request.json else 'Manual stop via API'

        if safety_manager:
            success = safety_manager.pause_trading(reason)
            if success:
                return jsonify({
                    'success': True,
                    'message': f'Trading PAUSED: {reason}',
                    'status': 'paused'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'Trading already paused'
                }), 400
        else:
            return jsonify({
                'success': False,
                'message': 'Safety manager not initialized'
            }), 500

    @app.route('/emergency/resume', methods=['POST'])
    def emergency_resume():
        """
        Resume trading after pause.
        Requires X-API-KEY header matching EMERGENCY_API_KEY env var.
        """
        # Authentication check
        api_key = request.headers.get('X-API-KEY')
        expected_key = os.environ.get('EMERGENCY_API_KEY')
        if not expected_key or api_key != expected_key:
            return jsonify({'error': 'Unauthorized', 'message': 'Valid X-API-KEY header required'}), 401

        if safety_manager:
            success = safety_manager.resume_trading()
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Trading RESUMED',
                    'status': 'active'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'Trading was not paused'
                }), 400
        else:
            return jsonify({
                'success': False,
                'message': 'Safety manager not initialized'
            }), 500

    @app.route('/emergency/close-all', methods=['POST'])
    def emergency_close_all():
        """
        EMERGENCY: Close all open positions at market price

        This will immediately exit all positions. Use with caution!
        Requires X-API-KEY header matching EMERGENCY_API_KEY env var.
        """
        # Authentication check
        api_key = request.headers.get('X-API-KEY')
        expected_key = os.environ.get('EMERGENCY_API_KEY')
        if not expected_key or api_key != expected_key:
            return jsonify({'error': 'Unauthorized', 'message': 'Valid X-API-KEY header required'}), 401

        dry_run = request.json.get('dry_run', True) if request.json else True

        state = engine.portfolio.get_current_state()
        positions = state.get_open_positions()

        if not positions:
            return jsonify({
                'success': True,
                'message': 'No open positions to close',
                'closed': []
            }), 200

        # First, pause trading to prevent new entries
        if safety_manager:
            safety_manager.pause_trading("Emergency close-all initiated")

        results = []
        for pos_id, pos in positions.items():
            if dry_run:
                results.append({
                    'position_id': pos_id,
                    'instrument': pos.instrument,
                    'lots': pos.lots,
                    'status': 'DRY_RUN - Would close'
                })
            else:
                try:
                    # Create exit signal and process
                    # TODO: Implement actual market exit via order_executor
                    results.append({
                        'position_id': pos_id,
                        'instrument': pos.instrument,
                        'lots': pos.lots,
                        'status': 'CLOSE_REQUESTED'
                    })
                except Exception as e:
                    results.append({
                        'position_id': pos_id,
                        'instrument': pos.instrument,
                        'lots': pos.lots,
                        'status': f'ERROR: {str(e)}'
                    })

        # Alert
        if telegram_notifier:
            telegram_notifier.send_alert(
                f"🚨 EMERGENCY CLOSE-ALL\n"
                f"Dry Run: {dry_run}\n"
                f"Positions: {len(positions)}"
            )

        return jsonify({
            'success': True,
            'message': f'Emergency close-all {"(DRY RUN)" if dry_run else "EXECUTED"}',
            'dry_run': dry_run,
            'positions_count': len(positions),
            'results': results
        }), 200

    @app.route('/safety/status', methods=['GET'])
    def safety_status():
        """Get current safety status"""
        if safety_manager:
            return jsonify(safety_manager.get_status()), 200
        else:
            return jsonify({'error': 'Safety manager not initialized'}), 500

    # =========================================================================
    # Broker Sync Endpoints
    # =========================================================================

    @app.route('/sync/broker', methods=['POST'])
    def sync_broker():
        """
        Manually trigger broker position sync

        Compares PM positions with actual broker positions and reports discrepancies.
        """
        if not broker_sync:
            return jsonify({
                'success': False,
                'message': 'Broker sync not initialized'
            }), 500

        result = broker_sync.sync_now()

        discrepancies_data = []
        for d in result.discrepancies:
            discrepancies_data.append({
                'type': d.discrepancy_type,
                'instrument': d.instrument,
                'pm_lots': d.pm_lots,
                'broker_lots': d.broker_lots,
                'details': d.details
            })

        return jsonify({
            'success': result.success,
            'timestamp': result.timestamp.isoformat(),
            'pm_positions': result.pm_positions,
            'broker_positions': result.broker_positions,
            'discrepancy_count': len(result.discrepancies),
            'discrepancies': discrepancies_data,
            'error': result.error
        }), 200 if result.success else 500

    @app.route('/sync/status', methods=['GET'])
    def sync_status():
        """Get broker sync status"""
        if broker_sync:
            return jsonify(broker_sync.get_status()), 200
        else:
            return jsonify({'error': 'Broker sync not initialized'}), 500

    # =========================================================================
    # Broker Position Viewing & Import Endpoints
    # =========================================================================

    @app.route('/broker/positions', methods=['GET'])
    def get_broker_positions():
        """
        Get current broker positions with PM match status

        Returns list of positions from broker, each marked as:
        - matched: Position exists in PM
        - unmatched: Position exists at broker but not in PM (can be imported)
        """
        if not broker_sync:
            return jsonify({'error': 'Broker sync not initialized'}), 500

        try:
            # Get broker positions
            broker_positions = broker_sync._fetch_broker_positions()
            if broker_positions is None:
                return jsonify({'error': 'Failed to fetch broker positions'}), 500

            # Get PM positions for matching
            pm_state = engine.portfolio.get_current_state() if engine else None
            pm_positions = pm_state.get_open_positions() if pm_state else {}

            # Build PM symbol set for matching
            pm_symbols = set()
            for pos_id, pos in pm_positions.items():
                # Add various symbol formats that might match
                if hasattr(pos, 'futures_symbol') and pos.futures_symbol:
                    pm_symbols.add(pos.futures_symbol.upper())
                if hasattr(pos, 'pe_symbol') and pos.pe_symbol:
                    pm_symbols.add(pos.pe_symbol.upper())
                if hasattr(pos, 'ce_symbol') and pos.ce_symbol:
                    pm_symbols.add(pos.ce_symbol.upper())

            # Get tagged positions from database
            tagged_symbols = {}  # symbol -> {strategy_id, strategy_name, tag_id}
            if db_manager:
                try:
                    from psycopg2.extras import RealDictCursor
                    with db_manager.get_connection() as conn:
                        cursor = conn.cursor(cursor_factory=RealDictCursor)
                        cursor.execute("""
                            SELECT bpt.id as tag_id, bpt.symbol, bpt.strategy_id, ts.strategy_name
                            FROM broker_position_tags bpt
                            JOIN trading_strategies ts ON ts.strategy_id = bpt.strategy_id
                            WHERE bpt.is_active = TRUE
                        """)
                        for row in cursor.fetchall():
                            tagged_symbols[row['symbol'].upper()] = {
                                'tag_id': row['tag_id'],
                                'strategy_id': row['strategy_id'],
                                'strategy_name': row['strategy_name']
                            }
                except Exception as e:
                    logger.warning(f"Failed to fetch tagged positions: {e}")

            # Build response with match status
            positions_list = []

            for symbol, pos_data in broker_positions.items():
                quantity = pos_data.get('quantity', 0)
                if quantity == 0:
                    continue  # Skip zero positions

                # Determine instrument type and lot size divisor
                # NOTE: MCX futures return quantity as lot count directly (divisor = 1)
                #       NSE/BFO options return quantity in units (divide by lot size)
                symbol_upper = symbol.upper()
                if 'GOLDM' in symbol_upper and 'FUT' in symbol_upper:
                    # MCX Gold Mini futures - broker returns lots directly
                    instrument = 'GOLD_MINI'
                    lot_size = 1
                elif 'SILVERM' in symbol_upper and 'FUT' in symbol_upper:
                    # MCX Silver Mini futures - broker returns lots directly
                    instrument = 'SILVER_MINI'
                    lot_size = 1
                elif 'GOLD' in symbol_upper or 'GOLDM' in symbol_upper:
                    # Gold options or other gold instruments
                    instrument = 'GOLD_MINI'
                    lot_size = 100
                elif 'BANKNIFTY' in symbol_upper or 'NIFTYBANK' in symbol_upper:
                    instrument = 'BANK_NIFTY'
                    lot_size = 30  # Dec 2025 onwards
                elif 'SENSEX' in symbol_upper:
                    instrument = 'SENSEX'
                    lot_size = 10
                elif 'FINNIFTY' in symbol_upper:
                    instrument = 'FINNIFTY'
                    lot_size = 25
                elif 'MIDCPNIFTY' in symbol_upper:
                    instrument = 'MIDCPNIFTY'
                    lot_size = 50
                elif 'NIFTY' in symbol_upper:  # Must come after BANKNIFTY/FINNIFTY/MIDCPNIFTY
                    instrument = 'NIFTY'
                    lot_size = 75
                else:
                    instrument = 'OTHER'
                    lot_size = 1

                lots = abs(quantity) // lot_size if lot_size > 0 else abs(quantity)
                is_matched = symbol_upper in pm_symbols
                tag_info = tagged_symbols.get(symbol_upper)

                positions_list.append({
                    'symbol': symbol,
                    'instrument': instrument,
                    'quantity': quantity,  # Positive = BUY, Negative = SELL
                    'lots': lots,
                    'average_price': pos_data.get('average_price', 0),
                    'ltp': pos_data.get('ltp', 0),  # Last traded price
                    'pnl': pos_data.get('pnl', 0),  # Unrealized P&L
                    'product': pos_data.get('product', 'NRML'),
                    'exchange': pos_data.get('exchange', ''),
                    'matched': is_matched,
                    'pm_position_id': None,
                    'tagged': tag_info is not None,
                    'tag_id': tag_info['tag_id'] if tag_info else None,
                    'strategy_id': tag_info['strategy_id'] if tag_info else None,
                    'strategy_name': tag_info['strategy_name'] if tag_info else None,
                })

            return jsonify({
                'success': True,
                'broker_positions': positions_list,
                'pm_position_count': len(pm_positions),
                'matched_count': sum(1 for p in positions_list if p['matched']),
                'unmatched_count': sum(1 for p in positions_list if not p['matched']),
                'tagged_count': sum(1 for p in positions_list if p.get('tagged'))
            }), 200

        except Exception as e:
            logger.error(f"Error fetching broker positions: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/broker/positions/raw', methods=['GET'])
    def get_broker_positions_raw():
        """
        Get raw broker positions for debugging

        Returns the exact response from OpenAlgo without parsing
        """
        if not openalgo_client:
            return jsonify({'error': 'OpenAlgo client not initialized'}), 500

        try:
            raw_positions = openalgo_client.get_positions()
            return jsonify({
                'success': True,
                'raw_positions': raw_positions,
                'count': len(raw_positions) if raw_positions else 0,
                'sample_fields': list(raw_positions[0].keys()) if raw_positions and len(raw_positions) > 0 else []
            }), 200
        except Exception as e:
            logger.error(f"Error fetching raw broker positions: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/broker/positions/import', methods=['POST'])
    def import_broker_position():
        """
        Import an unmatched broker position into PM

        Request body:
        {
            "symbol": "GOLDM25DEC31FUT",
            "instrument": "GOLD_MINI",
            "quantity": 300,
            "average_price": 78500.00,
            "strategy_id": 1,
            "stop_loss": 77000.00  (optional)
        }
        """
        if not engine:
            return jsonify({'error': 'Portfolio manager not initialized'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required = ['symbol', 'instrument', 'quantity', 'average_price', 'strategy_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'error': f'Missing fields: {missing}'}), 400

        try:
            from datetime import datetime
            from core.models import Position

            instrument = data['instrument']
            quantity = abs(int(data['quantity']))
            entry_price = float(data['average_price'])
            strategy_id = int(data['strategy_id'])

            # Calculate lots based on instrument
            lot_sizes = {
                'GOLD_MINI': 100,
                'SILVER_MINI': 5,
                'COPPER': 2500,
                'BANK_NIFTY': 30,  # Dec 2025 onwards
                'NIFTY': 25,
                'SENSEX': 10,
                'FINNIFTY': 25,
                'MIDCPNIFTY': 50,
            }
            lot_size = lot_sizes.get(instrument, 1)

            lots = quantity // lot_size
            if lots == 0:
                return jsonify({'error': f'Quantity {quantity} is less than 1 lot ({lot_size})'}), 400

            # Generate position ID
            existing_positions = engine.portfolio.get_current_state().get_open_positions()
            existing_for_instrument = [p for p in existing_positions.values()
                                       if p.instrument == instrument]
            position_num = len(existing_for_instrument) + 1
            position_id = f"Long_{position_num}"

            # Use provided stop or calculate default (2% below entry)
            stop_loss = data.get('stop_loss', entry_price * 0.98)

            # Create position
            position = Position(
                position_id=position_id,
                instrument=instrument,
                status='open',
                entry_timestamp=datetime.now(),
                entry_price=entry_price,
                lots=lots,
                quantity=quantity,
                initial_stop=stop_loss,
                current_stop=stop_loss,
                highest_close=entry_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                atr=0.0,  # Will need to be updated
                risk_contribution=0.0,
                vol_contribution=0.0,
                is_base_position=(position_num == 1),
                rollover_status='none',
                rollover_pnl=0.0,
                rollover_count=0,
                strategy_id=strategy_id
            )

            # Add symbol-specific fields
            if instrument == 'GOLD_MINI':
                position.futures_symbol = data['symbol']
            elif instrument in ('COPPER', 'SILVER_MINI'):
                position.futures_symbol = data['symbol']
            elif instrument == 'BANK_NIFTY':
                # For synthetic futures, we'd need PE/CE symbols
                position.pe_symbol = data.get('pe_symbol')
                position.ce_symbol = data.get('ce_symbol')

            # Add to portfolio state
            pm_state = engine.portfolio.get_current_state()
            pm_state.positions[position_id] = position

            # Persist to database
            if db_manager:
                db_manager.save_position(position)

            logger.info(f"[IMPORT] Imported broker position: {position_id} - {instrument} {lots} lots @ {entry_price}")

            return jsonify({
                'success': True,
                'position_id': position_id,
                'instrument': instrument,
                'lots': lots,
                'entry_price': entry_price,
                'strategy_id': strategy_id
            }), 201

        except Exception as e:
            logger.error(f"Error importing broker position: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/broker/positions/bulk-import', methods=['POST'])
    def bulk_import_broker_positions():
        """
        Tag broker positions to a strategy for P&L tracking.
        Does NOT create PM positions - just associates broker positions with strategies.

        Request body:
        {
            "symbols": ["NIFTY09DEC2525650PE", "BANKNIFTY30DEC2558600PE"],
            "strategy_id": 3
        }
        """
        if not db_manager:
            return jsonify({'error': 'Database not initialized'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        symbols = data.get('symbols', [])
        strategy_id = data.get('strategy_id', 2)  # Default to "unknown" strategy

        if not symbols:
            return jsonify({'error': 'No symbols provided'}), 400

        try:
            from datetime import datetime
            from psycopg2.extras import RealDictCursor

            # Fetch current broker positions
            broker_positions = {}
            if broker_sync:
                bp = broker_sync._fetch_broker_positions()
                if bp:
                    broker_positions = bp

            tagged = []
            errors = []

            # Lot sizes for various instruments
            lot_sizes = {
                'GOLD_MINI': 100,
                'SILVER_MINI': 5,
                'COPPER': 2500,
                'BANK_NIFTY': 30,  # Dec 2025 onwards
                'NIFTY': 75,
                'SENSEX': 10,
                'FINNIFTY': 25,
                'MIDCPNIFTY': 50,
            }

            with db_manager.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                for symbol in symbols:
                    try:
                        # Find the position in broker data
                        if symbol not in broker_positions:
                            errors.append({'symbol': symbol, 'error': 'Not found in broker positions'})
                            continue

                        bp = broker_positions[symbol]
                        quantity = int(bp.get('quantity', 0))
                        entry_price = float(bp.get('average_price', 0))

                        if quantity == 0:
                            errors.append({'symbol': symbol, 'error': 'Zero quantity'})
                            continue

                        # Detect instrument from symbol
                        instrument = 'OTHER'
                        symbol_upper = symbol.upper()
                        if 'BANKNIFTY' in symbol_upper:
                            instrument = 'BANK_NIFTY'
                        elif 'FINNIFTY' in symbol_upper:
                            instrument = 'FINNIFTY'
                        elif 'MIDCPNIFTY' in symbol_upper:
                            instrument = 'MIDCPNIFTY'
                        elif 'NIFTY' in symbol_upper:
                            instrument = 'NIFTY'
                        elif 'SENSEX' in symbol_upper:
                            instrument = 'SENSEX'
                        elif 'SILVERM' in symbol_upper:
                            instrument = 'SILVER_MINI'
                        elif 'COPPER' in symbol_upper:
                            instrument = 'COPPER'
                        elif 'GOLD' in symbol_upper:
                            instrument = 'GOLD_MINI'

                        # Check if already tagged to this strategy
                        cursor.execute("""
                            SELECT id FROM broker_position_tags
                            WHERE symbol = %s AND strategy_id = %s AND is_active = TRUE
                        """, (symbol, strategy_id))

                        if cursor.fetchone():
                            errors.append({'symbol': symbol, 'error': 'Already tagged to this strategy'})
                            continue

                        # Insert tag record
                        cursor.execute("""
                            INSERT INTO broker_position_tags
                            (symbol, strategy_id, instrument, quantity, entry_price, is_active)
                            VALUES (%s, %s, %s, %s, %s, TRUE)
                            RETURNING id
                        """, (symbol, strategy_id, instrument, quantity, entry_price))

                        tag_id = cursor.fetchone()['id']

                        tagged.append({
                            'symbol': symbol,
                            'tag_id': tag_id,
                            'instrument': instrument,
                            'quantity': quantity,
                            'entry_price': entry_price
                        })

                        logger.info(f"[BULK-TAG] Tagged {symbol} to strategy {strategy_id} - {instrument}")

                    except Exception as e:
                        errors.append({'symbol': symbol, 'error': str(e)})
                        logger.error(f"[BULK-TAG] Failed to tag {symbol}: {e}")

                conn.commit()

            return jsonify({
                'success': True,
                'tagged_count': len(tagged),
                'failed_count': len(errors),
                'tagged': tagged,
                'errors': errors if errors else None
            }), 201

        except Exception as e:
            logger.error(f"Error in bulk tag: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/broker/positions/tagged', methods=['GET'])
    def get_tagged_broker_positions():
        """
        Get all broker positions tagged to strategies

        Query params:
        - strategy_id: Filter by strategy (optional)
        - active_only: Only show active tags (default: true)
        """
        if not db_manager:
            return jsonify({'error': 'Database not initialized'}), 500

        strategy_id = request.args.get('strategy_id', type=int)
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        try:
            from psycopg2.extras import RealDictCursor

            with db_manager.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                query = """
                    SELECT
                        bpt.id, bpt.symbol, bpt.strategy_id, bpt.instrument,
                        bpt.quantity, bpt.entry_price, bpt.tagged_at,
                        bpt.is_active, bpt.closed_at, bpt.exit_price, bpt.realized_pnl,
                        ts.strategy_name
                    FROM broker_position_tags bpt
                    JOIN trading_strategies ts ON ts.strategy_id = bpt.strategy_id
                    WHERE 1=1
                """
                params = []

                if strategy_id:
                    query += " AND bpt.strategy_id = %s"
                    params.append(strategy_id)

                if active_only:
                    query += " AND bpt.is_active = TRUE"

                query += " ORDER BY bpt.tagged_at DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Get current prices from broker
                broker_positions = {}
                if broker_sync:
                    bp = broker_sync._fetch_broker_positions()
                    if bp:
                        broker_positions = bp

                # Enrich with current prices
                positions = []
                for row in rows:
                    pos = dict(row)
                    pos['tagged_at'] = pos['tagged_at'].isoformat() if pos['tagged_at'] else None
                    pos['closed_at'] = pos['closed_at'].isoformat() if pos['closed_at'] else None

                    # Add current price and P&L if available
                    if pos['symbol'] in broker_positions and pos['is_active']:
                        bp = broker_positions[pos['symbol']]
                        pos['current_price'] = bp.get('ltp', 0)
                        pos['broker_pnl'] = bp.get('pnl', 0)
                        pos['broker_quantity'] = bp.get('quantity', 0)
                    else:
                        pos['current_price'] = None
                        pos['broker_pnl'] = None
                        pos['broker_quantity'] = None

                    positions.append(pos)

            return jsonify({
                'success': True,
                'positions': positions,
                'count': len(positions)
            }), 200

        except Exception as e:
            logger.error(f"Error fetching tagged positions: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/broker/positions/untag', methods=['POST'])
    def untag_broker_position():
        """
        Remove a broker position tag (close tracking)

        Request body:
        {
            "tag_id": 123,
            "exit_price": 100.50,  // Optional - for P&L calculation
            "realized_pnl": 500.00  // Optional - override calculated P&L
        }
        """
        if not db_manager:
            return jsonify({'error': 'Database not initialized'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        tag_id = data.get('tag_id')
        if not tag_id:
            return jsonify({'error': 'tag_id is required'}), 400

        exit_price = data.get('exit_price')
        realized_pnl = data.get('realized_pnl')

        try:
            from datetime import datetime
            from psycopg2.extras import RealDictCursor

            with db_manager.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Get current tag info
                cursor.execute("""
                    SELECT * FROM broker_position_tags WHERE id = %s
                """, (tag_id,))
                tag = cursor.fetchone()

                if not tag:
                    return jsonify({'error': 'Tag not found'}), 404

                if not tag['is_active']:
                    return jsonify({'error': 'Tag already closed'}), 400

                # Calculate P&L if not provided
                if realized_pnl is None and exit_price and tag['entry_price']:
                    qty = tag['quantity']
                    realized_pnl = (exit_price - tag['entry_price']) * qty

                # Update tag to closed
                cursor.execute("""
                    UPDATE broker_position_tags
                    SET is_active = FALSE, closed_at = %s, exit_price = %s, realized_pnl = %s
                    WHERE id = %s
                """, (datetime.now(), exit_price, realized_pnl, tag_id))

                # Update strategy cumulative P&L if we have realized P&L
                if realized_pnl:
                    cursor.execute("""
                        UPDATE trading_strategies
                        SET cumulative_realized_pnl = cumulative_realized_pnl + %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE strategy_id = %s
                    """, (realized_pnl, tag['strategy_id']))

                conn.commit()

                logger.info(f"[UNTAG] Closed tag {tag_id} for {tag['symbol']} - P&L: {realized_pnl}")

            return jsonify({
                'success': True,
                'tag_id': tag_id,
                'symbol': tag['symbol'],
                'realized_pnl': realized_pnl
            }), 200

        except Exception as e:
            logger.error(f"Error untagging position: {e}")
            return jsonify({'error': str(e)}), 500

    # =========================================================================
    # ADMIN: Position P&L Update (for testing/manual adjustment)
    # =========================================================================

    @app.route('/admin/position/update-pnl', methods=['POST'])
    def admin_update_position_pnl():
        """
        Update unrealized P&L for a position (admin/testing use)

        Request body:
        {
            "position_id": "SILVER_MINI_Long_1",
            "unrealized_pnl": 81100.0
        }
        """
        if not engine:
            return jsonify({'error': 'Trading engine not initialized'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        position_id = data.get('position_id')
        unrealized_pnl = data.get('unrealized_pnl')

        if not position_id:
            return jsonify({'error': 'position_id is required'}), 400
        if unrealized_pnl is None:
            return jsonify({'error': 'unrealized_pnl is required'}), 400

        try:
            # Get position from portfolio
            position = engine.portfolio.positions.get(position_id)
            if not position:
                return jsonify({'error': f'Position not found: {position_id}'}), 404

            old_pnl = position.unrealized_pnl
            position.unrealized_pnl = float(unrealized_pnl)

            logger.info(f"[ADMIN] Updated P&L for {position_id}: {old_pnl} -> {unrealized_pnl}")

            return jsonify({
                'success': True,
                'position_id': position_id,
                'old_pnl': old_pnl,
                'new_pnl': position.unrealized_pnl
            }), 200

        except Exception as e:
            logger.error(f"Error updating position P&L: {e}")
            return jsonify({'error': str(e)}), 500

    logger.info("=" * 60)
    logger.info("Endpoints:")
    logger.info("  POST /webhook          - TradingView webhook receiver")
    logger.info("  GET  /webhook/stats    - Webhook processing statistics")
    logger.info("  GET  /status           - Portfolio status")
    logger.info("  GET  /positions        - Open positions")
    logger.info("  GET  /signals          - Signal history (from database)")
    logger.info("  GET  /trades           - Trade history (from database)")
    logger.info("  GET  /config           - Configuration (read-only)")
    logger.info("  GET  /rollover/status  - Rollover status")
    logger.info("  GET  /rollover/scan    - Scan for rollover candidates")
    logger.info("  POST /rollover/execute - Execute rollover (dry_run=true for simulation)")
    logger.info("  GET  /eod/status       - EOD pre-close execution status")
    logger.info("  GET  /health           - Health check")
    logger.info("  GET  /voice/status     - Voice announcer status & pending errors")
    logger.info("  POST /voice/acknowledge- Acknowledge errors (stop repeat)")
    logger.info("  POST /voice/test       - Test voice announcement")
    logger.info("  --- SAFETY & SYNC ---")
    logger.info("  POST /emergency/stop   - KILL SWITCH: Pause trading")
    logger.info("  POST /emergency/resume - Resume trading")
    logger.info("  POST /emergency/close-all - Close all positions (dry_run=true)")
    logger.info("  GET  /safety/status    - Safety manager status")
    logger.info("  POST /sync/broker      - Manual broker sync")
    logger.info("  GET  /sync/status      - Broker sync status")
    logger.info("  --- HOLIDAY CALENDAR ---")
    logger.info("  GET  /holidays/status  - Today's holiday status")
    logger.info("  GET  /holidays/{exchange} - List holidays for NSE/MCX")
    logger.info("  POST /holidays/{exchange} - Add holiday")
    logger.info("  DELETE /holidays/{exchange}/{date} - Remove holiday")
    logger.info("  POST /holidays/upload  - Upload holidays from CSV")
    logger.info("  --- STRATEGY MANAGEMENT ---")
    logger.info("  GET  /strategies       - List all strategies")
    logger.info("  POST /strategies       - Create new strategy")
    logger.info("  GET  /strategies/{id}  - Get strategy details")
    logger.info("  PUT  /strategies/{id}  - Update strategy")
    logger.info("  DELETE /strategies/{id} - Delete strategy")
    logger.info("  GET  /strategies/{id}/positions - Positions for strategy")
    logger.info("  GET  /strategies/{id}/pnl - P&L summary for strategy")
    logger.info("  GET  /strategies/{id}/trades - Trade history for strategy")
    logger.info("  PUT  /positions/{id}/strategy - Reassign position to strategy")
    logger.info("=" * 60)
    logger.info(f"Starting webhook server on port {args.port}...")

    try:
        # Enable threading for concurrent request handling
        # This ensures webhook signals aren't blocked by dashboard polling
        app.run(host='0.0.0.0', port=args.port, threaded=True)
    finally:
        # Graceful shutdown
        logger.info("Shutting down...")

        if broker_sync:
            broker_sync.stop_background_sync()
            logger.info("Broker sync stopped")

        if telegram_notifier:
            telegram_notifier.shutdown()
            logger.info("Telegram notifier stopped")

        if rollover_scheduler:
            rollover_scheduler.stop()
            logger.info("Rollover scheduler stopped")

        if eod_scheduler:
            eod_scheduler.shutdown()
            logger.info("EOD scheduler stopped")

    return 0

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Tom Basso Multi-Instrument Portfolio Manager'
    )

    subparsers = parser.add_subparsers(dest='mode', help='Operating mode')

    # Backtest mode
    backtest_parser = subparsers.add_parser('backtest', help='Run backtest')
    backtest_parser.add_argument('--gold', type=str, help='Gold signals CSV path')
    backtest_parser.add_argument('--bn', type=str, help='Bank Nifty signals CSV path')
    backtest_parser.add_argument('--capital', type=float, default=5000000.0,
                                help='Initial capital (default: 50L)')

    # Live mode
    live_parser = subparsers.add_parser('live', help='Run live trading')
    live_parser.add_argument('--broker', type=str, default='zerodha',
                            choices=['zerodha', 'dhan'],
                            help='Broker name (default: zerodha)')
    live_parser.add_argument('--api-key', type=str, required=True,
                            help='OpenAlgo API key')
    live_parser.add_argument('--capital', type=float, default=None,
                            help='Initial capital (loads from database if not specified)')
    live_parser.add_argument('--disable-rollover', action='store_true',
                            help='Disable automatic rollover scheduler')
    live_parser.add_argument('--db-config', type=str,
                            help='Path to database config JSON file')
    live_parser.add_argument('--db-env', type=str, default='local',
                            choices=['local', 'production'],
                            help='Database environment (local or production)')
    live_parser.add_argument('--redis-config', type=str,
                            help='Path to Redis config JSON file for HA/leader election')
    live_parser.add_argument('--port', type=int, default=5002,
                            help='Webhook server port (default: 5002)')
    live_parser.add_argument('--test-mode', action='store_true',
                            help='Test mode: place 1 lot only, log actual calculated lots. Positions marked as test.')
    live_parser.add_argument('--silent', action='store_true',
                            help='Silent mode: disable voice announcements, use visual alerts only. Critical errors show dialog, non-critical show auto-dismiss notifications.')

    args = parser.parse_args()

    if args.mode == 'backtest':
        return run_backtest(args)
    elif args.mode == 'live':
        return run_live(args)
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    sys.exit(main())
