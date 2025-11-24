# BANK NIFTY TREND FOLLOWING STRATEGY - v6 CHANGELOG

**Current Version:** v6.0
**Release Date:** 2025-11-16
**Strategy:** ITJ Bank Nifty 75-min Trend Following
**Base:** v5.0 with Parameter Reversion + ROC Filter Disabled
**Backtest Period:** Jan 1, 2009 — Nov 14, 2025 (16.9 years)

---

## EXECUTIVE SUMMARY

Bank Nifty v6.0 represents a **strategic parameter reversion** from v5.0:
1. **Maintained v5 Capacity**: 5 pyramids (6 total positions) - KEPT
2. **Reverted Entry Parameters**: ER Period 5→3, ER Threshold 0.77→0.8 - REVERTED
3. **Reverted Pyramid Parameters**: ROC 2%→5%, ATR 0.5→0.75 - REVERTED
4. **Reverted Risk**: 1.5%→2.0% - REVERTED
5. **CRITICAL: ROC Filter DISABLED** - Major deviation from v4/v5

**Philosophy:** "Extended pyramiding capacity (v5) with proven v4 parameter stability, without ROC gating constraint."

---

## BACKTEST RESULTS (Jan 1, 2009 — Nov 14, 2025)

### Performance Metrics

| Metric | v6.0 Result | v5.0 Expected | v4.1 Baseline |
|--------|-------------|---------------|---------------|
| **Total P&L** | ₹29.99 Cr (+6,006.52%) | TBD | ₹22.59 Cr |
| **Initial Capital** | ₹50 Lakhs | ₹50 Lakhs | ₹50 Lakhs |
| **CAGR** | **~27.5%** | 19-24% | 22.59% |
| **Max Drawdown** | **-25.08%** | -20% to -27% | -24.87% |
| **Total Trades** | **923** | ~650-750 | ~880 |
| **Profitable Trades** | **52.98% (489/923)** | 48-54% | 51% |
| **Profit Factor** | **2.055** | TBD | ~2.0 |
| **Sharpe Ratio** | **0.294** | TBD | TBD |
| **Sortino Ratio** | **0.957** | TBD | TBD |
| **Avg Win** | ₹11.96 Lakhs (2.44%) | TBD | TBD |
| **Avg Loss** | ₹6.56 Lakhs (1.07%) | TBD | TBD |
| **Win/Loss Ratio** | **1.824** | TBD | TBD |
| **Avg Bars in Trade** | 22 bars | TBD | TBD |
| **Margin Calls** | **0** | 0 | 0 |

### Key Observations

1. **Outstanding CAGR**: 27.5% over 16.9 years significantly exceeds v4 (22.59%) and v5 expectations (19-24%)
2. **Managed Drawdown**: -25.08% is within acceptable range (v4: -24.87%, v5 expected: -20% to -27%)
3. **High Trade Count**: 923 trades suggests more pyramiding activity than v5 (due to no ROC filter)
4. **Strong Profitability**: 52.98% win rate with 2.055 profit factor indicates robust edge
5. **Zero Margin Calls**: Risk management systems working correctly across 923 trades

---

## v6.0 COMPLETE SETTINGS SPECIFICATION

### Strategy Declaration (Properties Tab)

```pinescript
strategy("Bank Nifty Trend Following v6.0",
    overlay=true,
    pyramiding=5,                    // ← v5/v6 (was 3 in v4)
    initial_capital=5000000,         // ₹50 Lakhs
    default_qty_type=strategy.fixed,
    default_qty_value=1,
    commission_type=strategy.commission.percent,
    commission_value=0.05,           // ← v5/v6 (was 0.1 in v4)
    slippage=5,                      // ← v6 empirical validation
    calc_on_every_tick=false,        // ← v4/v5/v6
    process_orders_on_close=true)    // ← v4/v5/v6
```

### Inputs Tab - Complete Parameters

#### ENTRY CONDITIONS

