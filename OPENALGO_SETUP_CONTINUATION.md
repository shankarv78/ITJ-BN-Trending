# OpenAlgo Setup Continuation Guide

## ✅ Completed Steps

1. ✓ Broker integration structure created (`portfolio_manager/brokers/`)
2. ✓ Broker factory implemented
3. ✓ OpenAlgo client integrated
4. ✓ `portfolio_manager.py` updated to use broker factory
5. ✓ `openalgo_config.json` created from example

## 🔧 Next Steps

### Step 1: Configure OpenAlgo Server

The OpenAlgo server is installed at `~/openalgo` but needs configuration:

```bash
cd ~/openalgo

# Create .env file from sample
cp .sample.env .env

# Edit .env with your broker credentials
nano .env
```

**Required Configuration in `~/openalgo/.env`:**

```env
# Enable which brokers you want to use (comma-separated list)
VALID_BROKERS=zerodha,dhan

# Broker Configuration (same variables for all brokers)
BROKER_API_KEY=your_broker_api_key_here
BROKER_API_SECRET=your_broker_api_secret_here

# For Zerodha: Use your Zerodha API key and secret
# For Dhan: Use your Dhan client ID as API key and access token as secret

# Market Data Configuration (Optional - only for XTS API supported brokers)
BROKER_API_KEY_MARKET=your_market_api_key_here
BROKER_API_SECRET_MARKET=your_market_api_secret_here

# Redirect URL for OAuth callbacks
# Generic format (OpenAlgo will substitute <broker> with actual broker name):
REDIRECT_URL=http://127.0.0.1:5000/<broker>/callback

# OR specify explicitly for your broker:
# For Dhan: REDIRECT_URL=http://127.0.0.1:5000/dhan/callback
# For Zerodha: REDIRECT_URL=http://127.0.0.1:5000/zerodha/callback

# OpenAlgo Security Keys (IMPORTANT: Generate new random values!)
# Generate APP_KEY: python -c "import secrets; print(secrets.token_hex(32))"
APP_KEY=your_generated_app_key_here

# Generate API_KEY_PEPPER: python -c "import secrets; print(secrets.token_hex(32))"
API_KEY_PEPPER=your_generated_pepper_here

# Database Configuration
DATABASE_URL=sqlite:///db/openalgo.db
LATENCY_DATABASE_URL=sqlite:///db/latency.db
LOGS_DATABASE_URL=sqlite:///db/logs.db
SANDBOX_DATABASE_URL=sqlite:///db/sandbox.db
```

**Important Notes:**
- **`VALID_BROKERS`** - List which brokers you want to enable (e.g., `zerodha,dhan`)
- **`BROKER_API_KEY` and `BROKER_API_SECRET`** - Generic variables for your broker's API credentials
  - For Zerodha: Use your Zerodha API key and secret
  - For Dhan: Use your Dhan client ID as API key and access token as secret
- **Broker Selection:** The actual broker you use is selected and authenticated through the OpenAlgo dashboard (see Step 3)
- Generate new random values for `APP_KEY` and `API_KEY_PEPPER` for security

**See `OPENALGO_BROKER_SELECTION_EXPLAINED.md` for detailed explanation of how broker selection works.**

### Step 2: Start OpenAlgo Server

```bash
cd ~/openalgo

# Install UV if not already installed
pip install uv

# Start OpenAlgo server
uv run app.py
```

**Expected Output:**
```
 * Running on http://localhost:5000
 * OpenAlgo Server Started
```

**Note:** After starting the server, you'll need to:
1. Open http://localhost:5000 in your browser
2. Login to the dashboard
3. Select your broker (Zerodha, Dhan, etc.) from the dashboard
4. Complete broker authentication through the dashboard

**Note:** Keep this terminal running. The server must be running for Portfolio Manager to connect.

### Step 3: Configure Broker in OpenAlgo Dashboard

1. Open browser: http://localhost:5000
2. Login to OpenAlgo dashboard (check OpenAlgo documentation for default credentials)
3. Navigate to **Broker Settings** or **Connect Broker**
4. Select your broker (Zerodha, Dhan, etc.)
5. Complete the OAuth authentication flow (you'll be redirected to your broker's login)
6. Verify broker connection is successful

### Step 4: Get OpenAlgo API Key

1. In the OpenAlgo dashboard, navigate to **Settings → API Keys**
2. Generate a new API key
3. **Copy and save the API key** - you'll need it for Portfolio Manager

### Step 5: Configure Portfolio Manager

