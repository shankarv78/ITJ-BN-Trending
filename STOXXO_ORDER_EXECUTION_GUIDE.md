# Stoxxo Order Execution Guide

**Purpose:** Step-by-step guide to manually execute Bank Nifty synthetic futures via Stoxxo

**Target:** Phase 1 manual trading (before automation)

---

## What is a Synthetic Future?

A **synthetic future** replicates a futures position using options:

```
Synthetic Long Future = Sell ATM Put + Buy ATM Call
```

**Why use synthetic futures?**
- Better capital efficiency (lower margin vs actual futures)
- More liquidity in options market
- Easier to manage via Stoxxo's multi-leg order interface

**Example:**
```
Bank Nifty Spot: 50,000
ATM Strike: 50,000

Order 1: SELL 50,000 PE at ₹150 (receive premium)
Order 2: BUY 50,000 CE at ₹100 (pay premium)

Net position = -150 + 100 = -50 points debit
Synthetic future entry = 50,000 - (-50) = 50,050

If Bank Nifty moves to 51,000:
- PE profit: ₹150 (option expires worthless, you keep premium)
- CE profit: 51,000 - 50,100 = ₹900
- Total profit: 150 + 900 = ₹1,050 per lot
```

---

## Stoxxo Installation & Setup

### Step 1: Download Stoxxo

**From Broker:**
- Visit your broker's "Trading Tools" or "API" section
- Look for "Stoxxo" or "Algobaba Stoxxo"
- Download installer (Windows only)

**Direct from Algobaba:**
- Website: https://algobaba.com/
- Click "Download Stoxxo"
- Save installer (stoxxo_setup.exe)

### Step 2: Install

1. Run installer as Administrator
2. Accept license agreement
3. Choose installation folder: `C:\Program Files\Stoxxo`
4. Click Install
5. Launch Stoxxo after installation

### Step 3: First Launch

1. **License Key:** Enter license key (from Algobaba or broker)
2. **Select Broker:**
   - Zerodha
   - ICICI Direct
   - Angel One
   - 5paisa
   - etc. (choose your broker)
3. **Enter Credentials:**
   - User ID
   - Password
   - API Key (if required)
   - 2FA/PIN
4. Click **Connect**

### Step 4: Verify Connection

- Status bar should show: "Connected to [Broker]"
- Green indicator dot
- If red: Check credentials, API status, internet connection

---

## Stoxxo Interface Overview

**Main Window Sections:**

```
┌─────────────────────────────────────────────────┐
│ [File] [Order] [Position] [Settings] [Help]    │
├─────────────────────────────────────────────────┤
│ Status: Connected ● | Broker: Zerodha          │
├─────────────────────────────────────────────────┤
│                                                 │
│  [Order Book]  [Trade Book]  [Positions]       │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │ Symbol  | Side | Qty | Price | Status    │ │
│  ├───────────────────────────────────────────┤ │
│  │ (empty initially)                         │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  [Place Order]  [Modify]  [Cancel]             │
│                                                 │
├─────────────────────────────────────────────────┤
│ Available Margin: ₹5,00,000 | Used: ₹0        │
└─────────────────────────────────────────────────┘
```

---

## Executing a Base Entry Signal

### Scenario

You receive this Telegram alert:

```
🟢 BASE ENTRY
Price: 50,000
Lots: 12
Stop: 49,650
ATR: 350
Time: 10:29
```

### Step-by-Step Execution

#### 1. Calculate ATM Strike

**Current price: 50,000**
- Round to nearest 100 = **50,000** (already at 100 boundary)

If price was 50,067:
- Round down: 50,000 (if closer to 50,000)
- Round up: 50,100 (if closer to 50,100)

**Rule:** Choose strike closest to current spot price.

#### 2. Determine Current Expiry

Bank Nifty options expire **last Wednesday of month**.

**Check current expiry:**
1. Open NSE website: https://www.nseindia.com/
2. Navigate: Market Data → Derivatives → Bank Nifty
3. Note current month expiry (e.g., 27-NOV-2025)

**Expiry format in Stoxxo:**
- Format: `YYMONDD`
- Example: 27-NOV-2025 = `25NOV27`

#### 3. Open Multi-leg Order Window

**In Stoxxo:**
1. Click **Order → Multi-leg Order** (or press Ctrl+M)
2. Select **Strategy Type:** "Custom" (or "Synthetic Future")

