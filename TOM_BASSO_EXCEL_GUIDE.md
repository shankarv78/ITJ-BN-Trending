# Tom Basso Position Sizing - Excel Template Guide

## 📊 Overview

This guide provides Excel formulas to calculate Tom Basso position sizing based on TradingView signals. The template calculates all three constraints (Risk, Volatility, Margin) and determines the final position size.

---

## 📋 Excel Template Structure

### Sheet Layout

```
Column A: Labels
Column B: Bank Nifty Values
Column C: Gold Mini Values
Column D: Formulas/Calculations
```

---

## 🔧 Setup Instructions

### Step 1: Create Input Section (Rows 1-20)

**Row 1: Title**
```
A1: "TOM BASSO POSITION SIZER"
```

**Row 3: Portfolio Parameters**
```
A3: "PORTFOLIO PARAMETERS"
A4: "Current Equity (₹)"
A5: "Available Margin (₹)"
A6: "Initial Risk %"
A7: "Initial Volatility %"
A8: "Ongoing Risk %"
A9: "Ongoing Volatility %"
```

**Row 11: Instrument Parameters - Bank Nifty**
```
A11: "BANK NIFTY PARAMETERS"
A12: "Lot Size"
A13: "Point Value (₹ per point per lot)"
A14: "Margin per Lot (₹)"
```

**Row 16: Instrument Parameters - Gold Mini**
```
A16: "GOLD MINI PARAMETERS"
A17: "Lot Size"
A18: "Point Value (₹ per point per lot)"
A19: "Margin per Lot (₹)"
```

**Row 21: TradingView Signal Data**
```
A21: "TRADINGVIEW SIGNAL DATA"
A22: "Signal Type (BASE_ENTRY/PYRAMID)"
A23: "Instrument (BANK_NIFTY/GOLD_MINI)"
A24: "Entry Price"
A25: "Stop Price (SuperTrend)"
A26: "ATR (Average True Range)"
A27: "ER (Efficiency Ratio)"
A28: "Base Position Size (for pyramids)"
A29: "Profit After Base Risk (for pyramids)"
```

---

## 📐 Default Values

### Portfolio Parameters (Enter in Column B)
```
B4: 5000000    (₹50 lakhs)
B5: 3000000    (₹30 lakhs available margin)
B6: 0.5        (0.5% initial risk)
B7: 0.2        (0.2% initial volatility)
B8: 1.0        (1.0% ongoing risk)
B9: 0.5        (0.5% ongoing volatility)
```

### Bank Nifty Parameters (Enter in Column B)
```
B12: 30        (30 lots per contract)
B13: 30        (₹30 per point per lot)
B14: 270000    (₹2.7L per lot)
```

### Gold Mini Parameters (Enter in Column C)
```
C17: 100       (100 grams per contract)
C18: 10        (₹10 per point per lot)
C19: 105000    (₹1.05L per lot)
```

---

## 🧮 Formula Section (Rows 31-60)

### Row 31: Title
```
A31: "CALCULATIONS"
```

### Row 33: Signal Data Selection
```
A33: "Selected Instrument"
B33: =IF(B23="BANK_NIFTY","BANK_NIFTY",IF(B23="GOLD_MINI","GOLD_MINI",""))
```

### Row 35: Lot Size (Dynamic)
```
A35: "Lot Size"
B35: =IF(B33="BANK_NIFTY",B12,IF(B33="GOLD_MINI",C17,0))
```

### Row 36: Point Value (Dynamic)
```
A36: "Point Value"
B36: =IF(B33="BANK_NIFTY",B13,IF(B33="GOLD_MINI",C18,0))
```

### Row 37: Margin per Lot (Dynamic)
```
A37: "Margin per Lot"
B37: =IF(B33="BANK_NIFTY",B14,IF(B33="GOLD_MINI",C19,0))
```

### Row 39: Risk Calculation
```
A39: "CONSTRAINT 1: RISK-BASED (Lot-R)"
A40: "Risk Amount (₹)"
B40: =B4*B6/100
A41: "Risk per Point"
B41: =B24-B25
A42: "Risk per Lot (₹)"
B42: =B41*B36
A43: "Lot-R (Risk-based)"
B43: =IF(B42>0,(B40/B42)*B27,0)
```

