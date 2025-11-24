import os
import json
import logging
import math
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests

# ==============================================================================
# CONFIGURATION
# ==============================================================================
STOXXO_API_URL = "http://localhost:3000/api/v1/orders"  # Default Stoxxo API port
LOG_FILE = "stoxxo_bridge.log"
BANK_NIFTY_LOT_SIZE = 15  # Current Lot Size
STRIKE_INTERVAL = 100     # Bank Nifty Strike Interval

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

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_atm_strike(price):
    """
    Calculate ATM strike for Bank Nifty (nearest 100).
    Example: 50040 -> 50000, 50060 -> 50100
    """
    return round(price / STRIKE_INTERVAL) * STRIKE_INTERVAL

def get_monthly_expiry(date_obj=None):
    """
    Get the last Wednesday of the current month.
    If today is past the last Wednesday, get next month's expiry.
    Returns string in Stoxxo format: 'YYMONDD' (e.g., '25NOV27')
    """
    if date_obj is None:
        date_obj = datetime.now()
    
    # Start with current month
    year = date_obj.year
    month = date_obj.month
    
    # Find last day of month
    if month == 12:
        next_month = date_obj.replace(year=year+1, month=1, day=1)
    else:
        next_month = date_obj.replace(month=month+1, day=1)
    
    last_day = next_month - timedelta(days=1)
    
    # Find last Wednesday
    # weekday(): Mon=0, Tue=1, Wed=2...
    offset = (last_day.weekday() - 2) % 7
    last_wednesday = last_day - timedelta(days=offset)
    
    # If today is past the expiry, move to next month
    if date_obj.date() > last_wednesday.date():
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
            
        # Recalculate for next month
        if month == 12:
            next_month = date_obj.replace(year=year+1, month=1, day=1)
        else:
            next_month = date_obj.replace(year=year, month=month+1, day=1)
        last_day = next_month - timedelta(days=1)
        offset = (last_day.weekday() - 2) % 7
        last_wednesday = last_day - timedelta(days=offset)
    
    # Format: YYMONDD (e.g., 25NOV27)
    yy = str(year)[-2:]
    mon = last_wednesday.strftime("%b").upper()
    dd = last_wednesday.strftime("%d")
    
    return f"{yy}{mon}{dd}"

def place_stoxxo_order(symbol, action, quantity, tag):
    """
    Send order to Stoxxo API.
    """
    payload = {
        "symbol": symbol,
        "action": action,  # BUY or SELL
        "quantity": quantity,
        "order_type": "MARKET",
        "product": "NRML",
        "tag": tag
    }
    
    logger.info(f"Sending to Stoxxo: {payload}")
    
    try:
        # Uncomment to actually send when API is ready
        # response = requests.post(STOXXO_API_URL, json=payload, timeout=5)
        # response.raise_for_status()
        # return response.json()
        
        # Simulation for now
        return {"status": "success", "order_id": f"SIM_{int(datetime.now().timestamp())}"}
        
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        return {"status": "error", "message": str(e)}

# ==============================================================================
# WEBHOOK ENDPOINT
# ==============================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info(f"Received Webhook: {json.dumps(data)}")
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
            
        signal_type = data.get("type")
        price = float(data.get("price", 0))
        lots = int(data.get("lots", 0))
        quantity = lots * BANK_NIFTY_LOT_SIZE
        position_id = data.get("position", "Long_1")
        
        if quantity <= 0:
            logger.warning("Quantity is 0, ignoring signal")
            return jsonify({"status": "ignored", "message": "Quantity 0"}), 200

        # 1. Calculate Parameters
        atm_strike = get_atm_strike(price)
        expiry = get_monthly_expiry()
        
        logger.info(f"Processing {signal_type} | Price: {price} | ATM: {atm_strike} | Expiry: {expiry} | Qty: {quantity}")
        
        # 2. Construct Symbols
        # Format: BANKNIFTY + EXPIRY + STRIKE + TYPE
        # Example: BANKNIFTY25NOV2750000PE
        pe_symbol = f"BANKNIFTY{expiry}{atm_strike}PE"
        ce_symbol = f"BANKNIFTY{expiry}{atm_strike}CE"
        
        orders = []
        
        # 3. Execute Logic based on Signal Type
        if signal_type in ["BASE_ENTRY", "PYRAMID"]:
            # SYNTHETIC LONG ENTRY = SELL PE + BUY CE
            logger.info("Executing SYNTHETIC LONG ENTRY")
            
            # Leg 1: SELL PE
            res_pe = place_stoxxo_order(pe_symbol, "SELL", quantity, f"{position_id}_ENTRY_PE")
            orders.append(res_pe)
            
            # Leg 2: BUY CE
            res_ce = place_stoxxo_order(ce_symbol, "BUY", quantity, f"{position_id}_ENTRY_CE")
            orders.append(res_ce)
            
        elif signal_type == "EXIT":
            # SYNTHETIC LONG EXIT = BUY PE + SELL CE (Reverse)
            # Note: For exits, we ideally need to know the ORIGINAL strike.
            # However, TradingView alert sends CURRENT price.
            # If we simply reverse at CURRENT ATM, we are effectively closing the exposure,
            # but we might leave "orphan" strikes if the market moved significantly.
            #
            # BETTER APPROACH FOR AUTOMATION:
            # Stoxxo usually tracks "Positions". We should ideally send a "Close Position" command.
            # But assuming simple order execution for now:
            # We will try to close the ATM strike derived from the ENTRY PRICE if provided,
            # otherwise we might need a database to track what strike was opened.
            
            entry_price = float(data.get("entry_price", 0))
            if entry_price > 0:
                # Use the strike we likely entered at
                strike_to_close = get_atm_strike(entry_price)
                logger.info(f"Closing position based on Entry Price: {entry_price} -> Strike: {strike_to_close}")
                
                pe_close_symbol = f"BANKNIFTY{expiry}{strike_to_close}PE"
                ce_close_symbol = f"BANKNIFTY{expiry}{strike_to_close}CE"
                
                # Leg 1: BUY PE (Cover Short)
                res_pe = place_stoxxo_order(pe_close_symbol, "BUY", quantity, f"{position_id}_EXIT_PE")
                orders.append(res_pe)
                
                # Leg 2: SELL CE (Close Long)
                res_ce = place_stoxxo_order(ce_close_symbol, "SELL", quantity, f"{position_id}_EXIT_CE")
                orders.append(res_ce)
            else:
                logger.warning("No entry price provided for exit, cannot determine strike to close!")
                return jsonify({"status": "error", "message": "Missing entry_price for exit"}), 400

        return jsonify({"status": "processed", "orders": orders}), 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("🚀 Stoxxo Bridge Started on Port 5000")
    print("👉 Send Webhooks to: http://localhost:5000/webhook")
    app.run(host='0.0.0.0', port=5000)