#### 4. Place Leg 1: SELL ATM PUT

**Order Entry:**

| Field | Value |
|-------|-------|
| Instrument | Bank Nifty |
| Expiry | 25NOV27 (current month) |
| Strike | 50000 |
| Option Type | PE (Put European) |
| Action | SELL |
| Quantity | 180 (12 lots × 15) |
| Order Type | MARKET |
| Product | NRML (Normal - for positional) |

**Symbol format:** `BANKNIFTY25NOV2750000PE`

**Click "Add Leg"** (don't execute yet!)

#### 5. Place Leg 2: BUY ATM CALL

**Order Entry:**

| Field | Value |
|-------|-------|
| Instrument | Bank Nifty |
| Expiry | 25NOV27 |
| Strike | 50000 |
| Option Type | CE (Call European) |
| Action | BUY |
| Quantity | 180 |
| Order Type | MARKET |
| Product | NRML |

**Symbol format:** `BANKNIFTY25NOV2750000CE`

**Click "Add Leg"**

#### 6. Review Multi-leg Order

**Order summary should show:**

```
Leg 1: SELL 180 BANKNIFTY25NOV2750000PE @ MARKET
Leg 2: BUY 180 BANKNIFTY25NOV2750000CE @ MARKET

Estimated Margin: ₹3,24,000 (approx ₹2.7L per lot × 12 lots)
```

#### 7. Execute Order

**Final checks:**
- ✅ Both legs present
- ✅ Correct quantities (180 each)
- ✅ Correct strikes (same ATM)
- ✅ Correct expiry (current month)
- ✅ Margin available

**Click "Place Order"** or **"Execute"**

#### 8. Monitor Execution

**Order Book will show:**

```
BANKNIFTY25NOV2750000PE | SELL | 180 | MARKET | Pending...
BANKNIFTY25NOV2750000CE | BUY  | 180 | MARKET | Pending...
```

**Wait for fills (typically 5-30 seconds):**

```
BANKNIFTY25NOV2750000PE | SELL | 180 | 152.50 | FILLED ✓
BANKNIFTY25NOV2750000CE | BUY  | 180 | 98.75  | FILLED ✓
```

#### 9. Calculate Actual Entry Price

**Synthetic future price:**
```
Entry = Spot - (PE premium received - CE premium paid)
      = 50,000 - (152.50 - 98.75)
      = 50,000 - 53.75
      = 49,946.25

(Or you can think of it as: Spot + Net Debit)
```

**Slippage:**
```
Signal price: 50,000
Actual entry: 49,946.25
Slippage: -53.75 points (favorable!)
```

#### 10. Log to Google Sheets

| Date | Time | Signal Type | Signal Price | Actual Fill | Slippage | Lots | Notes |
|------|------|-------------|--------------|-------------|----------|------|-------|
| 2025-11-18 | 10:29 | BASE_ENTRY | 50,000 | 49,946 | -54 | 12 | PE: 152.50, CE: 98.75 |

---

## Executing a Pyramid Signal

### Scenario

You receive this alert:

```
🔵 PYRAMID 1 (Long_2)
Price: 50,750
Lots: 6
ATR Moves: 2.14
Base Entry: 50,000
Move: +750 pts
Total P&L: ₹54,000
```

### Execution Steps

#### 1. Verify Profitability

**Check existing position:**
- Position: Long_1 (12 lots entered at 49,946)
- Current price: 50,750
- P&L: (50,750 - 49,946) × 12 × 15 = **₹1,44,720** ✅ Profitable

#### 2. Calculate New ATM Strike

Current price: 50,750
- Round to nearest 100 = **50,800** (closer to 50,800 than 50,700)

#### 3. Execute Pyramid (Same as Base Entry)

**Leg 1: SELL 50,800 PE**
- Quantity: 90 (6 lots × 15)

**Leg 2: BUY 50,800 CE**
- Quantity: 90

#### 4. Note Pyramid in Google Sheets

| Date | Time | Signal Type | Signal Price | Actual Fill | Slippage | Lots | Notes |
|------|------|-------------|--------------|-------------|----------|------|-------|
| 2025-11-19 | 11:44 | PYRAMID_1 | 50,750 | 50,825 | 75 | 6 | Strike: 50800 |

---

## Executing an Exit Signal

### Scenario

You receive this alert:

```
🔴 EXIT LONG_1
Stop: 49,650
Current: 49,600
Entry: 50,000
P&L: ₹-72,000
Lots: 12
```

### Execution Steps

#### 1. Identify Position to Close

**In Stoxxo Positions tab:**

```
Position: Long_1
BANKNIFTY25NOV2750000PE | SELL | 180 | Entry: 152.50
BANKNIFTY25NOV2750000CE | BUY  | 180 | Entry: 98.75
```

#### 2. Close Position (Reverse the Synthetic)

**To close a synthetic long future, REVERSE both legs:**

**Leg 1: BUY BACK the PUT** (you originally sold it)
- Symbol: BANKNIFTY25NOV2750000PE
- Action: BUY
- Quantity: 180
- Order Type: MARKET

**Leg 2: SELL the CALL** (you originally bought it)
- Symbol: BANKNIFTY25NOV2750000CE
- Action: SELL
- Quantity: 180
- Order Type: MARKET

#### 3. Execute Exit

**In Stoxxo:**
1. Select the position (Long_1)
2. Click **"Square Off"** or **"Exit Position"**
3. Confirm exit for both legs
4. Click **"Execute"**

#### 4. Calculate Realized P&L

**Example fills:**
- PE buy back: ₹10 (you receive PE value - you sold at 152.50, buy back at 10 = profit 142.50)
- CE sell: ₹5 (you pay CE value - you bought at 98.75, sell at 5 = loss 93.75)

**Net P&L per lot:**
```
PE profit: (152.50 - 10) = 142.50
CE loss: (98.75 - 5) = -93.75
Net per lot: 142.50 - 93.75 = 48.75 points

Total P&L: 48.75 × 12 lots × 15 = ₹8,775
```

Wait, this doesn't match the alert (₹-72,000). Let me recalculate:

**Actually, for synthetic futures, P&L = (Exit price - Entry price) × Lots × Lot size**

```
Entry: 49,946 (from earlier)
Exit: 49,600 (from alert)
P&L: (49,600 - 49,946) × 12 × 15 = -346 × 180 = ₹-62,280
```

The alert showed -₹72,000 (theoretical from signal price 50,000), actual is -₹62,280 (better due to favorable entry slippage).

#### 5. Log Exit

| Date | Time | Signal Type | Signal Price | Actual Fill | Slippage | Lots | Actual P&L | Theoretical P&L | Divergence | Notes |
|------|------|-------------|--------------|-------------|----------|------|------------|-----------------|------------|-------|
| 2025-11-20 | 14:29 | EXIT | 49,600 | 49,575 | -25 | 12 | -62,280 | -72,000 | +9,720 | Tom Basso stop hit |

---

## Rollover Process (Monthly)

**When:** 5 days before expiry (last Wednesday of month)

**Scenario:** You have open positions in current month, need to roll to next month

### Step 1: Identify Positions to Roll

**Positions tab:**
```
Long_1: BANKNIFTY25NOV2750000PE/CE (expiring 27-NOV)
Long_2: BANKNIFTY25NOV2750800PE/CE (expiring 27-NOV)
```

### Step 2: Exit Current Month

Follow normal exit process (reverse both legs for each position).

### Step 3: Enter Next Month

**Next month expiry:** 25-DEC-2025 = `25DEC25`

**For each position:**
1. Calculate current ATM strike
2. Place synthetic future in **next month expiry**
3. Use same quantity as closed position

**Example:**
```
Close: BANKNIFTY25NOV2750000PE/CE (12 lots)
Open:  BANKNIFTY25DEC2551000PE/CE (12 lots at new ATM)
```

### Step 4: Log Rollover Cost

**Rollover cost** = Exit price (current month) - Entry price (next month)

Example:
```
Exit Nov: 50,500
Enter Dec: 50,600
Rollover cost: 100 points × 12 lots × 15 = ₹18,000
```

**In Google Sheets:**
| Date | Time | Signal Type | Signal Price | Actual Fill | Slippage | Lots | Actual P&L | Notes |
|------|------|-------------|--------------|-------------|----------|------|------------|-------|
| 2025-11-22 | 15:00 | ROLLOVER | 50,500 | 50,600 | 100 | 12 | -18,000 | Nov→Dec rollover |

---

## Common Errors & Solutions

### Error 1: "Insufficient Margin"

**Cause:** Not enough margin to place order

**Solutions:**
1. Check available margin in Stoxxo
2. Reduce lot size (if alert says 12 lots, try 10)
3. Close other positions to free margin
4. Add funds to broker account

### Error 2: "Symbol Not Found"

**Cause:** Incorrect symbol format or strike doesn't exist

**Solutions:**
1. Verify expiry date format (YYMONDD)
2. Check strike exists (only 100-point intervals for Bank Nifty)
3. Ensure using current month expiry (not expired month)

### Error 3: "Order Rejected - Outside Price Range"

**Cause:** Market order would exceed price band

**Solutions:**
1. Use LIMIT order instead of MARKET
2. Set limit price 1-2% away from LTP (Last Traded Price)
3. Wait a few seconds and retry

### Error 4: "Partial Fill"

**Cause:** Full quantity not available at market

**Solutions:**
1. Wait 10-30 seconds for remaining fill
2. If unfilled quantity >10%, consider canceling and re-entering
3. For illiquid strikes, use limit orders

### Error 5: "Position Mismatch"

**Cause:** Stoxxo shows position, but broker terminal doesn't (or vice versa)

**Solutions:**
1. Refresh Stoxxo (F5 or Click "Refresh")
2. Log out and log back in
3. Check broker terminal directly
4. Restart Stoxxo application

---

## Best Practices

### Timing

- ✅ Execute within 1-2 minutes of alert
- ✅ Avoid last 5 minutes of market (3:25-3:30 PM) - wide spreads
- ✅ Prefer 10:00 AM - 2:00 PM for best liquidity

### Order Types

- **Use MARKET orders** for base entries and exits (urgency matters)
- **Use LIMIT orders** for pyramids (can afford to wait for better price)

### Strike Selection

- **Always use ATM strikes** (At-The-Money)
- Avoid OTM (Out-of-Money) - lower margin but worse slippage
- Avoid ITM (In-The-Money) - better delta but higher margin

### Position Tracking

- **Verify positions after every execution** (Positions tab)
- **Screenshot Stoxxo order confirmations** (for records)
- **Update Google Sheets immediately** (don't wait till EOD)

### Risk Management

- **Never exceed planned lot size** (if alert says 12, don't do 15)
- **Always verify margin before placing** (don't rely on estimates)
- **Use stop-loss** as indicated in alerts (Tom Basso stops)

### Troubleshooting

- **Keep Stoxxo running during market hours** (9:15 AM - 3:30 PM)
- **Restart Stoxxo daily** (before market open) to avoid connection issues
- **Keep broker terminal open** as backup (in case Stoxxo fails)

---

## Emergency Procedures

### If Stoxxo Crashes During Execution

1. **Open broker terminal immediately**
2. Check if orders executed (Order Book)
3. If partially filled, complete manually via broker terminal
4. Restart Stoxxo once market action complete

### If Internet Connection Lost

1. **Use mobile data** (hotspot from phone)
2. Access broker's mobile app as backup
3. Don't panic - positions won't disappear
4. Document what happened in Google Sheets notes

### If Telegram Alert Missed (AFK)

1. **Don't chase the trade** after 5+ minutes
2. Check TradingView chart to see if signal still valid
3. If price moved >1% from signal price, skip
4. Wait for next signal

### If Wrong Strike Entered

1. **Exit immediately** if realized within 1 minute
2. Re-enter correct strike
3. Log both trades (mistake + correction) in Google Sheets
4. Learn from error - double-check before clicking "Execute"

---

## Transition to Phase 2 (Automation)

Once comfortable with manual execution (2-4 weeks), you can automate:

**Phase 2 will:**
- Receive webhook from TradingView
- Parse JSON signal
- Place orders via Stoxxo API automatically
- Log to database/CSV

**You'll still:**
- Monitor execution via Stoxxo
- Can intervene if needed (manual override)
- Review logs and performance

**See `PHASE2_AUTOMATION_SETUP.md` (coming next)**

---

## Support Resources

- **Stoxxo Support:** support@algobaba.com
- **Stoxxo Telegram:** @stoxxobridge
- **NSE Options Chain:** https://www.nseindia.com/option-chain
- **Bank Nifty Lot Size:** Currently 15 (verify on NSE)

---

**You're now ready to execute trades manually via Stoxxo! Practice with small sizes first, then scale up.**
