#!/usr/bin/env python3
"""
Sync Portfolio Manager state from broker positions via OpenAlgo

This script:
1. Queries OpenAlgo for current broker positions
2. Displays them for verification
3. Optionally injects them into PM via webhook

Usage:
  python sync_from_broker.py --show        # Just show positions
  python sync_from_broker.py --inject      # Inject into running PM
"""

import argparse
import json
import requests
from datetime import datetime, timezone

# Configuration
OPENALGO_URL = "http://127.0.0.1:5000"
PM_URL = "http://127.0.0.1:5002"
CONFIG_FILE = "openalgo_config.json"

def load_api_key():
    """Load API key from config"""
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
            return config.get('openalgo_api_key')
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def get_broker_positions(api_key):
    """Fetch positions from broker via OpenAlgo"""
    url = f"{OPENALGO_URL}/api/v1/positionbook"
    try:
        response = requests.post(url, json={"apikey": api_key}, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result.get('data', [])
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def map_position_to_signal(position):
    """Map broker position to PM signal format"""
    # Determine instrument from symbol
    symbol = position.get('tradingsymbol', position.get('symbol', ''))

    if 'GOLD' in symbol.upper():
        instrument = 'GOLD_MINI'
    elif 'BANKNIFTY' in symbol.upper():
        instrument = 'BANK_NIFTY'
    else:
        instrument = symbol

    # Get position details
    qty = abs(int(position.get('netqty', position.get('quantity', 0))))
    buy_price = float(position.get('averageprice', position.get('buyavgprice', 0)))

    if qty == 0:
        return None

    # Create signal
    signal = {
        "type": "BASE_ENTRY",
        "instrument": instrument,
        "position": "Long_1",
        "price": buy_price,
        "stop": buy_price * 0.995,  # Default 0.5% stop (will be overridden by PM)
        "lots": qty,
        "atr": 300,  # Default ATR
        "er": 0.85,  # Default ER
        "supertrend": buy_price * 0.995,
        "roc": 0.9,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    return signal

def inject_into_pm(signal):
    """Send signal to PM webhook"""
    url = f"{PM_URL}/webhook"
    try:
        response = requests.post(url, json=signal, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error injecting signal: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Sync positions from broker to PM')
    parser.add_argument('--show', action='store_true', help='Show broker positions')
    parser.add_argument('--inject', action='store_true', help='Inject positions into PM')
    args = parser.parse_args()

    if not args.show and not args.inject:
        args.show = True  # Default to show

    # Load API key
    api_key = load_api_key()
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("❌ Please configure API key in openalgo_config.json")
        return

    print("=" * 60)
    print("🔄 Syncing positions from broker via OpenAlgo")
    print("=" * 60)
    print()

    # Fetch positions
    positions = get_broker_positions(api_key)

    if not positions:
        print("📭 No open positions found in broker")
        return

    print(f"📊 Found {len(positions)} position(s):")
    print()

    for i, pos in enumerate(positions, 1):
        symbol = pos.get('tradingsymbol', pos.get('symbol', 'Unknown'))
        qty = pos.get('netqty', pos.get('quantity', 0))
        avg_price = pos.get('averageprice', pos.get('buyavgprice', 0))
        pnl = pos.get('pnl', pos.get('unrealised', 0))

        print(f"  {i}. {symbol}")
        print(f"     Qty: {qty}")
        print(f"     Avg Price: ₹{avg_price:,.2f}")
        print(f"     P&L: ₹{pnl:,.2f}")
        print()

    if args.show:
        print("-" * 60)
        print("Raw position data:")
        print(json.dumps(positions, indent=2))

    if args.inject:
        print()
        print("=" * 60)
        print("💉 Injecting positions into Portfolio Manager")
        print("=" * 60)

        # Check if PM is running
        try:
            health = requests.get(f"{PM_URL}/health", timeout=5)
            if health.status_code != 200:
                raise Exception("PM not healthy")
        except:
            print("❌ Portfolio Manager is not running!")
            print("   Start it first: python portfolio_manager.py live ...")
            return

        for pos in positions:
            signal = map_position_to_signal(pos)
            if signal:
                print(f"  → Injecting {signal['instrument']} {signal['lots']} lots @ ₹{signal['price']:,.2f}")
                result = inject_into_pm(signal)
                if result and result.get('status') == 'processed':
                    print(f"    ✓ Success: {result.get('result', {}).get('lots', '?')} lots registered")
                else:
                    print(f"    ✗ Failed: {result}")
            else:
                print(f"  → Skipping zero-qty position")

        print()
        print("✅ Sync complete!")

if __name__ == "__main__":
    main()
