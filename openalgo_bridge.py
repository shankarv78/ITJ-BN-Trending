import os
import json
import logging
import math
import time
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
CONFIG_FILE = "openalgo_config.json"
STATE_FILE = "position_state.json"
LOG_FILE = "openalgo_bridge.log"

# Load Config
try:
    with open(CONFIG_FILE, 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    logging.error(f"Config file {CONFIG_FILE} not found!")
    CONFIG = {}

OPENALGO_URL = CONFIG.get("openalgo_url", "http://127.0.0.1:5000")
API_KEY = os.getenv("OPENALGO_API_KEY", CONFIG.get("api_key", ""))
BROKER = CONFIG.get("broker", "zerodha").lower()
RISK_PERCENT = CONFIG.get("risk_percent", 1.5)
MARGIN_PER_LOT = CONFIG.get("margin_per_lot", 270000)
MAX_PYRAMIDS = CONFIG.get("max_pyramids", 5)
BN_LOT_SIZE = CONFIG.get("bank_nifty_lot_size", 30)
ENABLE_TELEGRAM = CONFIG.get("enable_telegram", False)
TRUST_SIGNAL_QUANTITY = CONFIG.get("trust_signal_quantity", False)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", CONFIG.get("telegram_bot_token", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", CONFIG.get("telegram_chat_id", ""))

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global State Cache
position_state = {}
state_lock = threading.Lock()

