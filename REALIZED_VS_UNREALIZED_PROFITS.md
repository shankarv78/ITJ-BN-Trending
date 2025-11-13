# Realized vs Unrealized Profits - Critical Fix

## Issue Identified ✅

The original implementation had a **critical flaw** that would cause position sizing based on **unrealized (paper) profits** instead of **realized (locked-in) profits**.

---

## The Problem (BEFORE)

### Original Code (WRONG):
```pinescript
current_equity = strategy.equity  // ❌ Includes unrealized P&L
if current_equity > equity_high
    equity_high := current_equity
```

### What `strategy.equity` includes:
```
strategy.equity = Initial Capital
                + Unrealized P&L (open positions - paper profits) ❌
                + Realized P&L (closed trades - locked profits) ✅
```

### Why This Was Dangerous:

**Example Scenario:**
```
Starting Capital: ₹1,00,00,000
Equity High: ₹1,00,00,000

Trade 1 Entry: Buy 10 lots at 58,000
Price moves to 60,000 (open position)

Unrealized Profit: +₹70,00,000 (huge paper profit!)
strategy.equity = ₹1,70,00,000

❌ BAD: equity_high updates to ₹1,70,00,000

Next Entry:
Risk = 2% of ₹1.7 Cr = ₹3,40,000
Lots calculated = 15 lots (based on inflated equity!)

Then price reverses:
Trade 1 exits at 57,000 (loss!)
Realized Loss: -₹35,00,000
Actual Equity: ₹65,00,000

But equity_high is still ₹1.7 Cr!
Next trade still risks ₹3.4L based on profits that never materialized!
```

**Result**: You'd be over-sizing positions based on paper profits that disappeared.

---

## The Solution (AFTER)

### Fixed Code (CORRECT):
```pinescript
// Use ONLY realized profits from closed trades
realized_equity = strategy.initial_capital + strategy.netprofit
if realized_equity > equity_high
    equity_high := realized_equity

// Track current equity separately for display
current_equity = strategy.equity
```

### What `strategy.netprofit` includes:
```
strategy.netprofit = Total realized P&L from ALL closed trades ONLY
```

### How It Works Now:

**Same Scenario:**
```
Starting Capital: ₹1,00,00,000
Equity High: ₹1,00,00,000

Trade 1 Entry: Buy 10 lots at 58,000
Price moves to 60,000 (open position)

Unrealized Profit: +₹70,00,000
strategy.equity = ₹1,70,00,000  (shown in table)
strategy.netprofit = 0  (no closed trades yet)

✅ GOOD: realized_equity = ₹1,00,00,000 + 0 = ₹1,00,00,000
✅ GOOD: equity_high stays at ₹1,00,00,000

Next Entry (if signal occurs):
Risk = 2% of ₹1.0 Cr = ₹2,00,000
Lots calculated = 9 lots (conservative, based on actual capital)

Price reverses and exits at 57,000:
Realized Loss: -₹35,00,000
strategy.netprofit = -₹35,00,000
realized_equity = ₹1,00,00,000 - ₹35,00,000 = ₹65,00,000

✅ GOOD: equity_high stays at ₹1,00,00,000 (capital preservation during drawdown)

Next Entry:
Risk = 2% of ₹1.0 Cr = ₹2,00,000 (same as initial)
Lots = Conservative sizing maintained
```

**Result**: Position sizing remains disciplined, based only on realized profits.

---

## When Equity High DOES Increase

**Winning Trade Example:**
```
Starting: equity_high = ₹1,00,00,000

Trade 1: Buy at 58,000, Exit at 61,000
Realized Profit: +₹1,05,00,000
strategy.netprofit = +₹1,05,00,000

realized_equity = ₹1,00,00,000 + ₹1,05,00,000 = ₹2,05,00,000

✅ equity_high updates to ₹2,05,00,000 (profit locked in!)

Next Entry:
Risk = 2% of ₹2.05 Cr = ₹4,10,000
Lots = Increased sizing (compounding locked-in gains!)
```

**Key Point**: Equity high only increases when you **close a trade at a profit** and lock in those gains.

---

## Info Table Display

The updated table now clearly separates:

| Row | Field | Value | Formula | Purpose |
|-----|-------|-------|---------|---------|
| 10 | **Capital** | ₹1 Cr | Fixed | Starting point |
| 11 | **Current Equity** | Live | strategy.equity | Includes unrealized P&L (for info only) |
| 12 | **Realized Equity** | Live | initial_capital + netprofit | Only closed trades |
| 13 | **Equity High** | Peak | Peak of realized_equity | High watermark (for risk calc) |
| 14 | **Risk Amount** | 2% of peak | equity_high × 2% | Risk for next trade |
| 15 | **Lot Size** | Calculated | Formula-based | Position size preview |

