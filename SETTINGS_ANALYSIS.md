# Settings Analysis: Screenshots vs Code Defaults

**Date**: 2025-11-15
**Analysis**: Comparison of TradingView settings shown in screenshots against Bank Nifty v4.1 Pine Script defaults

---

## Executive Summary

⚠️ **CRITICAL FINDING**: The screenshots show **custom settings** that differ significantly from Bank Nifty v4.1 documented defaults. Some values appear to be a hybrid mix of Bank Nifty and Gold Mini settings, with additional custom modifications.

**Impact**: Users following the screenshots will get different backtest results than documented performance expectations.

---

## Detailed Comparison Table

| Parameter | Screenshot Value | Bank Nifty v4.1 Code | Gold Mini Code | Match Status | Notes |
|-----------|------------------|---------------------|----------------|--------------|-------|
| **ENTRY CONDITIONS** |
| RSI Period | 6 | 6 | 6 | ✅ MATCH | Correct |
| RSI Overbought | 70 | 70 | 70 | ✅ MATCH | Correct |
| RSI High Overbought | 80 | 80 | 80 | ✅ MATCH | Correct |
| EMA Period | 200 | 200 | 200 | ✅ MATCH | Correct |
| DC Period | 20 | 20 | 20 | ✅ MATCH | Correct |
| ADX Period | 30 | 30 | 30 | ✅ MATCH | Correct |
| **ADX Threshold** | **30** | **25** | **20** | ❌ CUSTOM | Screenshot = 30, Code = 25, Gold = 20 |
| **ER Period** | **5** | **3** | **3** | ❌ CUSTOM | Screenshot = 5, Code = 3 |
| ER Directional | false | false | false | ✅ MATCH | Correct |
| **ER Threshold** | **0.77** | **0.8** | **0.8** | ❌ CUSTOM | Screenshot = 0.77, Code = 0.8 |
| ROC Period | 15 | 15 | 15 | ✅ MATCH | Correct |
| **PYRAMIDING FILTER** |
| Use ROC Filter | TRUE | TRUE | TRUE | ✅ MATCH | v4 optimization enabled |
| **ROC Threshold %** | **2.0%** | **3.0%** | **5.0%** | ❌ CUSTOM | Screenshot = 2%, Code = 3%, Gold = 5% |
| **SUPERTRAND** |
| ST Period | 10 | 10 | 10 | ✅ MATCH | Correct |
| ST Multiplier | 1.5 | 1.5 | 1.5 | ✅ MATCH | Correct |
| Doji Body/Range Ratio | 0.1 | 0.1 | 0.1 | ✅ MATCH | Correct |
| **DISPLAY OPTIONS** |
| Show Debug Panel | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Show Donchian | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Show RSI | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Show ADX | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Show ER | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Show ATR | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Smart Info Panel | TRUE | TRUE | TRUE | ✅ MATCH | Correct |
| Show All Info (Debug) | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| **LOT SIZING (v4.1)** |
| Use Historical Lot Sizes | TRUE | TRUE | N/A | ✅ MATCH | v4.1 feature |
| Static Lot Size | 35 | 35 | 10 (point value) | ✅ MATCH | Bank Nifty current lot size |
| Show Lot Size Info Panel | FALSE | FALSE | N/A | ✅ MATCH | Correct |
| Mark Lot Size Changes | TRUE | FALSE | N/A | ⚠️ MODIFIED | Screenshot enabled, code default disabled |
| **POSITION SIZING** |
| **Risk % of Capital** | **1.5%** | **2.0%** | **1.5%** | ⚠️ GOLD VALUE | Screenshot = Gold default, Code = 2.0% |
| Enable Margin Check | TRUE | TRUE | TRUE | ✅ MATCH | Correct |
| **Margin per Lot (Lakhs)** | **2.7** | **2.7** | **0.75** | ✅ MATCH | v4 margin cushion correct |
| Use Leverage | FALSE | FALSE | FALSE | ✅ MATCH | Correct |
| Leverage Multiplier | 1 | 1.0 | 1.0 | ✅ MATCH | Correct |
| **PYRAMIDING** |
| Enable Pyramiding | TRUE | TRUE | TRUE | ✅ MATCH | Correct |
| Max Pyramids | 3 | 3 | 3 | ✅ MATCH | Correct |
| **ATR Pyramid Threshold** | **0.5** | **0.75** | **0.5** | ⚠️ GOLD VALUE | Screenshot = Gold default, Code = 0.75 |
| Pyramid Size Ratio | 0.5 | 0.5 | 0.5 | ✅ MATCH | Correct |
| **STOP LOSS** |
| Stop Loss Mode | Tom Basso | Tom Basso | Tom Basso | ✅ MATCH | v4 default correct |
| ATR Period (Pyramiding) | 10 | 10 | 10 | ✅ MATCH | Correct |
| Basso Initial Stop (× ATR) | 1 | 1.0 | 1.0 | ✅ MATCH | Correct |
| Basso Trailing Stop (× ATR) | 2 | 2.0 | 2.0 | ✅ MATCH | Correct |
| Basso ATR Period | 10 | 10 | 10 | ✅ MATCH | Correct |
| **DATE FILTER** |
| Use Start Date Filter | (not shown) | TRUE | TRUE | N/A | Not visible in screenshots |
| Trade Start Date | 2025-11-11 05:30 | 2025-11-11 00:00 | 2025-11-11 00:00 | ⚠️ TIME | Date matches, time differs |
| **STRATEGY PROPERTIES** |
| Initial Capital | 5000000 | 5000000 | 5000000 | ✅ MATCH | ₹50L correct |
| **Pyramiding (Property)** | **5 orders** | **3 orders** | **3 orders** | ❌ MISMATCH | Screenshot = 5, Code = 3 (max 4 positions) |
| Order Size | 1 | 1 | 1 | ✅ MATCH | Correct |
| **Commission** | **0.05%** | **0.1%** | **0.05%** | ⚠️ GOLD VALUE | Screenshot = Gold rate, Code = 0.1% |
| Slippage | 5 ticks | (default) | 5 ticks | ✅ MATCH | Realistic |
| **RECALCULATE** |
| On every tick | FALSE | FALSE (code) | FALSE (code) | ✅ MATCH | calc_on_every_tick=FALSE correct |
| On bar close | TRUE | TRUE (code) | TRUE (code) | ✅ MATCH | process_orders_on_close=TRUE correct |

