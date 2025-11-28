# OpenAlgo Trading Bridge - Complete Guide

## 📁 Files Created

### Python Modules (6 files)
1. **bridge_config.py** - Configuration management
2. **bridge_state.py** - Position state with persistence
3. **bridge_utils.py** - Utility functions (ATM strike, expiry, market hours)
4. **openalgo_client.py** - OpenAlgo REST API client
5. **position_sizer.py** - Position sizing calculator
6. **synthetic_executor.py** - Synthetic futures execution with partial fill protection
7. **openalgo_bridge.py** - Main Flask application

### Configuration Files
- **openalgo_config.json** - Bridge configuration
- **requirements_openalgo.txt** - Python dependencies

### Auto-generated Files
- **position_state.json** - Live position tracking (created at runtime)
- **openalgo_bridge.log** - Application logs (created at runtime)

## 🚀 Quick Start

### Step 1: Install OpenAlgo

```bash
# Clone OpenAlgo
git clone https://github.com/marketcalls/openalgo.git
cd openalgo

# Install UV package manager
pip install uv

# Configure
cp .sample.env .env
# Edit .env with your Zerodha/Dhan credentials

# Start OpenAlgo
uv run app.py
```

OpenAlgo will start on http://localhost:5000

### Step 2: Configure Trading Bridge

Edit `openalgo_config.json`:

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "YOUR_API_KEY_FROM_OPENALGO_SETTINGS",
  "broker": "zerodha",
  "execution_mode": "analyzer"
}
```

**Get API Key:** OpenAlgo → Settings → API Keys → Generate

**Execution Modes:**
- `analyzer`: Test mode (no real execution)
- `semi_auto`: Manual approval required
- `auto`: Live trading (use with caution)

### Step 3: Install Dependencies

```bash
cd /path/to/ITJ-BN-Trending
pip install -r requirements_openalgo.txt
```

### Step 4: Test the Bridge

```bash
python openalgo_bridge.py
```

You should see:
```
============================================================
OpenAlgo Trading Bridge Starting...
============================================================
Broker: zerodha
Execution Mode: analyzer
Webhook endpoint: http://localhost:5001/webhook
Health check: http://localhost:5001/health
============================================================
```

### Step 5: Test Health Check

Open browser or curl:
```bash
curl http://localhost:5001/health
```

Response:
```json
{
  "status": "healthy",
  "open_positions": 0,
  "market_hours": false,
  "margin": {
    "available_cash": 500000,
    "max_lots": 18
  }
}
```

## 🔔 TradingView Integration

### Pine Script Alert Setup

1. Upload `trend_following_strategy_v6.pine` to TradingView
2. Add to Bank Nifty Futures chart (75-min)
3. Create alerts:

**Alert Name:** BN_Signals
**Condition:** Script generates alert
**Webhook URL:** `http://YOUR_IP:5001/webhook`
**Message:** `{{strategy.order.alert_message}}`

The Pine Script already sends JSON payloads like:
```json
{
  "type": "BASE_ENTRY",
  "position": "Long_1",
  "price": 52000,
  "stop": 51650,
  "suggested_lots": 12,
  "atr": 350,
  "er": 0.82,
  "timestamp": "2025-11-25T10:30:00Z"
}
```

## 🧪 Testing

### Test 1: Manual Signal

Send test webhook:
```bash
curl -X POST http://localhost:5001/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "position": "Long_1",
    "price": 52000,
    "stop": 51650,
    "suggested_lots": 5,
    "timestamp": "2025-11-25T10:30:00Z"
  }'
```

Check logs:
```bash
tail -f openalgo_bridge.log
```

### Test 2: Position Query

```bash
curl http://localhost:5001/positions
```

### Test 3: Reconciliation

```bash
curl -X POST http://localhost:5001/reconcile
```

## 🔧 Architecture

```
TradingView Pine Script (Bank Nifty Futures)
    ↓ Webhook Alert (JSON)
Flask App (port 5001)
    ├── Validate signal
    ├── Check market hours
    ├── Check duplicates
    └── Route to handler
        ↓
Signal Handler (BASE_ENTRY, PYRAMID, EXIT)
    ├── Calculate position size
    ├── Get ATM strike
    ├── Format symbols
    └── Execute synthetic futures
        ↓
Synthetic Executor
    ├── STEP 1: SELL PE (wait for fill)
    ├── STEP 2: BUY CE (if PE filled)
    └── Emergency cover (if CE fails)
        ↓
OpenAlgo API Client
    ├── Place orders
    ├── Check status
    └── Get positions/funds
        ↓
OpenAlgo Server (port 5000)
    ↓
Zerodha/Dhan Broker API
```

