# Quick Start: Manual Trading Setup (Phase 1)

**Goal:** Start trading Bank Nifty v6 strategy THIS WEEK with minimal setup

**Timeline:** 1 day setup
**Cost:** ₹2,650/month (~$32)
**Effort:** Manual execution (1-2 signals per month)

---

## Overview

This is a **barebones MVP** to validate your strategy in live market while building automation gradually:

```
TradingView → Telegram Alert → You (manual) → Stoxxo → Broker
                                       ↓
                              Google Sheets Log
```

---

## Prerequisites

- ✅ TradingView Pro/Premium account (for alerts)
- ✅ Stoxxo license and installation
- ✅ Broker account connected to Stoxxo
- ✅ Bank Nifty v6 script loaded on TradingView
- ✅ Telegram account
- ✅ Google account (for Sheets)

---

## Step 1: Set Up Telegram Bot (15 minutes)

### 1.1 Create Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose bot name: e.g., "BN Trend Alerts"
4. Choose username: e.g., "bn_trend_alerts_bot"
5. **Copy the bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 1.2 Get Your Chat ID

1. Search for **@userinfobot** in Telegram
2. Send `/start`
3. **Copy your chat ID** (looks like: `987654321`)

### 1.3 Test Bot

Open browser and visit:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage?chat_id=<YOUR_CHAT_ID>&text=Test
```

Replace `<YOUR_BOT_TOKEN>` and `<YOUR_CHAT_ID>`. You should receive "Test" message.

---

## Step 2: Configure TradingView Alerts (30 minutes)

### 2.1 Add Alert Code to Your v6 Script

Open `trend_following_strategy_v6.pine` in TradingView Pine Editor and add alert calls:

**At the end of your base entry logic** (around line 295):
```pinescript
// After: strategy.entry("Long_1", strategy.long, qty=final_lots)

// Add this alert
if base_entry
    alert_msg = '🟢 BASE ENTRY\n' +
                'Price: ' + str.tostring(close) + '\n' +
                'Lots: ' + str.tostring(final_lots) + '\n' +
                'Stop: ' + str.tostring(close - atr) + '\n' +
                'ATR: ' + str.tostring(atr) + '\n' +
                'Time: ' + str.tostring(hour) + ':' + str.tostring(minute)
    alert(alert_msg, alert.freq_once_per_bar_close)
```

**At your pyramid logic** (around line 310):
```pinescript
// After: strategy.entry("Long_2", strategy.long, qty=pyramid_size)

// Add this alert
if pyramid_entry and pyramid_count == 0
    alert_msg = '🔵 PYRAMID 1\n' +
                'Price: ' + str.tostring(close) + '\n' +
                'Lots: ' + str.tostring(pyramid_size) + '\n' +
                'Move from base: ' + str.tostring(atr_moves) + ' ATR\n' +
                'Total P&L: ₹' + str.tostring(unrealized_pnl)
    alert(alert_msg, alert.freq_once_per_bar_close)
```

**At your exit logic** (for Tom Basso stops, around line 441):
```pinescript
// After: strategy.close("Long_1", comment="Tom Basso Stop")

// Add this alert
if basso_exit_long1
    alert_msg = '🔴 EXIT LONG_1\n' +
                'Stop Hit: ' + str.tostring(basso_stop_long1) + '\n' +
                'Current: ' + str.tostring(close) + '\n' +
                'Entry was: ' + str.tostring(base_entry_price) + '\n' +
                'P&L: ₹' + str.tostring((close - base_entry_price) * strategy.position_size * lot_size)
    alert(alert_msg, alert.freq_once_per_bar_close)
```

Repeat for all 6 positions (Long_1 through Long_6).

### 2.2 Create Alert in TradingView

1. Click **Alert** button (clock icon) in top toolbar
2. **Condition:** Select your script name
3. **Alert name:** "BN v6 - {{timenow}}"
4. **Message:** Leave as `{{strategy.order.alert_message}}`
5. **Webhook URL:** (Get from next step)
6. **Frequency:** "Once Per Bar Close"
7. Click **Create**

### 2.3 Set Up Telegram Webhook

Use this service to forward TradingView alerts to Telegram:

**Option A: TradingView-Webhook-Telegram (Free)**

1. Go to: https://tradingview-webhook-telegram.herokuapp.com/
2. Enter your **Bot Token** and **Chat ID**
3. Click "Generate Webhook URL"
4. Copy the URL (looks like: `https://api.telegram.org/bot...`)
5. Paste into TradingView Alert → Webhook URL