---

## Critical Discrepancies

### 1. ADX Threshold: 30 (Screenshot) vs 25 (Code)

**Code Default (Line 164):**
```pinescript
adx_threshold = input.float(25, "ADX Threshold", minval=0)
```

**Screenshot Shows:** 30

**Analysis:**
- Bank Nifty v4.1 default: **25** (more selective, filters weak trends)
- Gold Mini default: **20** (more entries, empirically validated for Gold)
- Screenshot custom: **30** (extremely conservative, will reduce entries further)

**Impact:**
- ADX 30 will generate **significantly fewer entries** than documented
- This is even more conservative than Bank Nifty's already strict ADX 25
- May be testing for extremely stable trends only

**Recommendation:** Revert to **25** for Bank Nifty v4.1 baseline performance

---

### 2. ER Period: 5 (Screenshot) vs 3 (Code)

**Code Default (Line 167):**
```pinescript
er_period = input.int(3, "ER Period", minval=1)
```

**Screenshot Shows:** 5

**Analysis:**
- Standard default: **3** (both Bank Nifty and Gold)
- Screenshot custom: **5** (longer lookback, smoother ER calculation)

**Impact:**
- Longer ER period = **more stable** but **less responsive** to momentum changes
- May miss early trend formations
- ER values will be lower on average (more noise in longer periods)