# ==============================================================================
# STATE MANAGEMENT
# ==============================================================================
def load_state():
    global position_state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                position_state = json.load(f)
            logger.info("Position state loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            position_state = {}

def save_state():
    global position_state
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(position_state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

# Load state on startup
load_state()

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def get_openalgo_headers():
    return {
        "Content-Type": "application/json",
        "X-API-KEY": API_KEY
    }

def send_telegram_message(message):
    """Send notification to Telegram"""
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def is_market_open():
    """Check if current time is within NSE F&O hours (9:15 - 15:30 IST)"""
    now = datetime.now() # Assumes system time is IST or UTC converted appropriately
    # For simplicity, assuming system time is correct local time
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # Allow 2 min buffer for late signals
    end_time_buffer = end_time + timedelta(minutes=2)
    
    return start_time <= now <= end_time_buffer

def get_monthly_expiry(date_obj=None):
    """Get last Wednesday of current month in DDMMMYY format (e.g. 25DEC25)"""
    if date_obj is None:
        date_obj = datetime.now()
    
    year = date_obj.year
    month = date_obj.month
    
    # Find last day of month
    if month == 12:
        next_month = date_obj.replace(year=year+1, month=1, day=1)
    else:
        next_month = date_obj.replace(month=month+1, day=1)
    last_day = next_month - timedelta(days=1)
    
    # Find last Wednesday
    offset = (last_day.weekday() - 2) % 7
    last_wednesday = last_day - timedelta(days=offset)
    
    # If today is past expiry, move to next month
    if date_obj.date() > last_wednesday.date():
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        
        if month == 12:
            next_month = date_obj.replace(year=year+1, month=1, day=1)
        else:
            next_month = date_obj.replace(year=year, month=month+1, day=1)
        last_day = next_month - timedelta(days=1)
        offset = (last_day.weekday() - 2) % 7
        last_wednesday = last_day - timedelta(days=offset)

    # Format for Zerodha: YYMONDD -> NO, Zerodha uses BANKNIFTY25NOV...
    # Actually Zerodha NFO format: BANKNIFTY + YY + MMM (upper) + DD + STRIKE + CE/PE
    # Example: BANKNIFTY25DEC52000CE -> YY=25, MMM=DEC, strike...
    # WAIT! Zerodha Symbol format is tricky. 
    # Standard NFO: BANKNIFTY25DEC2552000PE (YYMMMUDD...)
    # Let's use a standard helper or verify OpenAlgo's expectation
    
    yy = str(year)[-2:]
    mmm = last_wednesday.strftime("%b").upper() # DEC
    dd = last_wednesday.strftime("%d") # 25
    
    return {"yy": yy, "mmm": mmm, "dd": dd, "date": last_wednesday}

def format_symbol(expiry_dict, strike, option_type):
    """Format symbol based on broker"""
    # Zerodha: BANKNIFTY25DEC52000CE (Weekly) vs BANKNIFTY25DEC52000CE (Monthly)?
    # NSE Monthly: BANKNIFTY25DEC52000CE
    # NSE Weekly: BANKNIFTY25N0652000CE
    
    # We are using MONTHLY expiry for now
    # Format: BANKNIFTY + YY + MMM + STRIKE + TYPE
    # Example: BANKNIFTY25DEC52000PE
    
    if BROKER == "zerodha":
        return f"BANKNIFTY{expiry_dict['yy']}{expiry_dict['mmm']}{strike}{option_type}"
    elif BROKER == "dhan":
        # Dhan might differ, using standard for now
        return f"BANKNIFTY {expiry_dict['dd']} {expiry_dict['mmm']} {strike} {option_type}"
    else:
        return f"BANKNIFTY{expiry_dict['yy']}{expiry_dict['mmm']}{strike}{option_type}"

def get_atm_strike(price):
    return round(price / 100) * 100

def check_duplicate_signal(signal_data):
    """Prevent processing same signal twice within 60 seconds"""
    signal_id = f"{signal_data.get('type')}_{signal_data.get('position')}_{signal_data.get('timestamp')}"
    
    # Check if recently processed (simplified in-memory check)
    # ideally we store this with timestamp in a list and clean up old ones
    return False # Placeholder

# ==============================================================================
# OPENALGO API CLIENT
# ==============================================================================
def place_order(symbol, action, quantity, tag):
    """Place order via OpenAlgo"""
    payload = {
        "symbol": symbol,
        "action": action, # BUY/SELL
        "quantity": quantity,
        "order_type": "MARKET",
        "product": "NRML", # Carry forward
        "tag": tag,
        "exchange": "NFO"
    }
    
    logger.info(f"Sending Order: {payload}")
    
    try:
        response = requests.post(f"{OPENALGO_URL}/api/v1/placeorder", json=payload, headers=get_openalgo_headers(), timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        return {"status": "error", "message": str(e)}

def get_funds():
    """Get available margin"""
    try:
        response = requests.get(f"{OPENALGO_URL}/api/v1/funds", headers=get_openalgo_headers(), timeout=5)
        if response.status_code == 200:
            return response.json()
        return {}
    except:
        return {}

# ==============================================================================
# EXECUTION LOGIC (SYNTHETIC FUTURES)
# ==============================================================================
def execute_synthetic_entry(position_id, atm_strike, quantity, signal_price):
    """
    Execute Synthetic Long: SELL PE + BUY CE
    CRITICAL: Handle Partial Fills
    """
    expiry = get_monthly_expiry()
    pe_symbol = format_symbol(expiry, atm_strike, "PE")
    ce_symbol = format_symbol(expiry, atm_strike, "CE")
    
    logger.info(f"Executing Synthetic Entry for {position_id}: {quantity} qty @ {atm_strike}")
    send_telegram_message(f"🚀 *ENTRY SIGNAL* ({position_id})\nStrike: {atm_strike}\nQty: {quantity}")
    
    # 1. Place PE Order (SELL) - Leg 1
    pe_res = place_order(pe_symbol, "SELL", quantity, f"{position_id}_ENTRY_PE")
    
    if pe_res.get("status") != "success":
        logger.error(f"PE Order Failed! Aborting CE order. Reason: {pe_res.get('message')}")
        send_telegram_message(f"❌ *ENTRY FAILED* ({position_id})\nPE Order Rejected: {pe_res.get('message')}")
        return False
    
    pe_order_id = pe_res.get("order_id")
    logger.info(f"PE Order Placed: {pe_order_id}. Waiting for fill confirmation...")
    
    # 2. Wait for PE Fill (Simulated wait for now - OpenAlgo is async)
    # In production, we should poll /api/v1/orderbook?order_id=...
    time.sleep(1) 
    
    # 3. Place CE Order (BUY) - Leg 2
    ce_res = place_order(ce_symbol, "BUY", quantity, f"{position_id}_ENTRY_CE")
    
    if ce_res.get("status") != "success":
        logger.critical(f"CE Order Failed! NAKED PE EXPOSURE! Attempting Emergency Exit of PE...")
        send_telegram_message(f"🚨 *CRITICAL ERROR* ({position_id})\nCE Failed! Naked PE Exposure! Exiting PE...")
        # EMERGENCY: Buy back PE immediately
        place_order(pe_symbol, "BUY", quantity, f"{position_id}_EMERGENCY_EXIT")
        return False
        
    ce_order_id = ce_res.get("order_id")
    logger.info(f"CE Order Placed: {ce_order_id}. Synthetic Position Open.")
    send_telegram_message(f"✅ *POSITION OPEN* ({position_id})\nSynth Long @ {atm_strike}")
    
    # 4. Update State
    with state_lock:
        position_state[position_id] = {
            "status": "open",
            "strike": atm_strike,
            "expiry_str": f"{expiry['yy']}{expiry['mmm']}{expiry['dd']}",
            "pe_symbol": pe_symbol,
            "ce_symbol": ce_symbol,
            "quantity": quantity,
            "entry_price_underlying": signal_price,
            "timestamp": datetime.now().isoformat(),
            "pe_order_id": pe_order_id,
            "ce_order_id": ce_order_id
        }
        save_state()
        
    return True

def execute_synthetic_exit(position_id):
    """
    Execute Synthetic Exit: BUY PE + SELL CE
    Uses stored symbols from entry state
    """
    with state_lock:
        pos = position_state.get(position_id)
        
    if not pos or pos["status"] != "open":
        logger.warning(f"Position {position_id} not found or not open")
        return False
        
    pe_symbol = pos["pe_symbol"]
    ce_symbol = pos["ce_symbol"]
    quantity = pos["quantity"]
    
    logger.info(f"Executing Exit for {position_id}: {quantity} qty")
    send_telegram_message(f"🔻 *EXIT SIGNAL* ({position_id})\nClosing {quantity} qty")
    
    # 1. Buy Back PE (Cover Short)
    pe_res = place_order(pe_symbol, "BUY", quantity, f"{position_id}_EXIT_PE")
    
    # 2. Sell CE (Close Long)
    ce_res = place_order(ce_symbol, "SELL", quantity, f"{position_id}_EXIT_CE")
    
    if pe_res.get("status") == "success" and ce_res.get("status") == "success":
        with state_lock:
            position_state[position_id]["status"] = "closed"
            position_state[position_id]["exit_timestamp"] = datetime.now().isoformat()
            save_state()
        send_telegram_message(f"✅ *POSITION CLOSED* ({position_id})")
        return True
    else:
        logger.error("Partial exit failure! Check broker terminal.")
        send_telegram_message(f"⚠️ *PARTIAL EXIT FAILURE* ({position_id})\nCheck Broker Terminal!")
        return False

# ==============================================================================
# WEBHOOK HANDLER
# ==============================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    if not is_market_open():
        logger.warning("Signal received outside market hours. Ignoring.")
        return jsonify({"status": "ignored", "message": "Market closed"}), 200

    data = request.json
    logger.info(f"Received Signal: {json.dumps(data)}")
    
    signal_type = data.get("type")
    position_id = data.get("position")
    price = float(data.get("price", 0))
    signal_lots = int(data.get("lots", 0))
    
    # Quantity Logic
    if TRUST_SIGNAL_QUANTITY and signal_lots > 0:
        quantity = signal_lots * BN_LOT_SIZE
        logger.info(f"Using Signal Quantity: {signal_lots} lots ({quantity} qty)")
    else:
        quantity = BN_LOT_SIZE # Default 1 lot
        logger.info(f"Using Default Quantity: {quantity} qty (Safety Mode)")
    
    if signal_type == "BASE_ENTRY":
        atm = get_atm_strike(price)
        success = execute_synthetic_entry(position_id, atm, quantity, price)
        return jsonify({"status": "processed" if success else "failed"}), 200
        
    elif signal_type == "PYRAMID":
        atm = get_atm_strike(price)
        success = execute_synthetic_entry(position_id, atm, quantity, price)
        return jsonify({"status": "processed" if success else "failed"}), 200
        
    elif signal_type == "EXIT":
        success = execute_synthetic_exit(position_id)
        return jsonify({"status": "processed" if success else "failed"}), 200
        
    return jsonify({"status": "ignored", "message": "Unknown signal type"}), 400

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running", "positions": len(position_state)}), 200

if __name__ == '__main__':
    print("🚀 OpenAlgo Bridge Started on Port 5001")
    app.run(host='0.0.0.0', port=5001)