Edit `portfolio_manager/openalgo_config.json`:

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager
nano openalgo_config.json
```

**Update with your API key:**

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "YOUR_ACTUAL_API_KEY_HERE",  ← REPLACE THIS
  "broker": "zerodha",
  "execution_mode": "analyzer",  ← START WITH THIS (no real trades)
  "risk_percent": 1.5,
  "margin_per_lot_banknifty": 270000,
  "margin_per_lot_goldmini": 105000,
  "max_pyramids": 5,
  "bank_nifty_lot_size": 30,
  "gold_mini_lot_size": 100,
  "market_start_hour": 9,
  "market_start_minute": 15,
  "market_end_hour": 15,
  "market_end_minute": 30,
  "enable_signal_validation": true,
  "enable_eod_execution": true
}
```

**Important:** 
- Set `execution_mode` to `"analyzer"` for testing (no real trades)
- Only change to `"auto"` after thorough testing

### Step 6: Test OpenAlgo Connection

```bash
# Terminal 1: Ensure OpenAlgo is running
cd ~/openalgo
uv run app.py

# Terminal 2: Test connection
curl http://localhost:5000/api/v1/health

# Expected response:
# {"status": "ok", "broker": "zerodha"}
```

### Step 7: Test Portfolio Manager Integration

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager

# Run integration tests
pytest tests/integration/test_openalgo_integration.py -v

# Expected: All tests should pass
```

### Step 8: Start Portfolio Manager (Analyzer Mode)

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager

# Option 1: Use the quick start script
./start_portfolio_manager.sh

# Option 2: Manual start
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_OPENALGO_API_KEY \
  --capital 5000000 \
  --port 5002
```

**Expected Output:**
```
============================================================
TOM BASSO PORTFOLIO - LIVE TRADING
============================================================
Broker: zerodha
Mode: LIVE
Creating broker client: type=openalgo, broker=zerodha
✓ Broker client initialized successfully
OpenAlgo client initialized: http://localhost:5000
Webhook endpoint: http://localhost:5002/webhook
```

### Step 9: Send Test Signal

In another terminal:

```bash
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000,
    "stop": 51650,
    "suggested_lots": 5,
    "timestamp": "2025-12-02T10:30:00Z"
  }'
```

**Expected:** Signal processed, position size calculated, logged (not executed in analyzer mode)

---

## 🔍 Troubleshooting

### Issue: OpenAlgo server won't start

**Check:**
```bash
# Verify UV installation
uv --version

# Check Python version (needs 3.8+)
python --version

# Check .env file exists
ls -la ~/openalgo/.env

# Check for errors in OpenAlgo logs
```

### Issue: Portfolio Manager can't connect to OpenAlgo

**Check:**
```bash
# Verify OpenAlgo is running
curl http://localhost:5000/api/v1/health

# Check API key in config
cat portfolio_manager/openalgo_config.json | grep api_key

# Check OpenAlgo URL
cat portfolio_manager/openalgo_config.json | grep openalgo_url
```

### Issue: "API key is required" error

**Solution:**
1. Ensure `openalgo_config.json` exists in `portfolio_manager/` directory
2. Verify the API key is set (not "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD")
3. Check the API key is valid in OpenAlgo dashboard

### Issue: Broker factory returns mock client

**Check:**
- Broker type should be 'openalgo' for real broker
- API key must be provided in config
- OpenAlgo server must be running

---

## 📋 Verification Checklist

Before proceeding to live trading:

- [ ] OpenAlgo server running on port 5000
- [ ] OpenAlgo dashboard accessible at http://localhost:5000
- [ ] API key generated and saved
- [ ] `openalgo_config.json` configured with API key
- [ ] Integration tests passing
- [ ] Portfolio Manager starts without errors
- [ ] Test signals processed correctly
- [ ] Position sizing calculations correct
- [ ] Logs show proper signal flow
- [ ] No errors in analyzer mode

---

## 🚀 Next Phase: Production Deployment

Once analyzer mode is working correctly:

1. **Monitor for 1-2 weeks** in analyzer mode
2. **Switch to semi-auto mode** (manual approval)
3. **Gradually move to auto mode** (start with small positions)

See `OPENALGO_SETUP_GUIDE.md` for detailed production deployment steps.

---

## 📚 Related Documentation

- **Complete Setup Guide:** `OPENALGO_SETUP_GUIDE.md`
- **Quick Start:** `OPENALGO_QUICK_START.md`
- **Portfolio Manager README:** `portfolio_manager/README.md`
- **OpenAlgo Docs:** https://docs.openalgo.in

---

**Last Updated:** December 2, 2025
**Status:** Integration code complete, awaiting OpenAlgo server configuration

