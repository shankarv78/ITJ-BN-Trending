# Phase 2: Automation Setup Guide
## Bank Nifty Synthetic Futures with Stoxxo

This guide explains how to automate your trading using the **Stoxxo Bridge**.

### 1. Prerequisites

*   **Python 3.x**: Download from [python.org](https://www.python.org/downloads/).
*   **Stoxxo**: Installed and running (logged in to your broker).
*   **TradingView Pro/Premium**: Required for Webhook alerts.

### 2. Install Python Dependencies

Open your terminal (Command Prompt or PowerShell) and run:

```bash
pip install flask requests
```

### 3. Start the Stoxxo Bridge

1.  Download `stoxxo_bridge.py` to a folder (e.g., `C:\Trading\`).
2.  Open terminal in that folder.
3.  Run the bridge:

```bash
python stoxxo_bridge.py
```

You should see:
> 🚀 Stoxxo Bridge Started on Port 5000
> 👉 Send Webhooks to: http://localhost:5000/webhook

### 4. Configure TradingView Alert

1.  Open **TradingView** and load `trend_following_strategy_v6.pine`.
2.  Go to **Settings (Inputs)** and ensure `Enable Pyramiding` is checked.
3.  Click **"Add Alert"** (Clock icon) on the top toolbar.
4.  **Condition**: Select `Bank Nifty Trend Following v6.0 (Automated)`.
    *   Select `Any alert() function call`.
5.  **Alert Name**: `BN v6 Automation`.
6.  **Message**: Leave as `{{strategy.order.alert_message}}` (or empty, the script handles the message).
7.  **Notifications**:
    *   Check **Webhook URL**.
    *   Enter: `http://localhost:5000/webhook`
    *   *(Note: If TradingView is on the cloud and Bridge is local, you need a public URL. See "Exposing Localhost" below)*.

### 5. Exposing Localhost (Critical Step)

Since TradingView is on the internet and your bridge is on your laptop, they can't talk directly. You need a "Tunnel".

**Option A: Ngrok (Recommended)**
1.  Download [Ngrok](https://ngrok.com/).
2.  Run: `ngrok http 5000`
3.  Copy the `https://....ngrok-free.app` URL.
4.  Paste THIS URL into TradingView Webhook:
    `https://your-ngrok-url.ngrok-free.app/webhook`

**Option B: Cloud Hosting**
*   Host `stoxxo_bridge.py` on a VPS (AWS, DigitalOcean) where it can run 24/7.

### 6. Testing

1.  **Dry Run**:
    *   Keep Stoxxo open but maybe use a "Paper Trading" profile if available, or monitor the logs first.
    *   The `stoxxo_bridge.py` currently has the actual API call **commented out** (Lines 94-96).
    *   It will print "Sending to Stoxxo..." in the logs.
    *   **To go live**: Uncomment lines 94-96 in `stoxxo_bridge.py`.

2.  **Verify Logs**:
    *   Check `stoxxo_bridge.log` to see if signals are received and processed correctly.

### 7. Safety Checklist

*   [ ] Bridge running before market open (9:15 AM).
*   [ ] Stoxxo logged in and "Connected".
*   [ ] Ngrok running (if using local).
*   [ ] Funds available in broker.
*   [ ] **Emergency Stop**: If things go wrong, Close All in Stoxxo and Stop the Python script (Ctrl+C).
