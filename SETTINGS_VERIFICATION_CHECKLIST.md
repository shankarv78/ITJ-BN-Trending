# Settings Verification Checklist

**Before Running Backtests: Verify These Settings Match Code Defaults**

---

## Bank Nifty v4.1 Settings Checklist

### ✅ Inputs Tab

Copy these exact values into TradingView → Strategy Settings → Inputs:

#### Entry Conditions
- [ ] RSI Period: **6**
- [ ] RSI Overbought: **70**
- [ ] RSI High Overbought: **80**
- [ ] EMA Period: **200**
- [ ] DC Period: **20**
- [ ] ADX Period: **30**
- [ ] **ADX Threshold: 25** ⚠️ NOT 30, NOT 20
- [ ] **ER Period: 3** ⚠️ NOT 5
- [ ] ER Directional: **UNCHECKED**
- [ ] **ER Threshold: 0.8** ⚠️ NOT 0.77
- [ ] ROC Period: **15**

#### Pyramiding Filter (v4 Optimization)
- [ ] Use ROC Filter for Pyramids: **CHECKED**
- [ ] **ROC Threshold %: 3.0** ⚠️ NOT 2.0, NOT 5.0

#### SuperTrend
- [ ] ST Period: **10**
- [ ] ST Multiplier: **1.5**
- [ ] Doji Body/Range Ratio: **0.1**

#### Display Options
- [ ] Show Debug Panel: **UNCHECKED**
- [ ] Show Donchian Channel: **UNCHECKED**
- [ ] Show RSI: **UNCHECKED**
- [ ] Show ADX: **UNCHECKED**
- [ ] Show Efficiency Ratio: **UNCHECKED**
- [ ] Show ATR: **UNCHECKED**
- [ ] Smart Info Panel: **CHECKED**
- [ ] Show All Info (Debug): **UNCHECKED**