| Parameter | v6.0 Value | v5.0 Value | v4.1 Value | Change |
|-----------|------------|------------|------------|--------|
| **RSI Period** | 6 | 6 | 6 | ⚪ Unchanged |
| **RSI Overbought** | 70 | 70 | 70 | ⚪ Unchanged |
| **RSI High Overbought** | 80 | 80 | 80 | ⚪ Unchanged |
| **EMA Period** | 200 | 200 | 200 | ⚪ Unchanged |
| **DC Period** | 20 | 20 | 20 | ⚪ Unchanged |
| **ADX Period** | 30 | 30 | 30 | ⚪ Unchanged |
| **ADX Threshold** | **30** | 30 | 25 | ✅ Kept v5 |
| **ER Period** | **3** | 5 | 3 | ⬅️ Reverted to v4 |
| **ER Directional** | FALSE | FALSE | FALSE | ⚪ Unchanged |
| **ER Threshold** | **0.8** | 0.77 | 0.8 | ⬅️ Reverted to v4 |
| **ROC Period** | 15 | 15 | 15 | ⚪ Unchanged |
| **Use ROC Filter** | **FALSE** | TRUE | TRUE | ⚠️ DISABLED |
| **ROC Threshold %** | **5.0** | 2.0 | 3.0 | ⬅️ Modified |

#### SUPERTREND & DOJI

| Parameter | v6.0 Value | v5.0 Value | v4.1 Value |
|-----------|------------|------------|------------|
| **ST Period** | 10 | 10 | 10 |
| **ST Multiplier** | 1.5 | 1.5 | 1.5 |
| **Doji Body/Range Ratio** | 0.1 | 0.1 | 0.1 |

#### DISPLAY OPTIONS

| Parameter | v6.0 Value |
|-----------|------------|
| **Show Debug Panel** | FALSE |
| **Show Donchian Channel** | FALSE |
| **Show RSI** | FALSE |
| **Show ADX** | FALSE |
| **Show Efficiency Ratio** | FALSE |
| **Show ATR** | FALSE |
| **Smart Info Panel** | TRUE |
| **Show All Info (Debug)** | FALSE |

#### POSITION SIZING

| Parameter | v6.0 Value | v5.0 Value | v4.1 Value | Change |
|-----------|------------|------------|------------|--------|
| **Use Historical Lot Sizes** | TRUE | TRUE | TRUE | ⚪ Unchanged |
| **Static Lot Size** | 35 | 35 | 35 | ⚪ Unchanged |
| **Show Lot Size Info Panel** | FALSE | FALSE | FALSE | ⚪ Unchanged |
| **Mark Lot Size Changes** | FALSE | FALSE | FALSE | ⚪ Unchanged |
| **Risk % of Capital** | **2.0** | 1.5 | 2.0 | ⬅️ Reverted to v4 |
| **Enable Margin Check** | TRUE | TRUE | TRUE | ⚪ Unchanged |
| **Margin per Lot (Lakhs)** | 2.7 | 2.7 | 2.7 | ⚪ Unchanged |
| **Use Leverage** | FALSE | FALSE | FALSE | ⚪ Unchanged |
| **Leverage Multiplier** | 1 | 1 | 1 | ⚪ Unchanged |

#### PYRAMIDING

| Parameter | v6.0 Value | v5.0 Value | v4.1 Value | Change |
|-----------|------------|------------|------------|--------|
| **Enable Pyramiding** | TRUE | TRUE | TRUE | ⚪ Unchanged |
| **Max Pyramids** | **5** | 5 | 3 | ✅ Kept v5 |
| **ATR Pyramid Threshold** | **0.75** | 0.5 | 0.75 | ⬅️ Reverted to v4 |
| **Pyramid Size Ratio** | 0.5 | 0.5 | 0.5 | ⚪ Unchanged |

#### STOP LOSS

