# Excel Quick Start - Tom Basso Position Sizer

## 🚀 5-Minute Setup

### Step 1: Open Excel
Create a new workbook or open the CSV file provided.

### Step 2: Set Up Input Cells

**Column A = Labels, Column B = Values**

| Cell | Label | Value |
|------|-------|-------|
| B4 | Current Equity | 5000000 |
| B5 | Available Margin | 3000000 |
| B6 | Initial Risk % | 0.5 |
| B7 | Initial Volatility % | 0.2 |
| B12 | Bank Nifty Lot Size | 30 |
| B13 | Bank Nifty Point Value | 30 |
| B14 | Bank Nifty Margin/Lot | 270000 |
| C17 | Gold Mini Lot Size | 100 |
| C18 | Gold Mini Point Value | 10 |
| C19 | Gold Mini Margin/Lot | 105000 |

### Step 3: TradingView Signal Input

When you get a signal from TradingView, enter:

| Cell | What to Enter | Example |
|------|---------------|---------|
| B22 | Signal Type | BASE_ENTRY |
| B23 | Instrument | BANK_NIFTY |
| B24 | Entry Price | 52000 |
| B25 | Stop Price | 51650 |
| B26 | ATR | 350 |
| B27 | ER | 0.82 |

### Step 4: Copy These Formulas

**Cell B33 (Selected Instrument):**
```
=IF(B23="BANK_NIFTY","BANK_NIFTY",IF(B23="GOLD_MINI","GOLD_MINI",""))
```

**Cell B35 (Lot Size - Dynamic):**
```
=IF(B33="BANK_NIFTY",B12,IF(B33="GOLD_MINI",C17,0))
```

**Cell B36 (Point Value - Dynamic):**
```
=IF(B33="BANK_NIFTY",B13,IF(B33="GOLD_MINI",C18,0))
```

**Cell B37 (Margin per Lot - Dynamic):**
```
=IF(B33="BANK_NIFTY",B14,IF(B33="GOLD_MINI",C19,0))
```

**Cell B40 (Risk Amount):**
```
=B4*B6/100
```

**Cell B41 (Risk per Point):**
```
=B24-B25
```

**Cell B42 (Risk per Lot):**
```
=B41*B36
```

**Cell B43 (Lot-R):**
```
=IF(B42>0,(B40/B42)*B27,0)
```

**Cell B46 (Volatility Budget):**
```
=B4*B7/100
```

**Cell B47 (Volatility per Lot):**
```
=B26*B36
```

**Cell B48 (Lot-V):**
```
=IF(B47>0,B46/B47,0)
```

**Cell B51 (Lot-M):**
```
=IF(B37>0,B5/B37,0)
```

**Cell B54 (Minimum Constraint):**
```
=MIN(B43,B48,B51)
```

**Cell B55 (FINAL LOTS - This is your answer!):**
```
=FLOOR(B54,1)
```

**Cell B56 (Limiting Factor):**
```
=IF(B55=0,"INVALID",IF(B54=B43,"RISK",IF(B54=B48,"VOLATILITY","MARGIN")))
```

### Step 5: Read Your Answer!

**Cell B55** = Final Position Size in Lots
**Cell B56** = What limited the position (RISK, VOLATILITY, or MARGIN)

---

## 📊 Example: Bank Nifty Signal

**Input:**
- Entry: 52,000
- Stop: 51,650
- ATR: 350
- ER: 0.82

**Result:**
- Lot-R: 1.67
- Lot-V: 0.82
- Lot-M: 11.11
- **Final: 0 lots** (limited by VOLATILITY)

**Why 0?** Because Lot-V (0.82) is less than 1, so FLOOR(0.82) = 0

**Solution:** Increase equity or reduce volatility % to get at least 1 lot.

---

## 📊 Example: Gold Mini Signal

**Input:**
- Entry: 78,500
- Stop: 77,800
- ATR: 450
- ER: 0.85

**Result:**
- Lot-R: 3.04
- Lot-V: 2.22
- Lot-M: 28.57
- **Final: 2 lots** (limited by VOLATILITY)

---

## 🔄 For Pyramid Entries

**Additional Input:**
- B28: Base Position Size (e.g., 1)
- B29: Profit After Base Risk (e.g., 50000)

**Additional Formulas:**

**Cell B67 (Constraint A):**
```
=FLOOR(B5/B37,1)
```

**Cell B68 (Constraint B):**
```
=FLOOR(B28*0.5,1)
```

**Cell B69 (Constraint C):**
```
=IF(B41>0,FLOOR((B29*0.5)/(B41*B36),1),0)
```

**Cell B70 (Pyramid Final Lots):**
```
=FLOOR(MIN(B67,B68,B69),1)
```

---

## ⚡ Quick Tips

1. **Update Equity (B4)** after each trade
2. **Update Margin (B5)** after each position
3. **Check B56** to see what's limiting your position
4. **If Final = 0**, increase equity or reduce risk/volatility %
5. **ER from TradingView** - if missing, use 0.8 as default

---

## 🎯 What Data Comes from TradingView?

From your Pine Script alert JSON:

```json
{
  "price": 52000,      → B24
  "stop": 51650,       → B25
  "atr": 350,          → B26
  "er": 0.82,          → B27
  "instrument": "BANK_NIFTY" → B23
}
```

That's all you need! The Excel sheet does the rest.

---

**Need more details?** See `TOM_BASSO_EXCEL_GUIDE.md` for complete documentation.

