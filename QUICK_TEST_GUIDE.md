# Quick Test Guide - Tom Basso Features

## 🚀 Quick Start Testing

### Test 1: Verify Backward Compatibility (5 minutes)
```
Settings:
- Position Sizing Method: Percent Risk ✅
- Use ER Multiplier: Yes ✅
- Stop Loss Mode: Tom Basso ✅
- All other settings: Keep current
```
**Expected:** Results should match your previous backtest exactly

---

### Test 2: Tom Basso Pure Volatility (5 minutes)
```
Settings:
- Position Sizing Method: Percent Volatility 🆕
- Sizing ATR Period: 14
- Stop Loss Mode: Tom Basso
- All other settings: Keep same
```
**Compare:**
- Position sizes more consistent?
- Smoother equity curve?
- Different trade count?

---

### Test 3: Hybrid Approach (5 minutes)
```
Settings:
- Position Sizing Method: Percent Vol + ER 🆕
- Sizing ATR Period: 14
- Stop Loss Mode: Tom Basso
- All other settings: Keep same
```
**Compare:**
- Best of both worlds?
- Higher Sharpe ratio?

---

## 📊 Metrics to Compare

Create a simple comparison table:

| Metric | Percent Risk (Current) | Percent Volatility | Percent Vol + ER |
|--------|------------------------|-------------------|------------------|
| Total Return | ₹___Cr | ₹___Cr | ₹___Cr |
| Max Drawdown | ___% | ___% | ___% |
| Sharpe Ratio | ___ | ___ | ___ |
| Total Trades | ___ | ___ | ___ |
| Avg Position | ___lots | ___lots | ___lots |
| Win Rate | ___% | ___% | ___% |

---

## 🔍 What to Look For

### Risk Constraint Check:
1. During backtest, watch the info table Row 20 "Risk Budget"
2. Should show available budget dynamically
3. Pyramids should only trigger when budget available

### Position Sizing Check:
1. Info table Row 19 shows current sizing method
2. Row 15 shows calculated lot size for next entry
3. Compare lot sizes between methods

---

## ⚡ Quick Validation

### Pyramiding Risk Constraint Working?
- Look for comments in trade list: pyramid sizes should vary
- Check if some pyramids are smaller when risk budget tight
- Total risk should never exceed 2% (₹2L for ₹1Cr capital)

### Percent Volatility Working?
- Position sizes should be more consistent
- Less variation between trades
- Sizing based on ATR not stop distance

---

## 📈 Decision Matrix

Choose method based on:

| If You Want... | Choose... |
|----------------|-----------|
| Proven performance | Percent Risk (current) |
| Consistent position sizes | Percent Volatility |
| Tom Basso philosophy | Percent Volatility |
| Trend strength weighting | Percent Risk or Hybrid |
| Best risk-adjusted returns | Test all three! |

---

## 🎯 Recommended Action

1. **Run all 3 tests** (15 minutes total)
2. **Compare metrics** in the table above
3. **Choose based on:**
   - Highest Sharpe Ratio (risk-adjusted returns)
   - Lowest Max Drawdown (safety)
   - Your comfort level with position sizing

---

## ✅ Final Checklist

Before going live:
- [ ] Backtested all 3 methods
- [ ] Verified risk constraint working
- [ ] Compared key metrics
- [ ] Selected optimal method
- [ ] Documented choice and reasoning

---

**Time Required:** 15-20 minutes
**Recommendation:** Test all three, but "Percent Risk" is proven winner