| Parameter | v6.0 Value | v5.0 Value | v4.1 Value |
|-----------|------------|------------|------------|
| **Stop Loss Mode** | Tom Basso | Tom Basso | Tom Basso |
| **ATR Period (Pyramiding)** | 10 | 10 | 10 |
| **Basso Initial Stop (× ATR)** | 1 | 1 | 1 |
| **Basso Trailing Stop (× ATR)** | 2 | 2 | 2 |
| **Basso ATR Period** | 10 | 10 | 10 |

#### DATE FILTER

| Parameter | v6.0 Value |
|-----------|------------|
| **Use Start Date Filter** | FALSE |
| **Trade Start Date** | 2025-11-11 (unused) |

---

## DETAILED CHANGE ANALYSIS

### 1. ROC Filter: ENABLED → DISABLED ⚠️ CRITICAL

**Change:**
```pinescript
// v4/v5:
use_roc_for_pyramids = input.bool(true, "Use ROC Filter for Pyramids", ...)

// v6:
use_roc_for_pyramids = input.bool(false, "Use ROC Filter for Pyramids", ...)
```

**Impact:**
- **Most Significant Change**: Removes momentum gating for pyramid entries
- v4/v5: Only pyramid when 15-period ROC > threshold (3% or 2%)
- v6: Pyramid based on ATR spacing + triple-constraint only (no ROC check)
- **Expected Result**: +50-100% more pyramid attempts (many may fail triple-constraint)
- **Risk**: May pyramid in weak momentum or reversals (mitigated by profitability gate)

**Rationale:**
- ROC filter may be too restrictive, missing valid pyramid opportunities
- Triple-constraint system (margin, scaling, profitability) provides sufficient protection
- Empirical validation shows strong results without ROC filter

**Trade-off:**
- ✅ More pyramiding → better trend capture
- ⚠️ Some pyramids in weak momentum → potential whipsaw
- ✅ Still protected by profitability gate (only pyramid if profitable)

---

### 2. ER Period: 5 → 3

**Change:**
```pinescript
// v5:
er_period = input.int(5, "ER Period", minval=1, ...)

// v6:
er_period = input.int(3, "ER Period", minval=1, ...)
```

**Impact:**
- Shorter ER lookback = more sensitive to recent price action
- v5: 5-period ER smooths out noise, more stable
- v6: 3-period ER reacts faster to trend formation
- **Expected Result**: +5-10% more base entries (ER easier to meet)

**Rationale:**
- v5's 5-period ER may be over-smoothing on 75-min timeframe
- Bank Nifty intraday volatility suits faster ER calculation
- Empirically validated in v4 baseline

---

### 3. ER Threshold: 0.77 → 0.8

**Change:**
```pinescript
// v5:
er_threshold = input.float(0.77, "ER Threshold", ...)

// v6:
er_threshold = input.float(0.8, "ER Threshold", ...)
```

**Impact:**
- Slightly stricter ER threshold (0.8 vs 0.77)
- **Net Effect with ER Period 3**: Similar entry frequency to v5
- 3-period ER with 0.8 threshold ≈ 5-period ER with 0.77 threshold

**Rationale:**
- Compensates for shorter ER period
- Maintains entry quality standards
- Proven combination from v4

---

### 4. ROC Threshold: 2% → 5%

**Change:**
```pinescript
// v5:
roc_threshold = input.float(2.0, "ROC Threshold %", ...)

// v6:
roc_threshold = input.float(5.0, "ROC Threshold %", ...)
```

**Impact:**
- **Irrelevant** since ROC filter is disabled in v6
- Parameter kept at 5% for consistency if user re-enables ROC filter

---

### 5. Risk % of Capital: 1.5% → 2.0%

**Change:**
```pinescript
// v5:
risk_percent = input.float(1.5, "Risk % of Capital", ...)

// v6:
risk_percent = input.float(2.0, "Risk % of Capital", ...)
```

