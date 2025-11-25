# OpenAlgo Integration Guide for Bank Nifty Trend Following

## Overview
This guide enables automated execution of the Bank Nifty Trend Following strategy (v6.0) using OpenAlgo. It bridges TradingView signals to your broker (Zerodha/Dhan) via a local Python service.

## Architecture
1. **TradingView**: Generates signals (Base Entry, Pyramids, Exits)
2. **Python Bridge**: Receives signals, manages position state, handles synthetic legs
3. **OpenAlgo**: Executes orders on the broker API

## Setup Instructions

### 1. OpenAlgo Installation
1. Clone OpenAlgo: `git clone https://github.com/marketcalls/openalgo.git`
2. Install dependencies: `cd openalgo && pip install uv`
3. Configure `.env` with your broker credentials
4. Run OpenAlgo: `uv run app.py` (starts on port 5000)

### 2. Bridge Installation
1. Install Python dependencies:
   ```bash
   pip install -r requirements_openalgo.txt
   ```
2. Configure `openalgo_config.json`:
   - Set your `api_key` (from OpenAlgo settings)
   - Verify `bank_nifty_lot_size` matches NSE (currently 30)
3. Run the bridge:
   ```bash
   python openalgo_bridge.py
   ```
   (Starts on port 5001)

### 3. TradingView Setup
1. Add `trend_following_strategy_v6_signals.pine` to your chart
2. Create an Alert:
   - Condition: "Bank Nifty Trend Following Signals v6.0"
   - Expiration: Open-ended
   - Alert Actions: Check "Webhook URL"
   - Webhook URL: `http://YOUR_PUBLIC_IP:5001/webhook` (Use Ngrok if local)
   - Message: `{{strategy.order.alert_message}}` (Leave empty, the script handles JSON)

## Safety Features
- **Partial Fill Protection**: Places PE first, then CE. Emergency exit if leg 2 fails.
- **Market Hours Check**: Only accepts signals 09:15-15:30 IST.
- **Exit Logic**: Closes the exact strike entered (not current ATM).
- **State Persistence**: Positions saved to `position_state.json` to survive restarts.

## Monitoring
- Check `openalgo_bridge.log` for execution details
- Monitor OpenAlgo dashboard for live orders
- Verify positions in `position_state.json` periodically

## Troubleshooting
- **Signal Ignored**: Check market hours or duplicate signal logic.
- **Order Failed**: Verify OpenAlgo is running and margin is sufficient.
- **Partial Fill**: Check log for "EMERGENCY EXIT" and verify flat position in broker.


