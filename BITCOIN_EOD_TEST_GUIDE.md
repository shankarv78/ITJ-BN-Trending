# Bitcoin EOD Signal Testing Guide

## Overview

This guide explains how to test the EOD (End-of-Day) continuous signal generation logic using Bitcoin perpetual futures on TradingView.

## Components Created

1. **`Bitcoin_EOD_Signal_Tester.pine`** - Pine Script v6 indicator for TradingView
2. **`signal_listener.py`** - Python Flask server to receive and log signals

## Quick Start

### Step 1: Start the Python Listener

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending

# Activate your virtual environment if needed
source venv/bin/activate

# Install Flask if not already installed
pip install flask

# Start the listener
python signal_listener.py
```

The server will start on `http://0.0.0.0:5050/webhook`

### Step 2: Expose to Internet (for TradingView)

TradingView webhooks need a public URL. Use Cloudflare Tunnel:

```bash
# Install cloudflared if needed
brew install cloudflared

# Start tunnel (no account needed for quick testing)
cloudflared tunnel --url http://localhost:5050
```

Copy the Cloudflare URL (e.g., `https://random-hash.trycloudflare.com`)

### Step 3: Add Indicator to TradingView

1. Open TradingView and go to **BINANCE:BTCUSDT.P** chart (Bitcoin perpetual)
2. Set timeframe to **15 minutes** or **1 hour** for testing
3. Open Pine Script editor (bottom panel)
4. Copy contents of `Bitcoin_EOD_Signal_Tester.pine`
5. Click "Add to Chart"

### Step 4: Create TradingView Alert

1. Click "Create Alert" (clock icon on right toolbar)
2. **Condition**: Select "Bitcoin EOD Signal Tester v1.0"
3. **Options**:
   - Trigger: "Any alert() function call" (important!)
   - Expiration: Set appropriately
4. **Webhook URL**: Paste your Cloudflare URL + `/webhook`
   - Example: `https://random-hash.trycloudflare.com/webhook`
5. Click "Create"

### Step 5: Watch Signals Flow

In your terminal running `signal_listener.py`, you'll see signals like:

```
──────────────────────────────────────────────────
[2025-12-27 14:30:45.123] EOD_MONITOR
Status: ✅ Valid
  Instrument: BTCUSDT
  Price: 96500.50
  Timestamp: 2025-12-27T14:30:45
  Conditions: 5/7 ⏳ Waiting
    RSI: ✓ (72.34)
    EMA: ✓ (94200.50)
    DC:  ✗ (97100.00)
    ADX: ✓ (22.15)
    ER:  ✓ (0.6234)
    ST:  ✓ (95800.25)
    Doji: ✓
  Entry Signal: NO
  Exit Signal: NO
  Position: FLAT, Pyramids: 0
──────────────────────────────────────────────────
```

## Signal Types

| Signal Type | Frequency | Purpose |
|------------|-----------|---------|
| `EOD_MONITOR` | Every tick | Continuous condition monitoring |
| `BASE_ENTRY` | Once per bar close | Entry signal when all 7 conditions met |
| `PYRAMID` | Once per bar close | Add to position signal |
| `EXIT` | Once per bar close | Exit signal when close < SuperTrend |

## Indicator Settings

### EOD Testing Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Enable EOD Monitoring | `true` | Master switch for EOD signals |
| EOD Hour | `-1` | Hour for EOD window (-1 = any time) |
| EOD Window Start | `0` | Minute to start EOD window |
| Continuous EOD Mode | `true` | Always fire EOD signals (for testing) |
| EOD Only On Entry | `false` | Only fire when all 7 conditions met |

### Signal Testing

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Entry Alerts | `true` | Fire BASE_ENTRY signals |
| Enable Pyramid Alerts | `true` | Fire PYRAMID signals |
| Enable Exit Alerts | `true` | Fire EXIT signals |
| Enable EOD Alerts | `true` | Fire EOD_MONITOR signals |

### Position Simulation

| Setting | Default | Description |
|---------|---------|-------------|
| Simulate Position | `false` | Pretend we're in a position |
| Simulated Pyramid Count | `0` | Number of pyramids to simulate |

## Testing Scenarios

### Scenario 1: EOD Monitor Only

Test continuous EOD signal flow:
1. Enable "Continuous EOD Mode"
2. Disable "EOD Only On Entry"
3. Watch EOD_MONITOR signals every tick

### Scenario 2: Production-like EOD

Test EOD signals matching production behavior:
1. Disable "Continuous EOD Mode"
2. Enable "EOD Only On Entry"
3. Set EOD Hour to current hour
4. Watch signals only when conditions are met

### Scenario 3: Full Signal Flow

Test all signal types:
1. Enable all signal alerts
2. Enable "Simulate Position"
3. Set pyramid count to 0
4. Watch BASE_ENTRY, PYRAMID, EXIT signals

## Signal Format (JSON)

### EOD_MONITOR

```json
{
  "type": "EOD_MONITOR",
  "instrument": "BTCUSDT",
  "timestamp": "2025-12-27T14:30:45",
  "price": 96500.50,
  "conditions": {
    "rsi_condition": true,
    "ema_condition": true,
    "dc_condition": false,
    "adx_condition": true,
    "er_condition": true,
    "st_condition": true,
    "not_doji": true,
    "long_entry": false,
    "long_exit": false
  },
  "indicators": {
    "rsi": 72.34,
    "ema": 94200.50,
    "dc_upper": 97100.00,
    "adx": 22.15,
    "er": 0.6234,
    "supertrend": 95800.25,
    "atr": 850.25
  },
  "position_status": {
    "in_position": false,
    "pyramid_count": 0
  }
}
```

### BASE_ENTRY

```json
{
  "type": "BASE_ENTRY",
  "instrument": "BTCUSDT",
  "position": "Long_1",
  "price": 96500.50,
  "stop": 95800.25,
  "lots": 1,
  "atr": 850.25,
  "er": 0.6234,
  "supertrend": 95800.25,
  "timestamp": "2025-12-27T14:30:45"
}
```

## Troubleshooting

### No signals received

1. Check cloudflared is running and URL is correct
2. Verify TradingView alert is active (green dot)
3. Check alert condition is "Any alert() function call"
4. Ensure webhook URL ends with `/webhook`

### Invalid signals

1. Check Pine Script compiled without errors
2. Verify indicator settings match expected format
3. Check Python listener console for validation errors

### Rate limiting

TradingView may rate limit frequent alerts. If testing EOD_MONITOR:
1. Use "EOD Only On Entry" mode to reduce signal frequency
2. Or wait between test sessions

## Integration with Portfolio Manager

The signal format matches what `portfolio_manager/core/webhook_parser.py` expects. To integrate:

1. Replace the listener URL with the Portfolio Manager webhook endpoint
2. Ensure EOD_MONITOR parsing is enabled in the parser
3. The signals will be processed by `parse_eod_monitor_signal()`

## Files Reference

| File | Description |
|------|-------------|
| `Bitcoin_EOD_Signal_Tester.pine` | TradingView indicator |
| `signal_listener.py` | Python webhook receiver |
| `GoldMini_EOD_Monitor.pine` | Reference: Gold Mini EOD monitor |
| `GoldMini_TF_V8.5.pine` | Reference: Gold strategy with EOD |
| `portfolio_manager/core/webhook_parser.py` | Production signal parser |
| `portfolio_manager/core/eod_monitor.py` | Production EOD monitor |