## 🛡️ Safety Features

### 1. Partial Fill Protection

```python
# Step 1: Place PE
pe_order = place_order(pe_symbol, "SELL", qty)

# Step 2: Wait for confirmation
pe_status = get_order_status(pe_order_id)

# Step 3: Only if PE filled, place CE
if pe_filled:
    ce_order = place_order(ce_symbol, "BUY", qty)
    
# Step 4: Emergency cover if CE fails
if pe_filled and not ce_filled:
    emergency_cover(pe_symbol, "BUY", qty)
```

### 2. Exit Uses Entry Strike

```python
# At entry - store exact symbols
position = {
    'pe_symbol': 'BANKNIFTY25DEC2552000PE',
    'ce_symbol': 'BANKNIFTY25DEC2552000CE'
}

# At exit - use stored symbols (NOT current ATM)
close_synthetic_long(position['pe_symbol'], position['ce_symbol'])
```

### 3. Market Hours Validation

- Rejects signals outside 9:15 AM - 3:25 PM IST
- Checks weekdays only (Mon-Fri)

### 4. Duplicate Signal Prevention

- Tracks signal hash (type + position + timestamp)
- Rejects duplicates within 60-second window

### 5. Position State Persistence

- Auto-saves to `position_state.json` on every update
- Recovers positions on restart
- Survives crashes/restarts

## 📊 Position Sizing Logic

### BASE_ENTRY (Risk-Based)

```
Risk Amount = Equity × 1.5%
Risk Per Lot = (Entry - Stop) × Lot_Size
Risk-Based Lots = Risk_Amount / Risk_Per_Lot
Margin-Based Lots = Available_Margin / 2.7L

Final Lots = min(Risk-Based, Margin-Based)
```

### PYRAMID (Triple-Constraint)

Uses `suggested_lots` from TradingView (already calculated), but verifies margin availability.

## 🔍 Monitoring

### Check Logs

```bash
tail -f openalgo_bridge.log
```

### View Positions

```bash
curl http://localhost:5001/positions | python -m json.tool
```

### Check Margin

```bash
curl http://localhost:5001/health | python -m json.tool
```

### Reconcile State

```bash
curl -X POST http://localhost:5001/reconcile
```

## ⚙️ Configuration Options

Edit `openalgo_config.json`:

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "your_key",
  "broker": "zerodha",
  "risk_percent": 1.5,
  "margin_per_lot": 270000,
  "max_pyramids": 5,
  "bank_nifty_lot_size": 35,
  "execution_mode": "analyzer",
  "market_start_hour": 9,
  "market_start_minute": 15,
  "market_end_hour": 15,
  "market_end_minute": 25,
  "duplicate_window_seconds": 60,
  "enable_partial_fill_protection": true,
  "use_monthly_expiry": true
}
```

## 🚨 Troubleshooting

### Issue: Webhook not received

**Check:**
```bash
# Is bridge running?
ps aux | grep openalgo_bridge

# Is port accessible?
curl http://localhost:5001/health

# Check logs
tail -f openalgo_bridge.log
```

### Issue: Orders rejected

**Check:**
1. OpenAlgo connected to broker (check OpenAlgo dashboard)
2. Sufficient margin (check `/health` endpoint)
3. Market hours (9:15-15:30 IST)
4. Symbol format correct

### Issue: PE filled but CE failed

**Check logs for:**
```
⚠️ ALERT: PE filled but CE failed!
🚨 Attempting emergency PE cover...
```

This is handled automatically with emergency cover.

### Issue: Position state mismatch

**Run reconciliation:**
```bash
curl -X POST http://localhost:5001/reconcile
```

Compare bridge positions vs OpenAlgo positions.

## 📈 Next Steps

1. **Test in Analyzer Mode** (1-2 weeks)
   - Set `execution_mode: "analyzer"`
   - Verify signal processing
   - Check position sizing

2. **Paper Trading** (1-2 weeks)
   - Use small position sizes
   - Monitor fills and slippage

3. **Live Trading**
   - Start with 1-2 lots
   - Scale up gradually
   - Monitor daily

## 🆘 Support

- OpenAlgo Docs: https://docs.openalgo.in
- OpenAlgo GitHub: https://github.com/marketcalls/openalgo
- Strategy Backtest: Run v6 on TradingView for reference

---

**⚠️ Important:** This is a live trading system. Always test thoroughly in analyzer mode before deploying with real capital.


