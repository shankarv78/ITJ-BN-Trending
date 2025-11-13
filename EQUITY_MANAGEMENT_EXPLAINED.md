# Equity Management & Compounding Strategy

## Overview

The strategy now implements **proper equity management with compounding**, where:
1. Profits accumulate into the capital base
2. Position sizes grow as equity grows (compounding gains)
3. Risk is calculated from equity high watermark (capital preservation during drawdowns)

---

## How It Works

### 1. Equity Tracking (Lines 122-128)

```pinescript
var float equity_high = strategy.initial_capital  // Track highest equity reached

// Update equity high watermark every bar
current_equity = strategy.equity
if current_equity > equity_high
    equity_high := current_equity
```

**Key Variables:**
- `strategy.equity` = Current account value (initial capital + unrealized P&L + realized P&L)
- `equity_high` = Highest equity ever reached (high watermark)
- `strategy.initial_capital` = Starting capital (₹1 Crore)

### 2. Risk Calculation (Line 134)

```pinescript
risk_amount = equity_high * (risk_percent / 100)
```

**Why use equity_high instead of current_equity?**

This is a **capital preservation rule**:
- During **profit runs**: equity_high increases → position sizes grow ✅
- During **drawdowns**: equity_high stays constant → position sizes don't shrink ❌

**Example Scenarios:**

#### Scenario A: Profitable Trade (Compounding)
```
Initial Capital: ₹1,00,00,000
After Trade 1 Profit (+₹10L):
  - Current Equity: ₹1,10,00,000
  - Equity High: ₹1,10,00,000 (updated)
  - Risk on Next Trade: 2% of ₹1.1Cr = ₹2,20,000 (increased!)
```

#### Scenario B: Losing Trade (Capital Preservation)
```
After Trade 2 Loss (-₹5L):
  - Current Equity: ₹1,05,00,000
  - Equity High: ₹1,10,00,000 (unchanged - still at peak)
  - Risk on Next Trade: 2% of ₹1.1Cr = ₹2,20,000 (same as before)
```

**Result**: You don't "de-risk" after a loss. You maintain position sizing based on your peak equity.

---

## Position Sizing Formula

### Complete Formula:
```
Lots = (Risk ÷ ((Entry - SuperTrend) × Lot_Size)) × ER

Where:
- Risk = equity_high × 2%
- Entry = Close price
- SuperTrend = Stop loss level
- Lot_Size = 35
- ER = Efficiency Ratio (trend strength)
```

### Code Implementation (Lines 134-153):
```pinescript
// 1. Risk = 2% of equity high
risk_amount = equity_high * 0.02

// 2. Risk per lot
risk_per_point = entry_price - stop_loss
risk_per_lot = risk_per_point × 35

// 3. Calculate lots
num_lots = (risk_amount / risk_per_lot) × ER
final_lots = max(1, round(num_lots))
```

---

## Practical Examples

### Example 1: First Trade (Initial Capital)

**Starting State:**
- Initial Capital: ₹1,00,00,000
- Equity High: ₹1,00,00,000
- Risk: 2% = ₹2,00,000

**Entry Signal:**
- Entry Price: 58,500
- SuperTrend: 57,850
- ER: 0.8

**Calculation:**
```
Risk per point = 58,500 - 57,850 = 650
Risk per lot = 650 × 35 = 22,750
Base lots = 200,000 / 22,750 = 8.79
Final lots = 8.79 × 0.8 = 7.03 ≈ 7 lots
```

**Position Value:** 7 lots × 58,500 × 35 = ₹1,43,32,500

---

### Example 2: After Profitable Run (Compounding)

**After 5 winning trades:**
- Initial Capital: ₹1,00,00,000
- Current Equity: ₹1,30,00,000 (+30% profit)
- Equity High: ₹1,30,00,000
- Risk: 2% = ₹2,60,000 (increased!)

**Entry Signal (same as before):**
- Entry Price: 58,500
- SuperTrend: 57,850
- ER: 0.8

**Calculation:**
```
Risk per point = 650
Risk per lot = 22,750
Base lots = 260,000 / 22,750 = 11.43
Final lots = 11.43 × 0.8 = 9.14 ≈ 9 lots
```

**Result:** Position size grew from 7 → 9 lots (30% increase, matching equity growth)

---

### Example 3: After Drawdown (Capital Preservation)

**After a losing streak:**
- Initial Capital: ₹1,00,00,000
- Current Equity: ₹1,15,00,000 (down from ₹1.3Cr peak)
- Equity High: ₹1,30,00,000 (stays at peak)
- Risk: 2% of ₹1.3Cr = ₹2,60,000 (unchanged!)

**Entry Signal:**
- Same as Example 2

**Calculation:**
```
Final lots = 9 lots (same as Example 2)
```

**Result:** Position size doesn't shrink during drawdown. You maintain sizing based on peak equity.