**Recommendation:** Revert to **3** for standard strategy behavior

---

### 3. ER Threshold: 0.77 (Screenshot) vs 0.8 (Code)

**Code Default (Line 169):**
```pinescript
er_threshold = input.float(0.8, "ER Threshold", minval=0, maxval=1)
```

**Screenshot Shows:** 0.77

**Analysis:**
- Standard default: **0.8** (80% efficiency requirement)
- Screenshot custom: **0.77** (77% efficiency, slightly relaxed)

**Impact:**
- Lower threshold = **more entries** (easier to meet ER condition)
- Combined with ER Period 5, this may partially compensate for the longer lookback
- 3.75% easier to meet (0.77 vs 0.80)

**Recommendation:** Revert to **0.8** for consistent filtering

---

### 4. ROC Threshold: 2% (Screenshot) vs 3% (Code)

**Code Default (Line 174):**
```pinescript
roc_threshold = input.float(3.0, "ROC Threshold %", minval=-10, maxval=20, step=0.5,
    tooltip="✨ v4: 3% minimum momentum for pyramids (Gold learning: filters weak pyramids)")
```

**Screenshot Shows:** 2%

**Analysis:**
- Bank Nifty v4.1 default: **3.0%** (moderate momentum requirement)
- Gold Mini default: **5.0%** (strict momentum requirement, empirically validated)
- Screenshot custom: **2.0%** (relaxed momentum requirement)

**Impact:**
- Lower ROC threshold = **more pyramids allowed** (easier to meet momentum filter)
- This **contradicts v4 optimization philosophy** (selective pyramiding)
- May allow pyramids in weaker momentum, reducing pyramid quality
- Gold empirical data showed 5% worked best - 2% is 60% easier to meet

**Recommendation:** Revert to **3.0%** for v4 optimization benefits

---

### 5. Risk % of Capital: 1.5% (Screenshot) vs 2.0% (Code)

**Code Default (Line 212):**
```pinescript
risk_percent = input.float(2.0, "Risk % of Capital", minval=0.1, maxval=10, step=0.1,
    group="Position Sizing", tooltip="Percentage of capital to risk per trade")
```

**Screenshot Shows:** 1.5%

**Analysis:**
- Bank Nifty v4.1 default: **2.0%**
- Gold Mini default: **1.5%** (lower volatility instrument)
- Screenshot: Using **Gold value** for Bank Nifty

**Impact:**
- 1.5% risk = **25% smaller position sizes** than documented
- Lower returns and lower drawdowns expected
- More conservative approach, but not the v4.1 baseline

**Recommendation:** Use **2.0%** for Bank Nifty, **1.5%** only for Gold Mini

---

### 6. ATR Pyramid Threshold: 0.5 (Screenshot) vs 0.75 (Code)

**Code Default (Line 223):**
```pinescript
atr_pyramid_threshold = input.float(0.75, "ATR Pyramid Threshold", minval=0.25, maxval=2.0, step=0.25,
    tooltip="ATR multiplier for pyramid triggers (0.75 = add every 0.75 ATR move)")
```

**Screenshot Shows:** 0.5

**Analysis:**
- Bank Nifty v4.1 default: **0.75** (larger gaps between pyramids)
- Gold Mini default: **0.5** (tighter pyramiding for smoother trends)
- Screenshot: Using **Gold value** for Bank Nifty

**Impact:**
- 0.5 ATR = **33% faster pyramiding** (pyramids trigger sooner)
- Bank Nifty volatility may cause premature pyramids
- Gold used 0.5 because it has smoother, tighter trends
- Bank Nifty needs 0.75 to avoid crowded entries in volatile spikes

**Recommendation:** Use **0.75** for Bank Nifty, **0.5** only for Gold Mini

---

### 7. Commission: 0.05% (Screenshot) vs 0.1% (Code)

