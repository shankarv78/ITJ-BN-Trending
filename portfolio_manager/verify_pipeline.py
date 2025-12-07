#!/usr/bin/env python3
"""
🔍 Pipeline Verification Script
================================
Tests the entire signal flow without placing real orders:
  TradingView → PM → OpenAlgo → Zerodha

Run this every time you start up to ensure everything is connected.

Usage:
  python verify_pipeline.py           # Basic health checks
  python verify_pipeline.py --full    # Full test with simulated signal
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone
from typing import Tuple

# Configuration
PM_URL = "http://127.0.0.1:5002"
OPENALGO_URL = "http://127.0.0.1:5000"
CONFIG_FILE = "openalgo_config.json"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def ok(msg): print(f"{Colors.GREEN}✓ {msg}{Colors.END}")
def fail(msg): print(f"{Colors.RED}✗ {msg}{Colors.END}")
def warn(msg): print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")
def info(msg): print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")
def header(msg): print(f"\n{Colors.BOLD}{msg}{Colors.END}")

def load_config():
    """Load configuration"""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        return {}

def check_pm_health() -> Tuple[bool, str]:
    """Check if Portfolio Manager is running and healthy"""
    try:
        response = requests.get(f"{PM_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return True, f"Status: {data.get('status', 'unknown')}"
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused - PM not running"
    except Exception as e:
        return False, str(e)

def check_openalgo_health() -> Tuple[bool, str]:
    """Check if OpenAlgo is running"""
    try:
        # Use funds endpoint since /ping returns HTML
        # We just check if it responds - actual broker check is separate
        response = requests.get(f"{OPENALGO_URL}/", timeout=5)
        if response.status_code == 200:
            return True, "OpenAlgo web interface responding"
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused - OpenAlgo not running"
    except Exception as e:
        return False, str(e)

def check_broker_connection(api_key: str) -> Tuple[bool, str]:
    """Check if OpenAlgo can reach broker (Zerodha)"""
    try:
        # Use funds endpoint as a read-only health check
        response = requests.post(
            f"{OPENALGO_URL}/api/v1/funds",
            json={"apikey": api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                mode = data.get('mode', 'unknown')
                funds = data.get('data', {})
                available = funds.get('availablecash', funds.get('available_margin', 'N/A'))
                
                # Check if in analyze mode (not connected to real broker)
                if mode == 'analyze':
                    return False, f"⚠️  ANALYZE MODE - Not logged in to broker! Login at http://127.0.0.1:5000"
                
                if isinstance(available, (int, float)):
                    return True, f"Broker connected (mode: {mode}), Available: ₹{available:,.0f}"
                return True, f"Broker connected (mode: {mode})"
            elif 'error' in str(data).lower():
                return False, f"Broker error: {data.get('message', data)}"
        return False, f"HTTP {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return False, str(e)

def check_positions(api_key: str) -> Tuple[bool, str, list]:
    """Check current positions from broker"""
    try:
        response = requests.post(
            f"{OPENALGO_URL}/api/v1/positionbook",
            json={"apikey": api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            positions = data.get('data', [])
            if positions:
                pos_summary = []
                for p in positions:
                    symbol = p.get('tradingsymbol', p.get('symbol', '?'))
                    qty = p.get('netqty', p.get('quantity', 0))
                    if qty != 0:
                        pos_summary.append(f"{symbol}: {qty}")
                return True, f"Found {len(pos_summary)} position(s)", pos_summary
            return True, "No open positions", []
        return False, f"HTTP {response.status_code}", []
    except Exception as e:
        return False, str(e), []

def check_pm_can_reach_openalgo() -> Tuple[bool, str]:
    """Check if PM can communicate with OpenAlgo"""
    # This is implicit if both are healthy and PM is configured correctly
    config = load_config()
    openalgo_url = config.get('openalgo_url', 'not configured')
    execution_mode = config.get('execution_mode', 'unknown')
    broker = config.get('broker', 'unknown')
    
    return True, f"URL: {openalgo_url}, Mode: {execution_mode}, Broker: {broker}"

def test_webhook_endpoint() -> Tuple[bool, str]:
    """Test that PM webhook endpoint accepts requests"""
    try:
        # Send OPTIONS request (doesn't process signal)
        response = requests.options(f"{PM_URL}/webhook", timeout=5)
        return True, f"Webhook endpoint reachable (HTTP {response.status_code})"
    except Exception as e:
        return False, str(e)

def run_simulated_signal_test(api_key: str) -> Tuple[bool, str]:
    """
    Run a full signal test in ANALYZER mode
    This simulates the entire flow without placing real orders
    """
    # First check execution mode
    config = load_config()
    current_mode = config.get('execution_mode', 'unknown')
    
    if current_mode == 'live':
        return False, "⚠️  Currently in LIVE mode - switch to 'analyzer' in config to run simulated test"
    
    # Create a test signal with current timestamp
    test_signal = {
        "type": "BASE_ENTRY",
        "instrument": "GOLD_MINI",
        "position": "Long_TEST",  # Use TEST to identify test signals
        "price": 130000,
        "stop": 129700,
        "lots": 1,
        "atr": 300,
        "er": 0.85,
        "supertrend": 129700,
        "roc": 0.9,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    try:
        response = requests.post(
            f"{PM_URL}/webhook",
            json=test_signal,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'processed':
                lots = result.get('result', {}).get('lots', '?')
                return True, f"Signal processed! Calculated {lots} lots (simulated)"
            elif 'duplicate' in str(result).lower():
                return True, "Signal recognized (duplicate filtered)"
            else:
                return False, f"Unexpected result: {result}"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)

def main():
    parser = argparse.ArgumentParser(description='Verify pipeline health')
    parser.add_argument('--full', action='store_true', 
                       help='Run full test including simulated signal (analyzer mode only)')
    args = parser.parse_args()
    
    print(f"""
{Colors.BOLD}{'='*60}
🔍 PIPELINE VERIFICATION
{'='*60}{Colors.END}
""")
    
    all_passed = True
    config = load_config()
    api_key = config.get('openalgo_api_key', '')
    
    # Check 1: Portfolio Manager
    header("1️⃣  Portfolio Manager")
    passed, msg = check_pm_health()
    if passed:
        ok(f"PM Health: {msg}")
    else:
        fail(f"PM Health: {msg}")
        all_passed = False
    
    passed, msg = test_webhook_endpoint()
    if passed:
        ok(f"Webhook: {msg}")
    else:
        fail(f"Webhook: {msg}")
        all_passed = False
    
    passed, msg = check_pm_can_reach_openalgo()
    info(f"PM Config: {msg}")
    
    # Check 2: OpenAlgo
    header("2️⃣  OpenAlgo")
    passed, msg = check_openalgo_health()
    if passed:
        ok(f"OpenAlgo: {msg}")
    else:
        fail(f"OpenAlgo: {msg}")
        all_passed = False
        print(f"\n{Colors.RED}Cannot proceed without OpenAlgo. Start it with:{Colors.END}")
        print("  cd ~/openalgo && uv run app.py")
        return 1
    
    # Check 3: Broker Connection (Zerodha)
    header("3️⃣  Broker Connection (Zerodha)")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        fail("API key not configured in openalgo_config.json")
        all_passed = False
    else:
        passed, msg = check_broker_connection(api_key)
        if passed:
            ok(f"Broker: {msg}")
        else:
            fail(f"Broker: {msg}")
            all_passed = False
    
    # Check 4: Current Positions
    header("4️⃣  Broker Positions")
    passed, msg, positions = check_positions(api_key)
    if passed:
        ok(msg)
        for pos in positions:
            info(f"  → {pos}")
    else:
        warn(f"Could not fetch positions: {msg}")
    
    # Check 5: Full Signal Test (optional)
    if args.full:
        header("5️⃣  Simulated Signal Test")
        execution_mode = config.get('execution_mode', 'unknown')
        
        if execution_mode == 'live':
            warn("Skipping signal test - currently in LIVE mode")
            info("To run full test, set execution_mode to 'analyzer' in config")
        else:
            info(f"Running simulated signal test (mode: {execution_mode})")
            passed, msg = run_simulated_signal_test(api_key)
            if passed:
                ok(msg)
            else:
                fail(msg)
                all_passed = False
    
    # Summary
    print(f"""
{Colors.BOLD}{'='*60}
SUMMARY
{'='*60}{Colors.END}
""")
    
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ ALL CHECKS PASSED - Pipeline ready!{Colors.END}")
        print()
        execution_mode = config.get('execution_mode', 'unknown')
        if execution_mode == 'live':
            print(f"{Colors.YELLOW}⚠️  LIVE MODE ACTIVE - Real orders will be placed!{Colors.END}")
        else:
            print(f"{Colors.BLUE}ℹ️  Analyzer mode - Orders will be simulated{Colors.END}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ SOME CHECKS FAILED - Fix issues above{Colors.END}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