---

## Benefits of This Approach

### 1. **Compounding Gains** 📈
As you make profits, equity grows, and position sizes increase proportionally.

**Growth Example:**
```
Start:    ₹1.0 Cr → 7 lots
+10%:     ₹1.1 Cr → 8 lots
+20%:     ₹1.2 Cr → 8 lots
+30%:     ₹1.3 Cr → 9 lots
```

### 2. **Capital Preservation** 🛡️
During drawdowns, you don't reduce position sizes, preventing "death spiral" where losses compound.

**Without this logic (wrong approach):**
```
Peak:     ₹1.3 Cr → 9 lots
-10% DD:  ₹1.17 Cr → 8 lots (reduced!)
-20% DD:  ₹1.04 Cr → 7 lots (reduced again!)
```
Harder to recover as position sizes shrink.

**With equity high (correct approach):**
```
Peak:     ₹1.3 Cr → 9 lots
-10% DD:  ₹1.17 Cr → 9 lots (maintained!)
-20% DD:  ₹1.04 Cr → 9 lots (maintained!)
```
Same position size helps you recover faster.

### 3. **Consistent Risk Management** ⚖️
Every trade risks the same percentage (2%) of your peak equity.

---

## Info Table Display

The strategy now shows 5 equity-related rows:

| Row | Field | Formula | Purpose |
|-----|-------|---------|---------|
| 10 | Capital | Fixed ₹1 Cr | Initial starting capital |
| 11 | Current Equity | strategy.equity | Current account value (with P&L) |
| 12 | Equity High | equity_high | Peak equity reached |
| 13 | Risk Amount | equity_high × 2% | Risk for next trade |
| 14 | Lot Size | Calculated | Lots if entry happens now |

**Color Coding:**
- 🔵 Blue = Initial Capital (reference)
- 🟢 Green = Current Equity (real-time P&L)
- 🔵 Teal = Equity High (peak tracker)
- 🟠 Orange = Risk Amount (derived from equity high)
- 🟣 Purple = Lot Size (position preview)

---

## Visual Example Over Time

```
Time    Equity      Equity High    Risk        Lots
-----   ---------   -----------    --------    ----
T0      1.00 Cr     1.00 Cr        2.00 L      7
T1      1.05 Cr     1.05 Cr        2.10 L      7
T2      1.15 Cr     1.15 Cr        2.30 L      8
T3      1.10 Cr     1.15 Cr        2.30 L      8  ← Drawdown, but risk unchanged
T4      1.20 Cr     1.20 Cr        2.40 L      8
T5      1.35 Cr     1.35 Cr        2.70 L      9  ← New high, increased lots
```

**Key Observations:**
- At T3, equity dropped but equity high (and risk) stayed at 1.15 Cr
- Position sizes only increase when NEW equity highs are made
- This creates a "ratchet effect" - gains compound, losses don't de-compound

---

## Important Notes

### Strategy.equity vs Strategy.initial_capital

**strategy.initial_capital:**
- Fixed value (₹1 Crore)
- Never changes
- Starting point only

**strategy.equity:**
- Dynamic value
- Updates with every trade
- Includes unrealized P&L (open positions)
- Includes realized P&L (closed positions)

**equity_high:**
- Custom tracked variable
- Ratchets up only (never decreases)
- Used for risk calculation

### Edge Cases

**What if first trade is a big winner?**
```
Entry: equity_high = 1.00 Cr → 7 lots
Exit with +40% profit: equity = 1.40 Cr
Next Entry: equity_high = 1.40 Cr → 10 lots ✅
```
Position sizes immediately scale up.

**What if first trade is a big loser?**
```
Entry: equity_high = 1.00 Cr → 7 lots
Exit with -15% loss: equity = 0.85 Cr
Next Entry: equity_high = 1.00 Cr → 7 lots ✅
```
Position sizes stay the same (capital preservation).

**What if there's a huge drawdown from peak?**
```
Peak: equity_high = 2.00 Cr
Current: equity = 1.50 Cr (-25% drawdown)
Next Entry Risk: 2% of 2.00 Cr = 4.00 L
```
You're still risking based on the 2 Cr peak, which might be aggressive if you're in a 25% drawdown.

**Mitigation:** You could add a "max drawdown reset" rule, but this is the standard high watermark approach used in hedge funds.

---

## Summary

✅ **Profits compound** - As equity grows, position sizes grow
✅ **Capital preserved** - During drawdowns, position sizes maintained
✅ **Risk controlled** - Always 2% of peak equity
✅ **Transparent tracking** - Info table shows all equity metrics
✅ **Standard approach** - High watermark method used by professionals

This ensures the strategy **gets more aggressive as it wins** and **doesn't become timid after losses**.

---

**Last Updated:** 2025-11-10
**Version:** 4.0 (Equity Management + Compounding)