**Code Default (Line 78):**
```pinescript
strategy("Bank Nifty Trend Following v4.1",
     ...
     commission_value=0.1)
```

**Screenshot Shows:** 0.05%

**Analysis:**
- Bank Nifty default: **0.1%** (options commission rate)
- Gold Mini default: **0.05%** (futures commission rate)
- Screenshot: Using **Gold commission rate** for Bank Nifty

**Impact:**
- 0.05% commission = **50% lower trading costs** than realistic
- Bank Nifty trades synthetic futures via options (ATM PE Sell + CE Buy)
- Options have higher commission than futures
- **Backtest results will be unrealistically optimistic**

**Recommendation:** Use **0.1%** for Bank Nifty (realistic), **0.05%** only for Gold Mini

---

### 8. Pyramiding Property: 5 orders (Screenshot) vs 3 (Code)

**Code Default (Line 70):**
```pinescript
strategy("Bank Nifty Trend Following v4.1",
     ...
     pyramiding=3,
     ...)
```

**Screenshot Shows:** Pyramiding = 5 orders

**Analysis:**
- Code default: **pyramiding=3** (allows 4 total positions: 1 base + 3 pyramids)
- Screenshot Properties tab: **5 orders** (allows 6 total positions)

**Impact:**
- This is a **critical mismatch** - the code's `max_pyramids=3` input will be ignored
- Strategy Properties `pyramiding` value **overrides** the input parameter
- Screenshot allows up to **6 positions** instead of documented 4
- Position sizing, margin calculations, and stop management assume max 4 positions
- **May cause unexpected behavior** with more positions than designed

**Recommendation:** Change Strategy Properties → Pyramiding to **3** (not 5)

---

## Settings Classification

### ✅ Correct Settings (Matching Bank Nifty v4.1)

- RSI Period: 6
- RSI Thresholds: 70, 80
- EMA Period: 200
- DC Period: 20
- ADX Period: 30
- ROC Period: 15
- SuperTrend: 10, 1.5
- Doji Threshold: 0.1
- All display toggles (Smart Panel, etc.)
- Historical Lot Sizes: TRUE
- Static Lot Size: 35
- Margin per Lot: 2.7L (v4 cushion)
- Max Pyramids input: 3
- Pyramid Size Ratio: 0.5
- Stop Loss Mode: Tom Basso
- Tom Basso parameters: 1.0, 2.0, 10
- Initial Capital: ₹50L
- calc_on_every_tick: FALSE
- process_orders_on_close: TRUE

### ⚠️ Gold Mini Values (Not Bank Nifty Defaults)

- Risk % of Capital: 1.5% (should be 2.0%)
- ATR Pyramid Threshold: 0.5 (should be 0.75)
- Commission: 0.05% (should be 0.1%)

### ❌ Custom Values (Not Matching Any Default)

- ADX Threshold: 30 (Bank Nifty = 25, Gold = 20)
- ER Period: 5 (both = 3)
- ER Threshold: 0.77 (both = 0.8)
- ROC Threshold: 2% (Bank Nifty = 3%, Gold = 5%)
- Pyramiding Property: 5 orders (both = 3)

### ⚠️ Minor Modifications

- Mark Lot Size Changes: TRUE (code default = FALSE)
- Trade Start Date time: 05:30 (code = 00:00)

---

## Recommended Actions

### For Standard Bank Nifty v4.1 Backtesting

**Change these settings to match code defaults:**

1. **Inputs Tab:**
   - ADX Threshold: 30 → **25**
   - ER Period: 5 → **3**
   - ER Threshold: 0.77 → **0.8**
   - ROC Threshold %: 2 → **3.0**
   - Risk % of Capital: 1.5 → **2.0**
   - ATR Pyramid Threshold: 0.5 → **0.75**

2. **Properties Tab:**
   - Commission: 0.05% → **0.1%**
   - Pyramiding: 5 orders → **3 orders** ⚠️ CRITICAL