**Color Coding:**
- 🔵 Blue = Initial Capital
- ⚫ Gray = Current Equity (includes unrealized - informational)
- 🟢 Green = Realized Equity (closed trades only - what matters!)
- 🔵 Teal = Equity High (peak realized - used for sizing!)
- 🟠 Orange = Risk Amount
- 🟣 Purple = Lot Size

---

## Comparison Example

### Scenario: Winning Trade Followed by Open Losing Position

| State | Current Equity | Realized Equity | Equity High | Risk | Lots |
|-------|---------------|-----------------|-------------|------|------|
| **Start** | ₹1.00 Cr | ₹1.00 Cr | ₹1.00 Cr | ₹2.00 L | 7 |
| **Trade 1 Open (+₹50L)** | ₹1.50 Cr | ₹1.00 Cr | ₹1.00 Cr | ₹2.00 L | 7 |
| **Trade 1 Closed (+₹50L)** | ₹1.50 Cr | ₹1.50 Cr | ₹1.50 Cr | ₹3.00 L | 10 |
| **Trade 2 Open (-₹20L)** | ₹1.30 Cr | ₹1.50 Cr | ₹1.50 Cr | ₹3.00 L | 10 |
| **Trade 2 Closed (-₹20L)** | ₹1.30 Cr | ₹1.30 Cr | ₹1.50 Cr | ₹3.00 L | 10 |

**Key Insights:**
1. While Trade 1 is open with +₹50L paper profit:
   - Current Equity shows ₹1.5 Cr (includes unrealized)
   - Realized Equity stays ₹1.0 Cr (trade not closed)
   - Equity High stays ₹1.0 Cr (no change in sizing) ✅

2. After Trade 1 closes with +₹50L realized profit:
   - Realized Equity jumps to ₹1.5 Cr
   - Equity High updates to ₹1.5 Cr
   - Next trade risks ₹3L (increased sizing) ✅

3. While Trade 2 is open with -₹20L paper loss:
   - Current Equity shows ₹1.3 Cr (includes unrealized)
   - Realized Equity stays ₹1.5 Cr (trade not closed)
   - Equity High stays ₹1.5 Cr (sizing maintained) ✅

4. After Trade 2 closes with -₹20L realized loss:
   - Realized Equity drops to ₹1.3 Cr
   - Equity High stays ₹1.5 Cr (capital preservation)
   - Next trade still risks ₹3L (sizing maintained) ✅

---

## Why This Matters

### Without This Fix (Using strategy.equity):
```
Win streak with open positions:
  Paper profits inflate equity_high
  Position sizes grow aggressively
  If positions reverse and close at losses
  → Over-sized trades with deflated capital
  → Potential blowup risk
```

### With This Fix (Using strategy.netprofit):
```
Win streak:
  Only closed winning trades increase equity_high
  Position sizes grow conservatively
  Open positions can fluctuate
  → Sizing based on locked-in gains only
  → Sustainable growth, lower risk
```

---

## Technical Implementation

### Key Pine Script Variables:

```pinescript
strategy.initial_capital  // Fixed: ₹1,00,00,000
strategy.equity          // Dynamic: Initial + Unrealized P&L + Realized P&L
strategy.netprofit       // Dynamic: Total realized P&L only
strategy.openprofit      // Dynamic: Unrealized P&L of open positions
strategy.closedtrades    // Counter: Number of closed trades
```

### Our Formula:

```pinescript
// Realized equity = What you'd have if you closed everything now at market
// But we only count profits that are ALREADY closed
realized_equity = strategy.initial_capital + strategy.netprofit

// Equity high = Peak of realized equity (ratchets up only)
if realized_equity > equity_high
    equity_high := realized_equity

// Risk = Based on peak REALIZED equity
risk_amount = equity_high × 0.02
```

---

## Summary

✅ **BEFORE FIX**: equity_high could increase based on unrealized paper profits
✅ **AFTER FIX**: equity_high only increases when trades close at profit

✅ **BEFORE FIX**: Position sizing could be based on profits that never materialized
✅ **AFTER FIX**: Position sizing based only on locked-in realized gains

✅ **BEFORE FIX**: Risk of over-sizing after lucky paper profits reverse
✅ **AFTER FIX**: Conservative, sustainable growth based on actual performance

This is the **correct, professional way** to implement equity tracking and compounding in trading strategies.

---

**Critical Takeaway**:
Never let unrealized profits influence your position sizing. Only compound on realized, locked-in gains.

**Status**: ✅ Fixed in Version 4.1

**Last Updated**: 2025-11-10
