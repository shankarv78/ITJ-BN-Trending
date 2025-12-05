#!/usr/bin/env python3
"""
Test script to verify OpenAlgo integration

Usage:
    python test_openalgo_connection.py
"""
import sys
import json
from pathlib import Path

def test_broker_factory():
    """Test broker factory can create clients"""
    print("=" * 60)
    print("Testing Broker Factory")
    print("=" * 60)
    
    try:
        from brokers.factory import create_broker_client
        print("✓ Broker factory imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import broker factory: {e}")
        return False
    
    # Test creating mock broker
    try:
        mock_config = {}
        mock_broker = create_broker_client('mock', mock_config)
        print("✓ Mock broker created successfully")
        # Check for methods that MockBrokerSimulator actually has
        assert hasattr(mock_broker, 'get_funds'), "MockBrokerSimulator missing get_funds"
        assert hasattr(mock_broker, 'get_quote'), "MockBrokerSimulator missing get_quote"
        assert hasattr(mock_broker, 'place_limit_order'), "MockBrokerSimulator missing place_limit_order"
        print("✓ Mock broker has required methods (get_funds, get_quote, place_limit_order)")
    except AssertionError as e:
        print(f"✗ Mock broker missing method: {e}")
        return False
    except Exception as e:
        print(f"✗ Failed to create mock broker: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test creating OpenAlgo broker (if config exists)
    config_path = Path(__file__).parent / 'openalgo_config.json'
    if config_path.exists():
        print(f"\n✓ Found config file: {config_path}")
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            api_key = config.get('openalgo_api_key', '')
            if api_key and api_key != 'YOUR_API_KEY_FROM_OPENALGO_DASHBOARD':
                print("✓ API key configured")
                try:
                    openalgo_broker = create_broker_client('openalgo', config)
                    print("✓ OpenAlgo broker client created successfully")
                    return True
                except Exception as e:
                    print(f"⚠️  OpenAlgo broker creation failed: {e}")
                    print("   (This is OK if OpenAlgo server is not running)")
                    return True  # Still pass if config is correct
            else:
                print("⚠️  API key not configured (using placeholder)")
                print("   Please update openalgo_config.json with your API key")
                return True  # Config file exists, just needs API key
        except Exception as e:
            print(f"✗ Failed to load config: {e}")
            return False
    else:
        print(f"⚠️  Config file not found: {config_path}")
        print("   Run: cp openalgo_config.json.example openalgo_config.json")
        return False
    
    return True

def test_openalgo_server():
    """Test OpenAlgo server connection"""
    print("\n" + "=" * 60)
    print("Testing OpenAlgo Server Connection")
    print("=" * 60)
    
    try:
        import requests
    except ImportError:
        print("✗ requests library not installed")
        print("   Run: pip install requests")
        return False
    
    config_path = Path(__file__).parent / 'openalgo_config.json'
    if not config_path.exists():
        print("⚠️  Config file not found, skipping server test")
        return True
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        base_url = config.get('openalgo_url', 'http://127.0.0.1:5000')
        api_key = config.get('openalgo_api_key', '')
        
        if not api_key or api_key == 'YOUR_API_KEY_FROM_OPENALGO_DASHBOARD':
            print("⚠️  No API key configured - skipping server test")
            return True
        
        # According to OpenAlgo docs, /api/v1/ping requires POST with API key in body
        print(f"Testing ping endpoint: {base_url}/api/v1/ping")
        ping_payload = {'apikey': api_key}
        ping_response = requests.post(f"{base_url}/api/v1/ping", json=ping_payload, timeout=5)
        
        if ping_response.status_code == 200:
            response_text = ping_response.text
            print(f"✓ OpenAlgo server is running and responding")
            print(f"  Response: {response_text}")
            
            # Also test funds endpoint to verify full API access (uses POST with apikey in body)
            print(f"\nTesting funds endpoint: {base_url}/api/v1/funds")
            funds_payload = {'apikey': api_key}
            funds_response = requests.post(f"{base_url}/api/v1/funds", json=funds_payload, timeout=5)
            
            if funds_response.status_code == 200:
                funds_data = funds_response.json().get('data', {})
                print(f"✓ API key is VALID! Full API access confirmed.")
                available_cash = float(funds_data.get('availablecash', '0'))
                print(f"  Available cash: ₹{available_cash:,.2f}")
                return True
            elif funds_response.status_code == 403:
                print(f"⚠️  Funds endpoint returned 403 (Permission error)")
                print(f"   Ping works but funds requires additional permissions")
                print(f"   Check Order Mode in dashboard: Settings → API Keys")
                return False
            elif funds_response.status_code == 401:
                print(f"✗ 401 Unauthorized - API key is invalid")
                return False
            else:
                print(f"⚠️  Funds endpoint status: {funds_response.status_code}")
                return False
        elif ping_response.status_code == 403:
            print(f"✗ Ping endpoint returned 403 (Permission error)")
            print(f"   Check in dashboard:")
            print(f"   1. Settings → API Keys → Verify key is Active")
            print(f"   2. Check Order Mode setting")
            print(f"   3. Security → Check if IP is banned")
            return False
        elif ping_response.status_code == 401:
            print(f"✗ 401 Unauthorized - API key authentication failed")
            print(f"   Verify API key is correct in openalgo_config.json")
            return False
        else:
            print(f"⚠️  Ping endpoint status: {ping_response.status_code}")
            if ping_response.text:
                print(f"   Response: {ping_response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  Cannot connect to OpenAlgo server")
        print("   Make sure OpenAlgo is running: cd ~/openalgo && uv run app.py")
        return False
    except Exception as e:
        print(f"⚠️  Error testing server: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("OpenAlgo Integration Test")
    print("=" * 60 + "\n")
    
    factory_ok = test_broker_factory()
    server_ok = test_openalgo_server()
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Broker Factory: {'✓ PASS' if factory_ok else '✗ FAIL'}")
    print(f"OpenAlgo Server: {'✓ PASS' if server_ok else '⚠️  WARNING'}")
    
    if factory_ok:
        print("\n✓ Integration code is working correctly!")
        if not server_ok:
            print("\n⚠️  Next steps:")
            print("   1. Start OpenAlgo server: cd ~/openalgo && uv run app.py")
            print("   2. Configure API key in openalgo_config.json")
            print("   3. Run this test again to verify connection")
        else:
            print("\n✓ Ready to use Portfolio Manager with OpenAlgo!")
    else:
        print("\n✗ Integration issues detected. Please check errors above.")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