3. **Optional (for cleaner charts):**
   - Mark Lot Size Changes: TRUE → FALSE

### For Custom/Experimental Testing

If these custom settings are intentional experiments:

1. **Document the rationale** for each custom value
2. **Create a new strategy version** (e.g., v4.2-experimental)
3. **Update documentation** to reflect custom settings
4. **Compare results** against v4.1 baseline
5. **Track which settings improve/degrade performance**

---

## Impact on Performance Metrics

**Expected changes from screenshot settings vs code defaults:**

| Metric | Screenshot Settings (Custom) | Code Defaults (v4.1) | Expected Difference |
|--------|------------------------------|----------------------|---------------------|
| **Entry Count** | Lower (ADX 30 stricter) | Higher (ADX 25) | -10-20% fewer entries |
| **Pyramid Count** | Higher (ROC 2%, ATR 0.5) | Lower (ROC 3%, ATR 0.75) | +30-50% more pyramids |
| **Position Size** | Smaller (1.5% risk) | Larger (2.0% risk) | -25% smaller |
| **Total Positions** | Up to 6 (pyramiding=5) | Up to 4 (pyramiding=3) | +50% more positions allowed |
| **CAGR** | Lower (smaller positions, fewer entries) | Higher (documented baseline) | -3-7% CAGR difference |
| **Max Drawdown** | Lower (smaller positions) | Higher (2% risk) | -2-5% DD reduction |
| **Profit Factor** | Lower? (more pyramids at 2% ROC) | Higher (3% ROC filter) | Unpredictable |
| **Commission Impact** | Understated (0.05% vs 0.1%) | Realistic (0.1%) | +2-3% CAGR inflation |

**Net Effect:** Screenshot settings likely show **unrealistically optimistic** performance due to:
- Lower commission (50% less than actual)
- More pyramiding allowed (5 vs 3, with easier ROC filter)
- Smaller position sizes (lower risk, but also inflated by lower commission)

---

## Documentation Updates Required

### 1. Update CLAUDE.md

Current CLAUDE.md states:
- "Risk per trade: 2.0% (Bank Nifty)" ✅ CORRECT in docs, wrong in screenshot
- "ATR pyramid threshold: 0.75" ✅ CORRECT in docs, wrong in screenshot
- "Commission: 0.1%" ✅ CORRECT in docs, wrong in screenshot

**Action:** Add warning about verifying TradingView strategy properties match code defaults

### 2. Update BANKNIFTY_V4_CHANGELOG.md

Current changelog documents v4 changes correctly, but doesn't warn about:
- Strategy Properties pyramiding value override
- Common user errors (using Gold settings for Bank Nifty)

**Action:** Add "Common Configuration Errors" section

### 3. Create SETTINGS_VERIFICATION_CHECKLIST.md

New document needed:
- Pre-backtest settings verification checklist
- Code defaults vs TradingView Properties comparison
- Copy-paste settings for quick setup

---

## Conclusions

1. **Screenshot settings are CUSTOM** - not Bank Nifty v4.1 defaults
2. **Mix of Gold and custom values** - appears to be experimental configuration
3. **Critical mismatch: pyramiding=5** - allows more positions than designed for
4. **Commission too low** - will show unrealistically good results
5. **ROC filter weakened** - contradicts v4 optimization goal

**Recommendation:** If these screenshots represent a backtest, the results should be clearly labeled as "Custom Settings" and not compared to documented v4.1 baseline performance.

**For accurate v4.1 validation:** Use code defaults exactly as specified in the Pine Script file.

---

**Document Version:** 1.0
**Author:** Settings Verification Analysis
**Related Files:**
- `trend_following_strategy_banknifty_v4.pine` (actual code defaults)
- `gold_trend_following_strategy.pine` (Gold defaults for comparison)
- `BANKNIFTY_V4_CHANGELOG.md` (v4 optimization documentation)