#### Position Sizing (v4.1 Historical Lot Sizing)
- [ ] Use Historical Lot Sizes: **CHECKED** (realistic backtesting)
- [ ] Static Lot Size: **35** (only used if historical disabled)
- [ ] Show Lot Size Info Panel: **UNCHECKED** (optional - for debugging)
- [ ] Mark Lot Size Changes on Chart: **UNCHECKED** (optional)
- [ ] **Risk % of Capital: 2.0** ⚠️ NOT 1.5 (that's Gold Mini)

#### Margin Management
- [ ] Enable Margin Check: **CHECKED**
- [ ] **Margin per Lot (Lakhs): 2.7** (v4 cushion)
- [ ] Use Leverage: **UNCHECKED**
- [ ] Leverage Multiplier: **1**

#### Pyramiding
- [ ] Enable Pyramiding: **CHECKED**
- [ ] Max Pyramids: **3** (4 total positions)
- [ ] **ATR Pyramid Threshold: 0.75** ⚠️ NOT 0.5 (that's Gold Mini)
- [ ] Pyramid Size Ratio: **0.5** (geometric scaling)

#### Stop Loss (v4 Default)
- [ ] **Stop Loss Mode: Tom Basso** (dropdown)
- [ ] ATR Period (Pyramiding): **10**
- [ ] Basso Initial Stop (× ATR): **1**
- [ ] Basso Trailing Stop (× ATR): **2**
- [ ] Basso ATR Period: **10**

#### Date Filter
- [ ] Use Start Date Filter: **CHECKED** (recommended for forward testing)
- [ ] Trade Start Date: **2025-11-11** (or your desired start)

---

### ⚠️ Properties Tab (CRITICAL)

TradingView → Strategy Settings → Properties

#### Basic Settings
- [ ] Initial capital: **5000000** (₹50 Lakhs)
- [ ] Base currency: **Default**
- [ ] Order size: **1**
- [ ] Order size type: **Quantity**

#### Pyramiding (MOST IMPORTANT)
- [ ] **Pyramiding: 3 orders** ⚠️ CRITICAL - NOT 5, NOT 4
  - This allows max 4 total positions (1 base + 3 pyramids)
  - Values > 3 break strategy design assumptions

#### Commission & Slippage
- [ ] **Commission: 0.1 %** ⚠️ NOT 0.05% (that's Gold futures rate)
- [ ] Verify price for limit orders: **0 ticks**
- [ ] **Slippage: 5 ticks** (realistic for automation)

#### Margin
- [ ] Margin for long positions: **0 %** (margin check handled in code)
- [ ] Margin for short positions: **0 %** (long-only strategy)

#### Recalculate (v4 Optimization)
- [ ] After order is filled: **UNCHECKED**
- [ ] **On every tick: UNCHECKED** ⚠️ CRITICAL (calc_on_every_tick=FALSE)
- [ ] **On bar close: CHECKED** ⚠️ CRITICAL (process_orders_on_close=TRUE)
- [ ] Using bar magnifier: **UNCHECKED**
- [ ] Using standard OHLC: **UNCHECKED**

---

### 📊 Chart Settings

TradingView Chart Configuration:

- [ ] **Symbol: BANKNIFTY** (or full NSE:BANKNIFTY)
- [ ] **Timeframe: 75 minutes** (1h 15m)
- [ ] Data range: Minimum 5 years recommended (2015-2025 for statistical significance)

---

## Gold Mini Settings Checklist

### Key Differences from Bank Nifty

Only these parameters differ - all others same as Bank Nifty v4.1:

#### Inputs Tab
- [ ] **ADX Threshold: 20** (vs 25 for Bank Nifty)
- [ ] **Risk % of Capital: 1.5** (vs 2.0 for Bank Nifty)
- [ ] Point Value (Rs per tick): **10** (vs lot size 35 for Bank Nifty)
- [ ] **Margin per Lot (Lakhs): 0.75** (vs 2.7 for Bank Nifty)
- [ ] **ATR Pyramid Threshold: 0.5** (vs 0.75 for Bank Nifty)
- [ ] **ROC Threshold %: 5.0** (vs 3.0 for Bank Nifty)

#### Properties Tab
- [ ] **Commission: 0.05 %** (futures rate, vs 0.1% for Bank Nifty)
- [ ] Pyramiding: **3 orders** (same as Bank Nifty)

#### Chart Settings
- [ ] **Symbol: GOLDMINI** (MCX Gold Mini 100g)
- [ ] **Timeframe: 60 minutes** (1 hour)

---

## Quick Validation Steps

### Before Starting Backtest

1. **Load strategy** in Pine Editor
2. **Add to chart** with correct symbol and timeframe
3. **Open Strategy Settings** (gear icon)
4. **Go through Inputs tab** line by line using checklist above
5. **Go through Properties tab** - verify Pyramiding=3 and Commission
6. **Click OK** to apply
7. **Verify Strategy Tester** shows expected initial capital (₹50L)

### After Running Backtest

1. **Check Total Trades count** - should be 300-1000+ for 10+ year backtest
2. **Check Max Drawdown** - should be 20-30% range for Bank Nifty v4.1
3. **Export List of Trades** to CSV for detailed analysis
4. **Compare CAGR** with documented baseline:
   - Bank Nifty v4.1 (2009-2025): ~22.59% CAGR
   - Gold Mini (2015-2025): ~20.23% CAGR (empirically validated)

### Red Flags (Settings Likely Wrong)

❌ **Too Few Trades** (<100 in 10 years) → Check ADX/ER thresholds, may be too strict
❌ **Too Many Trades** (>2000 in 10 years) → Check entry conditions, filters may be disabled
❌ **Unrealistic CAGR** (>40%) → Check commission rate (might be 0.05% instead of 0.1%)
❌ **Very Low Drawdown** (<10%) → Check risk % and pyramiding settings
❌ **Max 6+ positions shown** → Pyramiding property set to >3 (wrong)

---

## Copy-Paste Settings (For Quick Setup)

### Bank Nifty v4.1 Quick Settings

```
INPUTS:
ADX Threshold = 25
ER Period = 3
ER Threshold = 0.8
ROC Threshold % = 3.0
Risk % of Capital = 2.0
ATR Pyramid Threshold = 0.75
Margin per Lot (Lakhs) = 2.7
Use Historical Lot Sizes = TRUE
Stop Loss Mode = Tom Basso

PROPERTIES:
Initial Capital = 5000000
Pyramiding = 3
Commission = 0.1%
Slippage = 5 ticks
On every tick = UNCHECKED
On bar close = CHECKED
```

### Gold Mini Quick Settings

```
INPUTS:
ADX Threshold = 20
ER Period = 3
ER Threshold = 0.8
ROC Threshold % = 5.0
Risk % of Capital = 1.5
ATR Pyramid Threshold = 0.5
Margin per Lot (Lakhs) = 0.75
Stop Loss Mode = Tom Basso

PROPERTIES:
Initial Capital = 5000000
Pyramiding = 3
Commission = 0.05%
Slippage = 5 ticks
On every tick = UNCHECKED
On bar close = CHECKED
```

---

## Common Mistakes to Avoid

### 1. Mixing Bank Nifty and Gold Settings

❌ **Don't Use:**
- Gold's 1.5% risk for Bank Nifty (use 2.0%)
- Gold's 0.5 ATR pyramid for Bank Nifty (use 0.75)
- Gold's 0.05% commission for Bank Nifty (use 0.1%)
- Gold's 5% ROC for Bank Nifty (use 3%)
- Gold's ADX 20 for Bank Nifty (use 25)

### 2. Pyramiding Property Override

❌ **Properties → Pyramiding > 3** breaks strategy design
- Code input "Max Pyramids = 3" gets overridden by Properties value
- Setting Pyramiding = 5 allows 6 total positions (not 4 as designed)
- Margin calculations assume max 4 positions
- Stop loss logic designed for 4 positions

### 3. Custom Entry Thresholds

⚠️ **Changing these significantly affects strategy:**
- ADX 30 (vs 25) = 30-50% fewer entries
- ER Period 5 (vs 3) = Different ER values, unpredictable entry impact
- ER 0.77 (vs 0.8) = ~5% more entries (easier to meet)
- ROC 2% (vs 3%) = More pyramids, potentially lower quality

### 4. Commission Understatement

❌ **Using 0.05% commission for Bank Nifty:**
- Inflates CAGR by 2-4 percentage points
- Bank Nifty uses options (synthetic futures) = higher commission
- Gold uses futures = lower commission (0.05% correct)
- Results won't match live trading performance

---

## Validation Results

After verifying all settings, you should see these approximate results:

### Bank Nifty v4.1 (2009-2025, 16.75 years)
- **Total Trades:** ~800-850
- **CAGR:** 22-23%
- **Max Drawdown:** -24% to -26%
- **Win Rate:** 50-52%
- **Final Equity:** ₹140-150 Crores

### Gold Mini (2015-2025, 10.6 years)
- **Total Trades:** ~400-450
- **CAGR:** 20-21%
- **Max Drawdown:** -17% to -19%
- **Win Rate:** 45-48%
- **Final Equity:** ₹30-35 Crores

If your results are significantly different, review the checklist again.

---

## Support & References

- **Detailed Settings Analysis:** SETTINGS_ANALYSIS.md
- **Official v4.1 Settings:** BACKTEST_SETTINGS_v4.1.md
- **Code Defaults:** See trend_following_strategy_banknifty_v4.pine (lines 150-238)
- **Gold Comparison:** BANKNIFTY_GOLD_COMPARISON.md

---

**Document Version:** 1.0
**Last Updated:** November 15, 2025
**Purpose:** Pre-backtest settings verification for Bank Nifty v4.1 and Gold Mini
