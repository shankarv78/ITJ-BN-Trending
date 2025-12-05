# OpenAlgo Installation & Integration Guide

## 📋 Overview

This guide covers:
1. Installing OpenAlgo server from GitHub
2. Configuring OpenAlgo with broker credentials
3. Integrating OpenAlgo client with Portfolio Manager
4. Testing the complete setup

**Estimated Time:** 3-4 hours

---

## Part 1: Install OpenAlgo Server (30-45 minutes)

### Step 1.1: Clone OpenAlgo Repository

```bash
# Navigate to your home directory or preferred location
cd ~

# Clone OpenAlgo
git clone https://github.com/marketcalls/openalgo.git
cd openalgo
```

### Step 1.2: Install UV Package Manager

```bash
# Install UV (Python package manager)
pip install uv

# Verify installation
uv --version
```

### Step 1.3: Configure OpenAlgo

```bash
# Copy sample environment file
cp .sample.env .env

# Edit .env with your broker credentials
nano .env  # or use your preferred editor
```

**Required Configuration in `.env`:**

```env
# Broker Configuration (same variables for all brokers)
BROKER_API_KEY=your_broker_api_key_here
BROKER_API_SECRET=your_broker_api_secret_here

# For Zerodha: Use your Zerodha API key and secret
# For Dhan: Use your Dhan client ID as API key and access token as secret

# Market Data Configuration (Optional - only for XTS API supported brokers)
BROKER_API_KEY_MARKET=your_market_api_key_here
BROKER_API_SECRET_MARKET=your_market_api_secret_here

# Redirect URL for OAuth callbacks
REDIRECT_URL=http://127.0.0.1:5000/<broker>/callback

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
- The broker type (Zerodha, Dhan, etc.) is selected through the OpenAlgo dashboard after starting the server
- `BROKER_API_KEY` and `BROKER_API_SECRET` are generic - use your broker's credentials
- Generate new random values for `APP_KEY` and `API_KEY_PEPPER` for security

### Step 1.4: Start OpenAlgo Server

```bash
# Start OpenAlgo
uv run app.py

# Server will start on http://localhost:5000
```

**Expected Output:**
```
 * Running on http://localhost:5000
 * OpenAlgo Server Started
 * Broker: zerodha
```

### Step 1.5: Access OpenAlgo Dashboard

1. Open browser: http://localhost:5000
2. Login with default credentials (check OpenAlgo docs)
3. Navigate to Settings → API Keys
4. Generate a new API key
5. **Save this API key** - you'll need it for Portfolio Manager

---

## Part 2: Integrate with Portfolio Manager (2-3 hours)

### Step 2.1: Create Broker Module Structure

Run the integration script:

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending
./setup_openalgo_integration.sh
```

Or manually:

```bash
cd portfolio_manager

# Create brokers directory
mkdir -p brokers

# Copy OpenAlgo client
cp ../openalgo_client.py brokers/

# Create __init__.py
touch brokers/__init__.py
```

### Step 2.2: Create Broker Factory

The integration script will create:
- `portfolio_manager/brokers/factory.py` - Broker factory pattern
- `portfolio_manager/brokers/openalgo_client.py` - OpenAlgo client
- `portfolio_manager/brokers/mock_broker.py` - Mock broker for testing

### Step 2.3: Configure Portfolio Manager

```bash
cd portfolio_manager

# Copy example config
cp openalgo_config.json.example openalgo_config.json

# Edit with your OpenAlgo API key
nano openalgo_config.json
```

**Configuration:**

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD",
  "broker": "zerodha",
  "execution_mode": "analyzer"
}
```

**Execution Modes:**
- `analyzer`: Test mode (no real trades) - **START HERE**
- `semi_auto`: Manual approval required
- `auto`: Live trading (use with extreme caution)

---

## Part 3: Testing (1 hour)

### Test 1: OpenAlgo Server Health

```bash
# Check OpenAlgo is running
curl http://localhost:5000/api/v1/health

# Expected response:
# {"status": "ok", "broker": "zerodha"}
```

### Test 2: Portfolio Manager with Mock Broker

```bash
cd portfolio_manager

# Run tests with MockBrokerSimulator
pytest tests/integration/test_signal_validation_integration.py -v

# All tests should pass
```

### Test 3: Portfolio Manager with Real OpenAlgo

```bash
# Start Portfolio Manager in analyzer mode
python portfolio_manager.py live \
  --broker openalgo \
  --api-key YOUR_OPENALGO_API_KEY \
  --capital 5000000 \
  --mode analyzer

# Expected output:
# Portfolio Manager starting...
# Broker: OpenAlgo (analyzer mode)
# Connected to OpenAlgo: http://localhost:5000
# Webhook endpoint: http://localhost:5001/webhook
```

### Test 4: Send Test Signal

```bash
# In another terminal, send test webhook
curl -X POST http://localhost:5001/webhook \
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

