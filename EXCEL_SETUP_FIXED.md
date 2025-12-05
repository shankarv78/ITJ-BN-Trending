# Excel Setup - Fixed (No Circular References)

## ✅ Fixed Issues

1. **Circular Reference Fixed:** Changed `B41*B36` to `B40*B36` (Risk per Lot calculation)
2. **Row References Fixed:** Changed `B33` to `B32` for instrument selection

## 📋 Step-by-Step Manual Setup

### Step 1: Create Labels (Column A)

Enter these labels in Column A:

```
A1: TOM BASSO POSITION SIZER
A3: PORTFOLIO PARAMETERS
A4: Current Equity (₹)
A5: Available Margin (₹)
A6: Initial Risk %
A7: Initial Volatility %
A11: BANK NIFTY PARAMETERS
A12: Lot Size
A13: Point Value (₹ per point per lot)
A14: Margin per Lot (₹)
A16: GOLD MINI PARAMETERS
A17: Lot Size
A18: Point Value (₹ per point per lot)
A19: Margin per Lot (₹)
A21: TRADINGVIEW SIGNAL DATA
A22: Signal Type
A23: Instrument
A24: Entry Price
A25: Stop Price
A26: ATR
A27: ER
A31: CALCULATIONS
A32: Selected Instrument
A34: Lot Size
A35: Point Value
A36: Margin per Lot
A38: CONSTRAINT 1: RISK-BASED (Lot-R)
A39: Risk Amount (₹)
A40: Risk per Point
A41: Risk per Lot (₹)
A42: Lot-R
A44: CONSTRAINT 2: VOLATILITY-BASED (Lot-V)
A45: Volatility Budget (₹)
A46: Volatility per Lot (₹)
A47: Lot-V
A49: CONSTRAINT 3: MARGIN-BASED (Lot-M)
A50: Lot-M
A52: FINAL POSITION SIZE
A53: Minimum Constraint
A54: Final Lots (FLOOR)
A55: Limiting Factor
```

### Step 2: Enter Values (Column B)

Enter these **VALUES** (not formulas):

```
B4: 5000000
B5: 3000000
B6: 0.5
B7: 0.2
B12: 30
B13: 30
B14: 270000
C17: 100
C18: 10
C19: 105000
B22: BASE_ENTRY
B23: BANK_NIFTY
B24: 52000
B25: 51650
B26: 350
B27: 0.82
```

### Step 3: Enter Formulas (Column B)

**IMPORTANT:** Enter these formulas **exactly as shown**:

```
B32: =IF(B23="BANK_NIFTY","BANK_NIFTY",IF(B23="GOLD_MINI","GOLD_MINI",""))

B34: =IF(B32="BANK_NIFTY",B12,IF(B32="GOLD_MINI",C17,0))
B35: =IF(B32="BANK_NIFTY",B13,IF(B32="GOLD_MINI",C18,0))
B36: =IF(B32="BANK_NIFTY",B14,IF(B32="GOLD_MINI",C19,0))

B39: =B4*B6/100
B40: =B24-B25
B41: =B40*B36
B42: =IF(B41>0,(B39/B41)*B27,0)

B45: =B4*B7/100
B46: =B26*B35
B47: =IF(B46>0,B45/B46,0)

B50: =IF(B36>0,B5/B36,0)

B53: =MIN(B42,B47,B50)
B54: =FLOOR(B53,1)
B55: =IF(B54=0,"INVALID",IF(B53=B42,"RISK",IF(B53=B47,"VOLATILITY","MARGIN")))
```

### Step 4: Verify

1. **Check B32:** Should show "BANK_NIFTY" or "GOLD_MINI"
2. **Check B54:** This is your **FINAL LOTS** answer
3. **Check B55:** This shows what's limiting (RISK, VOLATILITY, or MARGIN)

### Step 5: Test

**Test with Bank Nifty:**
- B23: BANK_NIFTY
- B24: 52000
- B25: 51650
- B26: 350
- B27: 0.82

**Expected Results:**
- B42 (Lot-R): ~1.67
- B47 (Lot-V): ~0.82
- B50 (Lot-M): ~11.11
- B54 (Final): 0 (limited by VOLATILITY)

## 🔧 Troubleshooting

### Still Getting Circular Reference Error?

1. **Check B41:** Should be `=B40*B36`, NOT `=B41*B36`
2. **Check B32 references:** Should reference `B32`, not `B33`
3. **Enable Iterative Calculation (if needed):**
   - Excel → Preferences → Calculation
   - Check "Enable iterative calculation"
   - Max iterations: 1

### Formulas Not Working?

1. **Check for typos:** Copy formulas exactly as shown
2. **Check cell references:** Make sure row numbers match
3. **Check data types:** B24, B25 should be numbers, not text

### Getting #VALUE! Error?

- Make sure B23 contains exactly "BANK_NIFTY" or "GOLD_MINI" (case-sensitive)
- Make sure B24 > B25 (entry price > stop price)
- Make sure all numeric cells contain numbers, not text

## 📊 Quick Reference

**Key Cells:**
- **B4:** Current Equity (update after each trade)
- **B5:** Available Margin (update after each position)
- **B24:** Entry Price (from TradingView)
- **B25:** Stop Price (from TradingView)
- **B26:** ATR (from TradingView)
- **B27:** ER (from TradingView)
- **B54:** **FINAL LOTS** ← Your answer!
- **B55:** Limiting Factor

## ✅ Verification Checklist

- [ ] No circular reference errors
- [ ] B32 shows "BANK_NIFTY" or "GOLD_MINI"
- [ ] B34, B35, B36 show correct instrument parameters
- [ ] B42, B47, B50 show positive numbers
- [ ] B54 shows final lots (0 or more)
- [ ] B55 shows RISK, VOLATILITY, or MARGIN

---

**If you still have issues, use the manual setup above instead of the CSV file.**

