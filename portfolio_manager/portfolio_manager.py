#!/usr/bin/env python3
"""
Tom Basso Portfolio Manager - Main Entry Point

Unified system for backtesting and live trading

Usage:
    # Backtest mode
    python portfolio_manager.py backtest --gold signals/gold.csv --bn signals/bn.csv

    # Live trading mode
    python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
"""
import sys
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
    from core.webhook_parser import DuplicateDetector, validate_json_structure, parse_webhook_signal
    from core.models import Signal

    logger.info("=" * 60)
    logger.info("TOM BASSO PORTFOLIO - LIVE TRADING")
    logger.info("=" * 60)
    logger.info(f"Broker: {args.broker}")
    logger.info(f"Mode: LIVE")
    logger.info(f"Auto Rollover: {'Enabled' if not args.disable_rollover else 'Disabled'}")
    logger.info("=" * 60)

    # Initialize OpenAlgo client (mock for now, replace with real client)
    class MockOpenAlgoClient:
        def get_funds(self):
            return {'availablecash': args.capital}

        def get_quote(self, symbol):
            # Mock quote for testing
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

    # Initialize live engine
    engine = LiveTradingEngine(
        initial_capital=args.capital,
        openalgo_client=openalgo
    )

    # Initialize duplicate detector for webhook signals
    duplicate_detector = DuplicateDetector(window_seconds=60)
    logger.info("Duplicate detector initialized (60s window)")

    # Initialize rollover scheduler
    rollover_scheduler = None
    if not args.disable_rollover:
        rollover_scheduler = RolloverScheduler(
            engine=engine,
            check_interval_hours=1.0  # Check every hour
        )
        rollover_scheduler.start()

    # Setup Flask webhook receiver
    app = Flask(__name__)
    
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
        try:
            data = request.json
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
            
            # Step 5: Process signal
            result = engine.process_signal(signal)
            
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
                # Error in processing
                logger.error(f"[{request_id}] Signal processing error: {result.get('reason', 'Unknown error')}")
                return jsonify({
                    'status': 'error',
                    'error_type': 'processing_error',
                    'message': result.get('reason', 'Unknown processing error'),
                    'request_id': request_id,
                    'details': result
                }), 500
                
        except Exception as e:
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

    @app.route('/status', methods=['GET'])
    def status():
        """Get current portfolio status"""
        state = engine.portfolio.get_current_state()
        return jsonify({
            'equity': state.equity,
            'positions': len(state.get_open_positions()),
            'risk_pct': state.total_risk_percent,
            'stats': engine.stats
        }), 200

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

    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'rollover_scheduler': 'running' if rollover_scheduler else 'disabled'
        }), 200

    logger.info("=" * 60)
    logger.info("Endpoints:")
    logger.info("  POST /webhook          - TradingView webhook receiver")
    logger.info("  GET  /webhook/stats    - Webhook processing statistics")
    logger.info("  GET  /status           - Portfolio status")
    logger.info("  GET  /positions        - Open positions")
    logger.info("  GET  /rollover/status  - Rollover status")
    logger.info("  GET  /rollover/scan    - Scan for rollover candidates")
    logger.info("  POST /rollover/execute - Execute rollover (dry_run=true for simulation)")
    logger.info("  GET  /health           - Health check")
    logger.info("=" * 60)
    logger.info("Starting webhook server on port 5002...")

    try:
        app.run(host='0.0.0.0', port=5002)
    finally:
        if rollover_scheduler:
            rollover_scheduler.stop()

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
    live_parser.add_argument('--broker', type=str, required=True,
                            choices=['zerodha', 'dhan'],
                            help='Broker name')
    live_parser.add_argument('--api-key', type=str, required=True,
                            help='OpenAlgo API key')
    live_parser.add_argument('--capital', type=float, default=5000000.0,
                            help='Initial capital')
    live_parser.add_argument('--disable-rollover', action='store_true',
                            help='Disable automatic rollover scheduler')
    
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

