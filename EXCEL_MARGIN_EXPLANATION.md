# Available Margin Calculation - Excel Template

## ❓ Why ₹30,00,000 in the Template?

The ₹30,00,000 (3 million) in the template is **just an example**. It assumes:
- You have ₹50,00,000 equity
- You already have some positions open using ₹20,00,000 margin
- Available margin = ₹50,00,000 - ₹20,00,000 = ₹30,00,000

**This is NOT a fixed value!** You must update it based on your actual portfolio.

---

## 📊 How to Calculate Available Margin

### Formula:

```
Available Margin = Total Equity - Margin Used by Existing Positions
```

### Step-by-Step Calculation:

#### 1. **Get Your Total Equity**
- Check your broker account balance
- Or: Initial Capital + Realized P&L + Unrealized P&L
- Enter this in **Cell B4** (Current Equity)

#### 2. **Calculate Margin Used by Existing Positions**

**For Bank Nifty:**
```
Margin Used = Number of Lots × ₹2,70,000 per lot
```

**For Gold Mini:**
```
Margin Used = Number of Lots × ₹1,05,000 per lot
```

**Example:**
- 2 lots Bank Nifty = 2 × ₹2,70,000 = ₹5,40,000
- 1 lot Gold Mini = 1 × ₹1,05,000 = ₹1,05,000
- **Total Margin Used = ₹6,45,000**

#### 3. **Calculate Available Margin**

```
Available Margin = ₹50,00,000 - ₹6,45,000 = ₹43,55,000
```

Enter this in **Cell B5** (Available Margin)

---

## 🎯 Example Scenarios

### Scenario 1: Fresh Start (No Positions)

**If you have no open positions:**
- Current Equity: ₹50,00,000
- Margin Used: ₹0
- **Available Margin: ₹50,00,000** (or slightly less for safety buffer)

**Set B5 = ₹50,00,000** (or ₹48,00,000 for 4% safety buffer)

---

### Scenario 2: With Existing Positions

**Current Portfolio:**
- Current Equity: ₹52,00,000 (gained ₹2L from profits)
- 1 lot Bank Nifty open = ₹2,70,000 margin
- 2 lots Gold Mini open = ₹2,10,000 margin
- Total Margin Used = ₹4,80,000

**Available Margin:**
```
₹52,00,000 - ₹4,80,000 = ₹47,20,000
```

**Set B5 = ₹47,20,000**

---

### Scenario 3: Conservative Approach

**If you want to keep a safety buffer:**
- Current Equity: ₹50,00,000
- Margin Used: ₹0
- Safety Buffer: 10% = ₹5,00,000
- **Available Margin: ₹45,00,000**

**Set B5 = ₹45,00,000**

---

## 🔄 How to Update After Each Trade

### After Opening a Position:

1. **Calculate new margin used:**
   ```
   New Margin Used = Old Margin Used + (Lots × Margin per Lot)
   ```

2. **Update Cell B5:**
   ```
   New Available Margin = Current Equity - New Margin Used
   ```

**Example:**
- Before: Available Margin = ₹50,00,000
- Opened: 1 lot Bank Nifty (₹2,70,000 margin)
- After: Available Margin = ₹50,00,000 - ₹2,70,000 = ₹47,30,000
- **Update B5 to ₹47,30,000**

### After Closing a Position:

1. **Calculate new margin used:**
   ```
   New Margin Used = Old Margin Used - (Lots × Margin per Lot)
   ```

2. **Update Cell B5:**
   ```
   New Available Margin = Current Equity - New Margin Used
   ```

**Example:**
- Before: Available Margin = ₹47,30,000
- Closed: 1 lot Bank Nifty (₹2,70,000 margin freed)
- After: Available Margin = ₹47,30,000 + ₹2,70,000 = ₹50,00,000
- **Update B5 to ₹50,00,000**

---

## 📝 Quick Reference Table

| Equity | Positions | Margin Used | Available Margin |
|--------|-----------|-------------|------------------|
| ₹50L | None | ₹0 | ₹50L |
| ₹50L | 1 BN lot | ₹2.7L | ₹47.3L |
| ₹50L | 2 BN lots | ₹5.4L | ₹44.6L |
| ₹50L | 1 GM lot | ₹1.05L | ₹48.95L |
| ₹50L | 1 BN + 1 GM | ₹3.75L | ₹46.25L |
| ₹52L | 1 BN lot | ₹2.7L | ₹49.3L |

**BN = Bank Nifty, GM = Gold Mini**

---

## ⚠️ Important Notes

1. **Update B5 Before Each New Trade:**
   - Check your broker account
   - Calculate margin used by all open positions
   - Update B5 = B4 - Total Margin Used

2. **Don't Use 100% of Equity:**
   - Keep 5-10% buffer for safety
   - Prevents margin calls
   - Allows for price movements

3. **Margin Requirements Can Change:**
   - Broker may increase margin during volatility
   - Check broker margin calculator
   - Use conservative estimates (₹2.7L for BN, ₹1.05L for GM)

4. **Equity Changes Daily:**
   - Update B4 (Current Equity) after each trade
   - Include realized P&L
   - Include unrealized P&L if you want to be precise

---

## 🧮 Excel Formula to Auto-Calculate (Optional)

If you want Excel to calculate available margin automatically, you can add:

**Cell A56:** "Margin Used by Positions"
**Cell B56:** Enter manually: `=SUM(BankNiftyLots*270000, GoldMiniLots*105000)`

**Cell A57:** "Available Margin (Auto)"
**Cell B57:** `=B4-B56`

Then use **B57** instead of B5 in your formulas.

**Note:** This requires you to track lots separately, which might be more complex than just updating B5 manually.

---

## ✅ Recommended Workflow

1. **Before Each Trade:**
   - Check broker account for current equity → Update B4
   - Count open positions and calculate margin used
   - Calculate available margin → Update B5
   - Enter TradingView signal data
   - Read B54 (Final Lots)

2. **After Each Trade:**
   - Update B4 (equity changed by P&L)
   - Update B5 (margin changed by new position)

3. **Daily:**
   - Update B4 with current equity (includes unrealized P&L)
   - Recalculate B5 based on open positions

---

## 🎯 Summary

**The ₹30,00,000 in the template is just an example!**

**Your actual available margin should be:**
```
Available Margin = Your Current Equity - Margin Used by Your Open Positions
```

**Update Cell B5 with your actual available margin before calculating position sizes.**

---

**Last Updated:** December 2, 2025