**Option B: Make.com (Integromat) - Recommended**

1. Sign up at https://www.make.com (free tier: 1,000 operations/month)
2. Create scenario: **Webhooks → Telegram**
3. Add "Webhooks" module → "Custom webhook"
4. Copy webhook URL
5. Add "Telegram" module → "Send a text message"
   - Bot token: Your bot token
   - Chat ID: Your chat ID
   - Message: `{{1.strategy.order.alert_message}}`
6. Save and activate
7. Paste webhook URL into TradingView

---

## Step 3: Set Up Google Sheets Trade Log (15 minutes)

### 3.1 Create New Sheet

1. Go to https://sheets.google.com
2. Create new spreadsheet: "BN v6 Trade Log"

### 3.2 Add Headers (Row 1)

```
A: Date | B: Time | C: Signal Type | D: Signal Price | E: Actual Fill |
F: Slippage | G: Lots | H: P&L | I: Theoretical P&L | J: Divergence |
K: Notes | L: Cumulative P&L
```

### 3.3 Add Formulas

**In cell F2 (Slippage):**
```
=E2-D2
```

**In cell J2 (Divergence):**
```
=I2-H2
```

**In cell L2 (Cumulative P&L):**
```
=SUM($H$2:H2)
```

Drag formulas down for 100+ rows.

### 3.4 Add Summary Dashboard (to the right)

**In column N:**
```
N1: METRICS
N2: Total Trades
N3: Win Rate
N4: Total P&L
N5: Avg Slippage
N6: Max Slippage
N7: Avg Divergence
```

**In column O (formulas):**
```
O2: =COUNTA(C2:C100)
O3: =COUNTIF(H2:H100,">0")/COUNTA(H2:H100)
O4: =SUM(H2:H100)
O5: =AVERAGE(F2:F100)
O6: =MAX(F2:F100)
O7: =AVERAGE(J2:J100)
```

---

## Step 4: Stoxxo Setup (30 minutes)

### 4.1 Install Stoxxo

1. Download from https://algobaba.com/ or your broker's integration page
2. Install on Windows machine (must stay running during market hours)
3. Launch Stoxxo

### 4.2 Connect to Broker

1. In Stoxxo: **Settings → Broker Configuration**
2. Select your broker (Zerodha, ICICI, Angel, etc.)
3. Enter API credentials
4. Test connection

### 4.3 Test Order Placement

**Manual test:**
1. Open Stoxxo order window
2. Try placing a small order (1 lot) for testing
3. Verify order reaches broker terminal
4. Cancel test order

---

## Step 5: Manual Execution Workflow

When you receive a Telegram alert:

### 5.1 Base Entry Alert

**Alert example:**
```
🟢 BASE ENTRY
Price: 50,000
Lots: 12
Stop: 49,650
ATR: 350
Time: 10:29
```

**Your actions:**
1. **Check current market price** (within 1 minute of alert)
2. **Calculate ATM strike:**
   - If price = 50,000 → ATM = 50,000 (round to nearest 100)
3. **Open Stoxxo order window**
4. **Place TWO orders** (synthetic future):

   **Order 1: Sell ATM Put**
   - Symbol: `BANKNIFTY<EXPIRY>50000PE` (current month)
   - Action: SELL
   - Quantity: 12 × 15 = 180 (12 lots × lot size)
   - Type: MARKET

   **Order 2: Buy ATM Call**
   - Symbol: `BANKNIFTY<EXPIRY>50000CE`
   - Action: BUY
   - Quantity: 180
   - Type: MARKET

5. **Note actual fill prices:**
   - PE Sell: e.g., ₹150
   - CE Buy: e.g., ₹100
   - **Synthetic future price** = PE - CE = 150 - 100 = 50 points = 50,050 effective price