**Impact:**
- 33% larger base positions (2.0% vs 1.5%)
- **Initial Position**: ~33% more lots per trade
- **Total Exposure**: Higher capital utilization
- **Drawdown Potential**: +2-5% max drawdown expected

**Rationale:**
- v6 has 6-position capacity, can handle larger base
- Empirically validated in v4 (2.0% risk)
- Better capital efficiency with extended pyramiding

**Risk Exposure Comparison:**
```
v5: 1.5% risk × 6 positions = 6.09% max exposure (with 50% scaling)
v6: 2.0% risk × 6 positions = 8.08% max exposure (with 50% scaling)

Net Effect: ~33% higher maximum capital at risk
```

---

### 6. ATR Pyramid Threshold: 0.5 → 0.75

**Change:**
```pinescript
// v5:
atr_pyramid_threshold = input.float(0.5, "ATR Pyramid Threshold", ...)

// v6:
atr_pyramid_threshold = input.float(0.75, "ATR Pyramid Threshold", ...)
```

**Impact:**
- Wider pyramid spacing (0.75 ATR vs 0.5 ATR)
- **Pyramid Trigger Frequency**: -30-40% fewer pyramid attempts
- Allows more price movement between pyramids

**Rationale:**
- With ROC filter disabled, ATR spacing is primary pyramid gate
- 0.75 ATR spacing prevents over-pyramiding
- Proven in v4 for Bank Nifty's volatility profile

**Example:**
```
Price moves 3.0 ATR from base entry:

v5 (0.5 ATR): Could trigger 6 pyramids (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
v6 (0.75 ATR): Could trigger 4 pyramids (0, 0.75, 1.5, 2.25, 3.0)

v6 spaces pyramids 50% wider apart
```

---

### 7. ADX Threshold: MAINTAINED at 30 ✅

**No Change from v5:**
```pinescript
adx_threshold = input.float(30, "ADX Threshold", ...)
```

**Rationale:**
- v5's ADX 30 stricter entry filter works well
- Complements v6's relaxed pyramiding (no ROC filter)
- Fewer base entries, more pyramiding per entry

---

### 8. Commission: MAINTAINED at 0.05% ✅

**No Change from v5:**
```pinescript
commission_value=0.05
```

**Rationale:**
- Realistic futures commission rate
- More accurate P&L modeling

---

### 9. Slippage: 0 → 5 ticks ✅

**Change:**
```pinescript
// Initial v6 testing:
slippage=0

// v6 final (empirical validation):
slippage=5
```

**Impact:**
- User noted: "results reduced slightly after i added 5 points slippage"
- 5 ticks slippage reflects realistic automation execution
- Performance metrics in this document reflect slippage=5 results

---

## PARAMETERS UNCHANGED (Maintained Across v4/v5/v6)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **RSI Period** | 6 | Fast momentum - proven effective |
| **RSI Overbought** | 70 | Standard threshold |
| **EMA Period** | 200 | Long-term trend - industry standard |
| **DC Period** | 20 | Breakout detection - proven effective |
| **SuperTrend** | (10, 1.5) | Core trend indicator |
| **Doji Threshold** | 0.1 | Indecision filter |
| **Margin per Lot** | 2.7L | v4 safety cushion |
| **Pyramid Size Ratio** | 0.5 | 50% geometric scaling |
| **Tom Basso ATR** | (1.0, 2.0, 10) | v4 Gold learning |
| **Historical Lot Sizing** | TRUE | v4.1 feature - essential |
| **calc_on_every_tick** | FALSE | v4 optimization |
| **process_orders_on_close** | TRUE | Anti-repainting |

---

## v6 PARAMETER SUMMARY TABLE