### Row 45: Volatility Calculation
```
A45: "CONSTRAINT 2: VOLATILITY-BASED (Lot-V)"
A46: "Volatility Budget (₹)"
B46: =B4*B7/100
A47: "Volatility per Lot (₹)"
B47: =B26*B36
A48: "Lot-V (Volatility-based)"
B48: =IF(B47>0,B46/B47,0)
```

### Row 50: Margin Calculation
```
A50: "CONSTRAINT 3: MARGIN-BASED (Lot-M)"
A51: "Lot-M (Margin-based)"
B51: =IF(B37>0,B5/B37,0)
```

### Row 53: Final Position Size
```
A53: "FINAL POSITION SIZE"
A54: "Minimum Constraint"
B54: =MIN(B43,B48,B51)
A55: "Final Lots (FLOOR)"
B55: =FLOOR(B54,1)
A56: "Limiting Factor"
B56: =IF(B55=0,"INVALID",IF(B54=B43,"RISK",IF(B54=B48,"VOLATILITY","MARGIN")))
```

### Row 58: Risk Metrics
```
A58: "RISK METRICS"
A59: "Risk per Trade (₹)"
B59: =B55*B42
A60: "Risk % of Equity"
B60: =IF(B4>0,(B59/B4)*100,0)
A61: "Volatility per Trade (₹)"
B61: =B55*B47
A62: "Volatility % of Equity"
B62: =IF(B4>0,(B61/B4)*100,0)
A63: "Margin Used (₹)"
B63: =B55*B37
A64: "Margin % of Available"
B64: =IF(B5>0,(B63/B5)*100,0)
```

---

## 🔄 Pyramid Entry Formulas (Additional Section)

### Row 66: Pyramid Calculations
```
A66: "PYRAMID ENTRY (if signal_type = PYRAMID)"
A67: "Constraint A: Margin Safety"
B67: =FLOOR(B5/B37,1)
A68: "Constraint B: 50% of Base"
B68: =FLOOR(B28*0.5,1)
A69: "Constraint C: Risk Budget (50% of profit)"
B69: =IF(B41>0,FLOOR((B29*0.5)/(B41*B36),1),0)
A70: "Pyramid Final Lots"
B70: =FLOOR(MIN(B67,B68,B69),1)
A71: "Pyramid Limiter"
B71: =IF(B70=0,"INVALID",IF(MIN(B67,B68,B69)=B67,"MARGIN",IF(MIN(B67,B68,B69)=B68,"50%_RULE","RISK_BUDGET")))
```

---

## 📝 Usage Instructions

### For BASE_ENTRY Signals:

1. **Enter Portfolio Data:**
   - Current Equity (B4)
   - Available Margin (B5)
   - Risk % (B6)
   - Volatility % (B7)

2. **Enter TradingView Signal:**
   - Signal Type: "BASE_ENTRY" (B22)
   - Instrument: "BANK_NIFTY" or "GOLD_MINI" (B23)
   - Entry Price (B24)
   - Stop Price (B25)
   - ATR (B26)
   - ER (B27)

3. **Read Results:**
   - Final Lots (B55)
   - Limiting Factor (B56)
   - Risk Metrics (B59-B64)

### For PYRAMID Signals:

1. **Enter all BASE_ENTRY data above**

2. **Additional Pyramid Data:**
   - Signal Type: "PYRAMID" (B22)
   - Base Position Size (B28)
   - Profit After Base Risk (B29)

3. **Read Pyramid Results:**
   - Pyramid Final Lots (B70)
   - Pyramid Limiter (B71)

---

## 🎯 Example Calculations

### Example 1: Bank Nifty BASE_ENTRY

**Input:**
- Equity: ₹50,00,000
- Entry: 52,000
- Stop: 51,650
- ATR: 350
- ER: 0.82

**Expected Results:**
- Lot-R: 1.67 lots
- Lot-V: 0.82 lots
- Lot-M: 11.11 lots
- **Final: 0 lots (limited by VOLATILITY)**

### Example 2: Gold Mini BASE_ENTRY

**Input:**
- Equity: ₹50,00,000
- Entry: 78,500
- Stop: 77,800
- ATR: 450
- ER: 0.85

**Expected Results:**
- Lot-R: 3.04 lots
- Lot-V: 2.22 lots
- Lot-M: 28.57 lots
- **Final: 2 lots (limited by VOLATILITY)**

