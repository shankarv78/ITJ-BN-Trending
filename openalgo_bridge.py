#!/usr/bin/env python3
"""
OpenAlgo Trading Bridge - Main Application
"""
import logging
from flask import Flask, request, jsonify

# Import bridge modules
from bridge_config import load_config
from bridge_state import StateManager
from bridge_utils import is_market_hours, validate_signal
from openalgo_client import OpenAlgoClient
from synthetic_executor import SyntheticFuturesExecutor
from position_sizer import PositionSizer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('openalgo_bridge.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration
CONFIG = load_config()

# Initialize Flask app
app = Flask(__name__)

# Initialize components
state = StateManager(duplicate_window=CONFIG.get('duplicate_window_seconds', 60))
openalgo = OpenAlgoClient(CONFIG['openalgo_url'], CONFIG['openalgo_api_key'])
executor = SyntheticFuturesExecutor(openalgo, CONFIG)
sizer = PositionSizer(openalgo, CONFIG)

# ============================================================================
# SIGNAL HANDLERS
# ============================================================================

def handle_base_entry(signal: dict) -> dict:
    """Handle BASE_ENTRY signal"""
    logger.info(f"📊 Processing BASE_ENTRY: {signal.get('position')}")
    
    # Check if we already have this position
    position_id = signal.get('position')
    existing = state.get_position(position_id)
    if existing and existing.get('status') == 'open':
        logger.warning(f"Position {position_id} already exists, skipping entry")
        return {'status': 'skipped', 'reason': 'position already open'}
    
    # Calculate position size
    lots = sizer.calculate_base_entry_size(signal)
    
    if lots == 0:
        logger.warning("Position size calculated as 0, skipping entry")
        return {'status': 'skipped', 'reason': 'insufficient capital or risk too high'}
    
    # Execute synthetic long
    execution_result = executor.execute_synthetic_long(signal, lots)
    
    if execution_result['status'] == 'success':
        # Save position state
        position_data = {
            'status': 'open',
            'signal_type': 'BASE_ENTRY',
            'entry_timestamp': signal.get('timestamp'),
            'signal_price': signal.get('price'),
            'stop_price': signal.get('stop'),
            **execution_result
        }
        state.add_position(position_id, position_data)
        logger.info(f"✓ Position {position_id} opened: {lots} lots at strike {execution_result['strike']}")
    else:
        logger.error(f"✗ Failed to open {position_id}: {execution_result.get('error')}")
    
    return execution_result

def handle_pyramid(signal: dict) -> dict:
    """Handle PYRAMID signal"""
    logger.info(f"📈 Processing PYRAMID: {signal.get('position')}")
    
    # Check if base position exists
    base_position = state.get_position('Long_1')
    if not base_position or base_position.get('status') != 'open':
        logger.error("Base position (Long_1) not found or not open, cannot pyramid")
        return {'status': 'error', 'reason': 'no base position'}
    
    # Check if this pyramid already exists
    position_id = signal.get('position')
    existing = state.get_position(position_id)
    if existing and existing.get('status') == 'open':
        logger.warning(f"Pyramid {position_id} already exists, skipping")
        return {'status': 'skipped', 'reason': 'pyramid already open'}
    
    # Get base position size for validation
    base_lots = base_position.get('quantity_lots', 0)
    
    # Calculate pyramid size
    lots = sizer.calculate_pyramid_size(signal, base_lots)
    
    if lots == 0:
        logger.warning("Pyramid size calculated as 0, skipping")
        return {'status': 'skipped', 'reason': 'insufficient capital for pyramid'}
    
    # Execute synthetic long
    execution_result = executor.execute_synthetic_long(signal, lots)
    
    if execution_result['status'] == 'success':
        # Save position state
        position_data = {
            'status': 'open',
            'signal_type': 'PYRAMID',
            'entry_timestamp': signal.get('timestamp'),
            'signal_price': signal.get('price'),
            'stop_price': signal.get('stop'),
            **execution_result
        }
        state.add_position(position_id, position_data)
        logger.info(f"✓ Pyramid {position_id} opened: {lots} lots at strike {execution_result['strike']}")
    else:
        logger.error(f"✗ Failed to open pyramid {position_id}: {execution_result.get('error')}")
    
    return execution_result

def handle_exit(signal: dict) -> dict:
    """Handle EXIT signal"""
    position_id = signal.get('position')
    logger.info(f"📉 Processing EXIT: {position_id}")
    
    # Get position from state
    position = state.get_position(position_id)
    
    if not position:
        logger.error(f"Position {position_id} not found in state")
        return {'status': 'error', 'reason': 'position not found'}
    
    if position.get('status') != 'open':
        logger.warning(f"Position {position_id} not open, status: {position.get('status')}")
        return {'status': 'skipped', 'reason': f"position status: {position.get('status')}"}
    
    # Close synthetic long
    exit_result = executor.close_synthetic_long(position)
    
    if exit_result['status'] == 'success':
        # Update position status
        position['status'] = 'closed'
        position['exit_timestamp'] = signal.get('timestamp')
        position['exit_price'] = signal.get('price')
        position['exit_result'] = exit_result
        state.add_position(position_id, position)
        
        pnl = exit_result.get('pnl', 0)
        logger.info(f"✓ Position {position_id} closed: P&L = ₹{pnl:,.2f}")
    else:
        logger.error(f"✗ Failed to close {position_id}: {exit_result.get('error')}")
    
    return exit_result

# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Receive TradingView webhook alerts
    
    Expected JSON:
    {
        "type": "BASE_ENTRY" | "PYRAMID" | "EXIT",
        "position": "Long_1" to "Long_6",
        "price": 52000,
        "stop": 51650,
        "suggested_lots": 12,
        "atr": 350,
        "er": 0.82,
        "supertrend": 51650,
        "roc": 2.5,
        "timestamp": "2025-11-25T10:30:00Z"
    }
    """
    try:
        signal = request.json
        logger.info(f"🔔 Webhook received: {signal.get('type')} {signal.get('position')}")
        
        # Validate payload
        if not signal:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        is_valid, error_msg = validate_signal(signal)
        if not is_valid:
            logger.error(f"Invalid signal: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400
        
        # Check market hours
        if not is_market_hours(CONFIG['market_start_hour'], CONFIG['market_start_minute'],
                                CONFIG['market_end_hour'], CONFIG['market_end_minute']):
            logger.warning("Signal received outside market hours, ignoring")
            return jsonify({"status": "ignored", "reason": "outside market hours"}), 200
        
        # Check for duplicate
        if state.is_duplicate_signal(signal):
            return jsonify({"status": "ignored", "reason": "duplicate signal"}), 200
        
        # Route to appropriate handler
        signal_type = signal['type']
        
        if signal_type == 'BASE_ENTRY':
            result = handle_base_entry(signal)
        elif signal_type == 'PYRAMID':
            result = handle_pyramid(signal)
        elif signal_type == 'EXIT':
            result = handle_exit(signal)
        else:
            return jsonify({"status": "error", "message": f"Unknown signal type: {signal_type}"}), 400
        
        return jsonify({"status": "processed", "result": result}), 200
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    positions = state.get_all_positions()
    margin_status = sizer.get_margin_status()
    
    return jsonify({
        "status": "healthy",
        "open_positions": len(positions),
        "market_hours": is_market_hours(CONFIG['market_start_hour'], CONFIG['market_start_minute'],
                                         CONFIG['market_end_hour'], CONFIG['market_end_minute']),
        "margin": margin_status,
        "config": {
            "broker": CONFIG['broker'],
            "execution_mode": CONFIG['execution_mode'],
            "lot_size": CONFIG['bank_nifty_lot_size']
        }
    }), 200

@app.route('/positions', methods=['GET'])
def get_positions_endpoint():
    """Get current positions"""
    positions = state.get_all_positions()
    return jsonify({"status": "success", "positions": positions}), 200

@app.route('/reconcile', methods=['POST'])
def reconcile():
    """Reconcile bridge state with OpenAlgo positions"""
    try:
        bridge_positions = state.get_all_positions()
        openalgo_positions = openalgo.get_positions()
        
        logger.info(f"Reconciliation: Bridge={len(bridge_positions)}, OpenAlgo={len(openalgo_positions)}")
        
        return jsonify({
            "status": "success",
            "bridge_positions": len(bridge_positions),
            "openalgo_positions": len(openalgo_positions),
            "bridge_data": bridge_positions
        }), 200
    
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("OpenAlgo Trading Bridge Starting...")
    logger.info("=" * 60)
    logger.info(f"Broker: {CONFIG['broker']}")
    logger.info(f"OpenAlgo URL: {CONFIG['openalgo_url']}")
    logger.info(f"Execution Mode: {CONFIG['execution_mode']}")
    logger.info(f"Lot Size: {CONFIG['bank_nifty_lot_size']}")
    logger.info(f"Risk%: {CONFIG['risk_percent']}")
    logger.info(f"Market Hours: {CONFIG['market_start_hour']}:{CONFIG['market_start_minute']:02d} - {CONFIG['market_end_hour']}:{CONFIG['market_end_minute']:02d}")
    logger.info(f"Partial Fill Protection: {'✓' if CONFIG['enable_partial_fill_protection'] else '✗'}")
    logger.info(f"Expiry: {'Monthly' if CONFIG['use_monthly_expiry'] else 'Weekly'}")
    logger.info("=" * 60)
    logger.info("Webhook endpoint: http://localhost:5001/webhook")
    logger.info("Health check: http://localhost:5001/health")
    logger.info("Positions: http://localhost:5001/positions")
    logger.info("=" * 60)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5001, debug=False)