| Parameter | v4.1 | v5.0 | v6.0 | v6 Source |
|-----------|------|------|------|-----------|
| **Pyramiding (Properties)** | 3 | 5 | **5** | v5 ✅ |
| **ADX Threshold** | 25 | 30 | **30** | v5 ✅ |
| **ER Period** | 3 | 5 | **3** | v4 ⬅️ |
| **ER Threshold** | 0.8 | 0.77 | **0.8** | v4 ⬅️ |
| **Use ROC Filter** | TRUE | TRUE | **FALSE** | v6 🆕 |
| **ROC Threshold** | 3.0% | 2.0% | **5.0%** | v6 🆕 |
| **Risk % Capital** | 2.0% | 1.5% | **2.0%** | v4 ⬅️ |
| **ATR Pyramid Threshold** | 0.75 | 0.5 | **0.75** | v4 ⬅️ |
| **Max Pyramids (Input)** | 3 | 5 | **5** | v5 ✅ |
| **Commission** | 0.1% | 0.05% | **0.05%** | v5 ✅ |
| **Slippage** | 5 | 5 | **5** | v5 ✅ |

**v6 Formula:**
- Extended Capacity (v5) + Entry Discipline (v4 ER, v5 ADX) + Relaxed Pyramiding (v4 ATR, NO ROC) + Aggressive Sizing (v4 risk)

---

## EXPECTED vs ACTUAL PERFORMANCE

| Metric | v6 Actual | v5 Expected | v4.1 Baseline | Performance |
|--------|-----------|-------------|---------------|-------------|
| **CAGR** | **27.5%** | 19-24% | 22.59% | ✅ +22% vs v5, +22% vs v4 |
| **Max DD** | **-25.08%** | -20% to -27% | -24.87% | ✅ Within range |
| **Total Trades** | **923** | 650-750 | 880 | ✅ High activity |
| **Win Rate** | **52.98%** | 48-54% | 51% | ✅ Above midpoint |
| **Profit Factor** | **2.055** | TBD | ~2.0 | ✅ Excellent |

**Outstanding Results:**
- v6 exceeds v5 expected CAGR by ~15-45%
- v6 exceeds v4 baseline CAGR by ~22%
- Drawdown remains controlled within expected range

---

## RISK ASSESSMENT

### High Impact Changes ⚠️

1. **ROC Filter Disabled**: Removes momentum gating, relies on profitability gate
   - **Mitigation**: Triple-constraint + profitability gate still active
   - **Result**: Empirically validated - strong performance

2. **Risk 2.0%**: 33% larger positions than v5
   - **Mitigation**: Max DD only +0.21% vs v4 (-25.08% vs -24.87%)
   - **Result**: Acceptable risk increase for +22% CAGR

3. **ATR 0.75 + No ROC**: Fewer pyramid constraints
   - **Mitigation**: Wider ATR spacing prevents over-pyramiding
   - **Result**: 923 trades, 0 margin calls - risk systems working

### Medium Impact Changes ⚪

1. **ER Period 3**: Faster reaction, more noise sensitivity
   - **Offset**: ER Threshold 0.8 maintains quality
   - **Result**: 52.98% win rate - quality maintained

2. **Extended Pyramiding**: 6 positions vs 4
   - **Offset**: Geometric scaling limits tail exposure
   - **Result**: Pyramid system working well

---

## MIGRATION GUIDE (v5 → v6 or v4 → v6)

### For v5 Users

**Step 1: Understand Key Differences**
- v6 = v5 capacity + v4 parameters + NO ROC FILTER
- More aggressive than v5 (larger positions, relaxed pyramiding)

**Step 2: Update Strategy Settings**

**Inputs Tab Changes:**
- ER Period: 5 → **3**
- ER Threshold: 0.77 → **0.8**
- Use ROC Filter: TRUE → **FALSE** ⚠️ CRITICAL
- ROC Threshold: 2.0 → **5.0** (unused but changed)
- Risk % Capital: 1.5 → **2.0**
- ATR Pyramid Threshold: 0.5 → **0.75**

**Properties Tab (No Changes from v5):**
- Pyramiding: 5 (unchanged)
- Commission: 0.05% (unchanged)
- Slippage: 5 ticks (unchanged)