---

## 📊 Data Extraction from TradingView

### From BASE_ENTRY Alert JSON:

```json
{
  "type": "BASE_ENTRY",
  "instrument": "BANK_NIFTY",
  "price": 52000,
  "stop": 51650,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650
}
```

**Map to Excel:**
- `price` → B24 (Entry Price)
- `stop` → B25 (Stop Price)
- `atr` → B26 (ATR)
- `er` → B27 (ER)
- `instrument` → B23 (Instrument)

### From PYRAMID Alert JSON:

```json
{
  "type": "PYRAMID",
  "instrument": "BANK_NIFTY",
  "price": 52500,
  "stop": 52000,
  "atr": 380,
  "er": 0.88,
  "base_position_size": 1,
  "profit_after_base_risk": 50000
}
```

**Map to Excel:**
- All BASE_ENTRY fields above
- `base_position_size` → B28
- `profit_after_base_risk` → B29 (calculate from your portfolio)

---

## ⚠️ Important Notes

1. **Equity Updates:** Update B4 (Current Equity) after each trade to reflect realized P&L

2. **Margin Updates:** Update B5 (Available Margin) after each position to reflect margin used

3. **ER Calculation:** ER (Efficiency Ratio) is sent by TradingView. If not available, use 0.8 as default

4. **Stop Price:** Always use SuperTrend value for stop loss calculation

5. **ATR:** Use the ATR value from TradingView (typically ATR used for pyramiding)

6. **Validation:**
   - Ensure Entry Price > Stop Price (for long positions)
   - Ensure ATR > 0
   - Ensure ER between 0 and 1

---

## 🔍 Troubleshooting

### Issue: Final Lots = 0

**Possible Causes:**
1. **Volatility Limited:** Lot-V is too small (< 1)
   - Solution: Increase equity or reduce volatility %
   
2. **Risk Limited:** Lot-R is too small (< 1)
   - Solution: Increase equity or reduce risk %
   
3. **Invalid Risk:** Stop Price >= Entry Price
   - Solution: Check TradingView signal data

### Issue: Wrong Instrument Parameters

**Solution:** Verify B23 (Instrument) matches the signal instrument. The formulas automatically select Bank Nifty or Gold Mini parameters.

### Issue: Margin Limited

**Solution:** 
- Increase available margin (B5)
- Or reduce position size manually
- Or close other positions to free margin

---

## 📈 Advanced: Multi-Instrument Tracking

Create separate sheets for:
- **Sheet 1:** Bank Nifty Calculator
- **Sheet 2:** Gold Mini Calculator
- **Sheet 3:** Portfolio Summary (combines both)

**Portfolio Summary Formulas:**
```
Total Margin Used = SUM(BankNifty!B63, GoldMini!B63)
Total Risk = SUM(BankNifty!B59, GoldMini!B59)
Total Equity = BankNifty!B4  (shared equity)
```

---

## 🎓 Understanding the Constraints

### Lot-R (Risk-Based)
- **Purpose:** Limit risk per trade to X% of equity
- **Formula:** `(Equity × Risk%) / (Entry-Stop × PointValue) × ER`
- **Why ER?** Scales position based on trend strength

### Lot-V (Volatility-Based)
- **Purpose:** Limit volatility exposure to X% of equity
- **Formula:** `(Equity × Vol%) / (ATR × PointValue)`
- **Why ATR?** Measures market volatility

### Lot-M (Margin-Based)
- **Purpose:** Don't exceed available margin
- **Formula:** `Available Margin / Margin Per Lot`
- **Why?** Prevents over-leveraging

### Final Position
- **Formula:** `FLOOR(MIN(Lot-R, Lot-V, Lot-M))`
- **Why MIN?** Most conservative constraint wins
- **Why FLOOR?** Can't trade fractional lots

---

## 📞 Quick Reference

**Key Cells:**
- B4: Current Equity
- B24: Entry Price
- B25: Stop Price
- B26: ATR
- B27: ER
- **B55: FINAL LOTS** ← **This is your answer!**
- B56: Limiting Factor

**Copy these formulas into Excel and you're ready to go!**

---

**Last Updated:** December 2, 2025
**Version:** 1.0