# Check Portfolio Manager logs for:
# - Signal received
# - Validation passed
# - Position size calculated
# - Order sent to OpenAlgo (analyzer mode - not executed)
```

---

## Part 4: Production Deployment

### Prerequisites Checklist

- [ ] OpenAlgo server running and stable
- [ ] Broker credentials configured and tested
- [ ] Portfolio Manager tests passing
- [ ] Database (PostgreSQL) set up (optional but recommended)
- [ ] Redis set up for HA (optional)
- [ ] TradingView alerts configured

### Step 4.1: Enable Database Persistence

```bash
cd portfolio_manager

# Set up PostgreSQL (see DATABASE_SETUP.md)
psql -U pm_user -d portfolio_manager -f migrations/001_initial_schema.sql

# Configure database
cp database_config.json.example database_config.json
# Edit with your database credentials
```

### Step 4.2: Start Portfolio Manager with Database

```bash
python portfolio_manager.py live \
  --broker openalgo \
  --api-key YOUR_OPENALGO_API_KEY \
  --capital 5000000 \
  --db-config database_config.json \
  --db-env local \
  --mode analyzer
```

### Step 4.3: Configure TradingView Alerts

1. Upload Pine Scripts to TradingView:
   - `BankNifty_TF_V8.0.pine`
   - `GoldMini_TF_V8.0.pine`

2. Create alerts:
   - **Alert Name:** BN_Signals (or GM_Signals)
   - **Condition:** Strategy generates alert
   - **Webhook URL:** `http://YOUR_IP:5001/webhook`
   - **Message:** `{{strategy.order.alert_message}}`

3. Use ngrok or similar for webhook access:
   ```bash
   ngrok http 5001
   # Use the ngrok URL in TradingView webhook
   ```

### Step 4.4: Gradual Rollout

**Phase 1: Analyzer Mode (1-2 weeks)**
- Run in analyzer mode
- Monitor signal processing
- Verify position sizing
- Check logs for errors

**Phase 2: Semi-Auto Mode (1-2 weeks)**
- Switch to semi_auto mode
- Manually approve each trade
- Monitor execution quality
- Track slippage

**Phase 3: Live Trading (Start Small)**
- Switch to auto mode
- Start with 1-2 lots
- Monitor closely
- Scale up gradually

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      TradingView                             │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │ BankNifty Chart  │         │ GoldMini Chart   │         │
│  │ (V8.0 Strategy)  │         │ (V8.0 Strategy)  │         │
│  └────────┬─────────┘         └────────┬─────────┘         │
│           │ Webhook Alert              │ Webhook Alert      │
└───────────┼────────────────────────────┼────────────────────┘
            │                            │
            └────────────┬───────────────┘
                         │ JSON Signals
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Portfolio Manager (Port 5001)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Flask Webhook Server                                  │  │
│  │  - Signal Validation                                  │  │
│  │  - Position Sizing (Tom Basso)                       │  │
│  │  - Risk Management                                    │  │
│  │  - EOD Pre-Close Execution                           │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │ REST API Calls                        │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenAlgo Server (Port 5000)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ REST API Server                                       │  │
│  │  - Order Execution                                    │  │
│  │  - Broker Authentication                              │  │
│  │  - Position Management                                │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │ Broker API                            │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   Broker (Zerodha/Dhan)                      │
│  - Order Execution                                           │
│  - Position Tracking                                         │
│  - Margin Management                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Issue: OpenAlgo not starting

**Check:**
```bash
# Verify UV installation
uv --version

# Check .env file exists
ls -la .env

# Check Python version (needs 3.8+)
python --version
```

### Issue: Portfolio Manager can't connect to OpenAlgo

**Check:**
```bash
# Verify OpenAlgo is running
curl http://localhost:5000/api/v1/health

# Check API key is correct
# Check openalgo_config.json has correct URL and key
```

### Issue: Orders not executing

**Check:**
1. Execution mode (should be 'analyzer' for testing)
2. OpenAlgo broker connection status
3. Broker credentials in OpenAlgo .env
4. Market hours (9:15 AM - 3:30 PM IST for Bank Nifty)

### Issue: Database connection failed

**Check:**
```bash
# Verify PostgreSQL is running
psql -U pm_user -d portfolio_manager -c "SELECT 1;"

# Check database_config.json credentials
```

---

## Next Steps

After successful installation:

1. **Run in Analyzer Mode** for 1-2 weeks
2. **Monitor Logs** daily
3. **Review Signals** and position sizing
4. **Test EOD Execution** during last 15 minutes
5. **Gradually Move to Live Trading**

---

## Support & Resources

- **OpenAlgo Docs:** https://docs.openalgo.in
- **OpenAlgo GitHub:** https://github.com/marketcalls/openalgo
- **Portfolio Manager README:** `portfolio_manager/README.md`
- **Database Setup:** `portfolio_manager/DATABASE_SETUP.md`

---

## Safety Reminders

⚠️ **IMPORTANT:**
- Always start in **analyzer mode**
- Test thoroughly before live trading
- Start with small position sizes
- Monitor closely during initial weeks
- Keep OpenAlgo and Portfolio Manager logs
- Have a manual override plan

---

**Last Updated:** December 2, 2025
**Version:** 1.0