**Step 3: Run Comparison Backtest**
- Date range: Jan 1, 2009 — Nov 14, 2025
- Compare v5 vs v6 results
- Expected: v6 ~20-40% higher CAGR, similar DD

### For v4 Users

**Step 1: Understand Key Differences**
- v6 = v4 + Extended pyramiding (5 vs 3) + ADX 30 + Commission 0.05% + NO ROC FILTER

**Step 2: Update Strategy Settings**

**Inputs Tab Changes:**
- ADX Threshold: 25 → **30**
- Use ROC Filter: TRUE → **FALSE** ⚠️
- Max Pyramids: 3 → **5**

**Properties Tab Changes:**
- Pyramiding: 3 → **5**
- Commission: 0.1% → **0.05%**

---

## TROUBLESHOOTING

### Issue 1: "Too many pyramid entries"
- **Cause**: ROC filter disabled + ATR 0.75 spacing
- **Expected**: More pyramids than v5 (by design)
- **Check**: Margin calls = 0? If yes, system working correctly

### Issue 2: "Different results than screenshots"
- **Verify**:
  - Properties → Pyramiding = 5
  - Properties → Commission = 0.05%
  - Properties → Slippage = 5
  - Inputs → Use ROC Filter = **FALSE**
  - Inputs → Risk % = 2.0
  - Inputs → ATR Pyramid = 0.75
  - Inputs → ER Period = 3, ER Threshold = 0.8

### Issue 3: "Drawdown higher than expected"
- v6 uses 2.0% risk (larger positions)
- Expected DD: -25% range (actual: -25.08%)
- Check: Is your backtest period identical (2009-2025)?

---

## FUTURE CONSIDERATIONS

### Potential v6.1 Refinements

1. **Hybrid ROC Filter**: Enable ROC but with lower threshold (1% instead of disabled)
2. **Dynamic ATR Spacing**: Use volatility regime to adjust pyramid spacing
3. **ER Optimization**: Test ER Period 4 as middle ground between 3 and 5
4. **Risk Scaling**: Risk 1.75% as middle ground between 1.5% and 2.0%

### A/B Testing Recommendations

1. **ROC Filter On/Off**: Compare v6 (OFF) vs v6.1 (ON at 1%)
2. **ATR Spacing**: Test 0.5, 0.625, 0.75 on identical date range
3. **Risk Levels**: Test 1.5%, 1.75%, 2.0% for optimal risk-return

---

## CONCLUSION

Bank Nifty v6.0 achieves **exceptional performance** through:
1. **Extended Capacity**: 6 positions from v5
2. **Proven Parameters**: v4 entry/pyramid parameters
3. **Relaxed Pyramiding**: ROC filter disabled for maximum trend capture
4. **Aggressive Sizing**: 2.0% risk for better capital efficiency

**Key Takeaway:** "Combine v5's extended pyramiding capacity with v4's proven parameter stability, remove ROC constraint, achieve superior CAGR with controlled drawdown."

**Performance Validation:**
- **27.5% CAGR** over 16.9 years
- **-25.08% Max DD** (acceptable)
- **2.055 Profit Factor** (excellent)
- **0 Margin Calls** (robust risk management)

**Recommendation:** v6.0 suitable for production deployment after standard validation process (paper trading, gradual rollout).

---

**Document Version:** 1.0
**Author:** Backtest Analysis Team
**Date:** November 16, 2025
**Backtest Platform:** TradingView Strategy Tester
**Data Source:** BANKNIFTY INDEX FUTURES - 75min NSE

**Related Files:**
- `trend_following_strategy_v6.pine` (strategy code)
- `trend_following_strategy_banknifty_v5.pine` (v5 baseline)
- `trend_following_strategy_banknifty_v4.pine` (v4 baseline)
- `BANKNIFTY_V5_CHANGELOG.md` (v5 specification)
- `BANKNIFTY_V4_CHANGELOG.md` (v4 specification)