6. **Log to Google Sheets:**
   - Date: Today
   - Time: 10:29
   - Signal Type: BASE_ENTRY
   - Signal Price: 50,000
   - Actual Fill: 50,050
   - Slippage: 50
   - Lots: 12
   - Theoretical P&L: (leave blank for now)
   - Notes: "First base entry"

### 5.2 Pyramid Alert

**Alert example:**
```
🔵 PYRAMID 1
Price: 50,750
Lots: 6
Move from base: 2.14 ATR
Total P&L: ₹54,000
```

**Your actions:**
1. **Verify profitability:** Check if existing position is profitable (price > entry)
2. **Calculate new ATM strike:**
   - If price = 50,750 → ATM = 50,800 (round to nearest 100)
3. **Place pyramid order** (same as base entry, but 6 lots instead of 12)
4. **Log to Google Sheets** with Signal Type: "PYRAMID_1"

### 5.3 Exit Alert

**Alert example:**
```
🔴 EXIT LONG_1
Stop Hit: 49,650
Current: 49,600
Entry was: 50,000
P&L: ₹-18,000
```

**Your actions:**
1. **Exit the position immediately**
2. **Reverse the synthetic future:**
   - Buy back the PE (was sold)
   - Sell the CE (was bought)
3. **Log actual P&L to Google Sheets**

---

## Step 6: Daily Routine

### Morning (9:00 AM)
- ✅ Ensure Stoxxo is running
- ✅ Check broker connection
- ✅ Open TradingView chart (BN, 75-min)
- ✅ Verify script is active
- ✅ Keep Telegram open

### During Market Hours (9:15 AM - 3:30 PM)
- ✅ Monitor Telegram for alerts (expect ~0-1 per week)
- ✅ Execute signals within 1-2 minutes
- ✅ Log to Google Sheets immediately

### EOD (3:30 PM)
- ✅ Update Google Sheets with day's summary
- ✅ Review divergence (theoretical vs actual)
- ✅ Note any issues in "Notes" column

### Weekly Review (Friday evening)
- ✅ Calculate weekly P&L
- ✅ Analyze slippage patterns
- ✅ Compare to TradingView backtest results

---

## Expected Signal Frequency

Based on Bank Nifty v6 backtest:
- **Signals per year:** ~55 trades
- **Signals per month:** ~4-5
- **Signals per week:** ~1
- **Base entries:** ~10-15 per year
- **Pyramids:** ~40-50 per year

**You'll receive about 1 alert per week** (very manageable for manual execution).

---

## Troubleshooting

### No Alerts Received

1. ✅ Check TradingView alert is "Active" (green checkmark)
2. ✅ Verify webhook URL is correct
3. ✅ Test Telegram bot with browser URL
4. ✅ Check if chart is loaded and script is running

### Missed Alert (AFK)

- Document in Google Sheets: "MISSED - AFK"
- Don't chase the trade after 5+ minutes
- Wait for next signal

### High Slippage (>200 points)

- If slippage > 200 points, **skip the trade**
- Alert conditions may have changed
- Log as "SKIPPED - High Slippage"

### Stoxxo Connection Lost

- Restart Stoxxo application
- Re-authenticate with broker
- Test with small order before live trade

---

## Cost Breakdown (Monthly)

| Item | Cost (₹) | Cost ($) |
|------|----------|----------|
| TradingView Pro | 650 | ~8 |
| Stoxxo License | 2,000 | ~24 |
| **Total** | **2,650** | **~32** |

No cloud costs, no VPS, no complex setup!

---

## Success Criteria (Week 1)

- ✅ Telegram alerts working
- ✅ Executed 1+ signals manually
- ✅ Google Sheets tracking in place
- ✅ Comfortable with Stoxxo order placement
- ✅ Measured actual slippage vs signal price

---

## Next Step: Phase 2 (Week 2-4)

Once comfortable with manual execution:
- Set up simple Python webhook receiver
- Automate order placement
- See `PHASE2_AUTOMATION_SETUP.md` (coming next)

---

## Support & Resources

- **Stoxxo Support:** https://algobaba.com/contact
- **TradingView Alerts:** https://www.tradingview.com/support/solutions/43000529348/
- **Telegram Bot API:** https://core.telegram.org/bots/api

---

**You're ready to start trading! Focus on execution quality, track everything, iterate next week.**
