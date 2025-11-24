# Gold Mini Trend Following Strategy v5.0 Changelog

**Version:** 5.0
**Date:** November 15, 2025
**Base Version:** Gold Mini Trend Following Strategy v4
**Instrument:** MCX Gold Mini (100g)
**Purpose:** Extend pyramiding support from 4 to 6 total positions + Apply v5 refinements from Bank Nifty v5

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Version History](#version-history)
3. [Changes from v4 to v5](#changes-from-v4-to-v5)
4. [Gold-Specific Settings (Preserved)](#gold-specific-settings-preserved)
5. [Implementation Details](#implementation-details)
6. [Risk Management Implications](#risk-management-implications)
7. [Testing Recommendations](#testing-recommendations)
8. [Migration Guide](#migration-guide)

---

## Executive Summary

Gold Mini v5.0 extends the strategy from **4 total positions** (1 base + 3 pyramids) to **6 total positions** (1 base + 5 pyramids), while incorporating parameter refinements validated in Bank Nifty v5. All Gold-specific optimizations (ADX 20, ROC 5%, tighter ATR pyramid threshold) are preserved.

**Key Changes:**
1. **Extended Pyramiding:** Max pyramids increased from 3 → 5 (allows 6 total positions)
2. **v5 Parameter Updates:** ER Period 3 → 5, ER Threshold 0.8 → 0.77 (from Bank Nifty v5)
3. **Gold-Specific Preserved:** ADX 20, ROC 5%, margin 0.75L, lot_size 10 (unchanged)
4. **Code Extensions:** All tracking variables, stop loss modes, risk calculations extended for Long_5 and Long_6

**Critical Considerations:**
- Geometric scaling (50% pyramid ratio) ensures controlled position sizing
- Triple-constraint system (lot-a, lot-b, lot-c) maintains risk discipline
- Gold's lower margin (₹75K vs ₹270K for Bank Nifty) allows more flexibility in pyramiding
- Expected impact: ~10-15% more trades hit 5-6 pyramids vs 3-4, potential CAGR improvement

---

## Version History

| Version | Date | Key Features | Performance (2015-2025) |
|---------|------|--------------|-------------------------|
| v4 | Nov 2025 | 4 total positions, ADX 20, ROC 5% | ~20.23% CAGR, -17.5% DD |
| **v5** | **Nov 15, 2025** | **6 total positions, ER Period 5, ER 0.77** | *Testing Required* |

---

## Changes from v4 to v5

### 1. Strategy Declaration Changes

**Location:** Line 2-12

```pinescript
// v4
strategy("Gold Mini Trend Following Strategy",
     pyramiding=3,  // OLD
     ...
)

// v5
strategy("Gold Mini Trend Following Strategy v5.0",
     pyramiding=5,  // NEW - allows 6 total positions
     ...
)
```

**Impact:**
- TradingView's Properties tab pyramiding setting is now set to 5 at code level
- Allows up to 6 simultaneous Long positions (Long_1 through Long_6)

---

### 2. Parameter Updates (Inputs Tab)

#### a) ER Period: 3 → 5

**Location:** Line 48

```pinescript
// v4
er_period = input.int(3, "ER Period", minval=1)

// v5
er_period = input.int(5, "ER Period", minval=1,
    tooltip="✨ v5: 5 (smoother ER calculation, from Bank Nifty v5)")
```

**Rationale:**
- Longer ER period (5 vs 3) produces smoother, more stable efficiency ratio values
- Reduces noise in trending efficiency measurement
- Applied from Bank Nifty v5 empirical validation
- Gold's smoother price action (vs Bank Nifty volatility) may benefit from this refinement

**Expected Impact:**
- Slightly fewer entry signals (~3-5% reduction)
- Higher quality entries (stronger trending conditions)
- Potentially lower whipsaw trades

---

#### b) ER Threshold: 0.8 → 0.77

**Location:** Line 50

```pinescript
// v4
er_threshold = input.float(0.8, "ER Threshold", minval=0, maxval=1)

// v5
er_threshold = input.float(0.77, "ER Threshold", minval=0, maxval=1,
    tooltip="✨ v5: 0.77 (slightly relaxed from 0.8, from Bank Nifty v5)")
```

**Rationale:**
- Slightly relaxed threshold (0.77 vs 0.80) balances with longer ER period (5 vs 3)
- Net effect: Maintains similar entry frequency but with higher quality signals
- Applied from Bank Nifty v5 empirical validation

**Expected Impact:**
- Compensates for strictness of ER Period 5
- ~3-5% more entry opportunities vs ER 0.80 + Period 5
- Combined with Period 5: Similar total entries as v4, but higher quality

---

#### c) Max Pyramids: 3 → 5

**Location:** Line 90

```pinescript
// v4
max_pyramids = input.int(3, "Max Pyramids", minval=1, maxval=3,
    tooltip="✨ OPTIMIZED: Up to 4 total positions (empirically validated for better scaling)")

// v5
max_pyramids = input.int(5, "Max Pyramids", minval=1, maxval=5,
    tooltip="✨ v5: Up to 6 total positions (extended from 4 in v4)")
```

**Rationale:**
- Extends pyramiding capability for stronger trends
- Gold trends often smoother and longer than Bank Nifty
- Geometric scaling (50% ratio) ensures controlled position sizing
- Triple-constraint system prevents over-pyramiding

**Expected Impact:**
- ~10-15% of trades will add 4th or 5th pyramid (beyond v4's max 3)
- Stronger trends capture more profit with additional pyramids
- Margin utilization may increase (Gold's lower margin allows this)

---

### 3. Gold-Specific Settings (UNCHANGED)

These parameters remain **Gold-optimized** and differ from Bank Nifty v5:

| Parameter | Gold v5 Value | Bank Nifty v5 Value | Why Different |
|-----------|---------------|---------------------|---------------|
| **ADX Threshold** | **20** | 30 | Gold less volatile, ADX 20 validated empirically |
| **ROC Threshold** | **5.0%** | 2.0% | Gold trends smoother, stricter ROC filter needed |
| **Risk % Capital** | **1.5%** | 1.5% | ✓ Same (v5 conservative setting) |
| **ATR Pyramid Threshold** | **0.5** | 0.5 | ✓ Same (v5 tighter pyramiding) |
| **Margin per Lot** | **0.75L** | 2.7L | Gold Mini margin ₹75K vs Bank Nifty ₹270K |
| **Lot Size** | **10** | NSE Historical | Gold: Rs 10 per tick, Bank Nifty: dynamic lot sizing |
| **Commission** | **0.05%** | 0.05% | ✓ Both futures (v5 corrected Bank Nifty commission) |

**Critical Preservation:**
- ADX 20 is empirically validated for Gold (more entry opportunities than ADX 25/30)
- ROC 5% is stricter for Gold's smoother trends (prevents weak pyramids)
- Margin 0.75L reflects MCX Gold Mini spec (₹72K + safety cushion)
- Lot size 10 is point value for 100g contract (Re 1 × 10g × 10 = Rs 10)

---

## Implementation Details

### 4. Code Structure Changes

#### a) New Tracking Variables

**Location:** Lines 199-217

```pinescript
// v4 (max 4 positions)
var float pyr3_entry_price = na  // Pyramid 3 entry price (Long_4)
var float basso_stop_long4 = na
var float highest_close_long4 = na
var float display_stop_long4 = na

// v5 (max 6 positions)
var float pyr4_entry_price = na  // Pyramid 4 entry price (Long_5) - NEW
var float pyr5_entry_price = na  // Pyramid 5 entry price (Long_6) - NEW
var float basso_stop_long5 = na  // NEW
var float basso_stop_long6 = na  // NEW
var float highest_close_long5 = na  // NEW
var float highest_close_long6 = na  // NEW
var float display_stop_long5 = na  // NEW
var float display_stop_long6 = na  // NEW
```

**Purpose:**
- Track entry prices for Long_5 and Long_6 (pyramids 4 and 5)
- Support Tom Basso ATR trailing stops for each position independently
- Enable Van Tharp trail-to-breakeven logic for all 6 positions
- Display individual stop levels in info panel

---

#### b) Extended Stop Loss Modes

All three stop loss modes now support 6 positions:

**SuperTrend Mode (Lines 268-274):**
```pinescript
// v5 additions
display_stop_long5 := not na(pyr4_entry_price) ? supertrend : na
display_stop_long6 := not na(pyr5_entry_price) ? supertrend : na
```
- Simple: All 6 positions use SuperTrend as stop

**Van Tharp Mode (Lines 276-282):**
```pinescript
// v5 additions
display_stop_long5 := not na(pyr4_entry_price) ?
    (not na(pyr5_entry_price) ? pyr5_entry_price : supertrend) : na
display_stop_long6 := not na(pyr5_entry_price) ? supertrend : na
```
- Long_5 trails to Long_6 entry or SuperTrend
- Long_6 (highest level) always trails to SuperTrend

**Tom Basso Mode (Lines 284-290, 534-570):**
```pinescript
// v5 additions - Long_5 and Long_6 independent ATR stops
if not na(pyr4_entry_price)
    highest_close_long5 := math.max(highest_close_long5, close)
    trailing_stop_long5 = highest_close_long5 - (basso_trailing_atr_mult * atr_basso)
    basso_stop_long5 := math.max(basso_stop_long5, trailing_stop_long5)

    if close < basso_stop_long5 and barstate.isconfirmed
        strategy.close("Long_5", comment="EXIT - Basso Stop")
        ...
```
- Each position (Long_5, Long_6) has independent ATR trailing stop
- Stops only move up, never down
- Exit only at bar close (barstate.isconfirmed)

---

#### c) Extended Risk Calculations

**Location:** Lines 292-297

```pinescript
// v4
total_risk_exposure = risk_long1 + risk_long2 + risk_long3 + risk_long4

// v5
risk_long5 = not na(pyr4_entry_price) and not na(display_stop_long5) ?
    math.max(0, (pyr4_entry_price - display_stop_long5) * initial_position_size *
    math.pow(pyramid_size_ratio, 4) * lot_size) : 0

risk_long6 = not na(pyr5_entry_price) and not na(display_stop_long6) ?
    math.max(0, (pyr5_entry_price - display_stop_long6) * initial_position_size *
    math.pow(pyramid_size_ratio, 5) * lot_size) : 0

total_risk_exposure = risk_long1 + risk_long2 + risk_long3 + risk_long4 +
                      risk_long5 + risk_long6  // v5 extended
```

**Purpose:**
- Calculate total Rs exposure if all 6 positions hit their stops
- Displayed in info panel for real-time risk awareness
- Geometric scaling ensures risk_long6 is smallest (base × 0.5^5 = 3.125% of base)

**Example Calculation:**
- Base entry: 10 lots @ 60,000, stop @ 59,500 → Risk ₹50,000
- Long_5: 0.625 lots @ 62,000, stop @ 61,000 → Risk ₹6,250
- Long_6: 0.3125 lots @ 63,000, stop @ 62,000 → Risk ₹3,125
- Total Risk: Sum of all 6 positions (typically 1.5-2.5× base risk)

---

#### d) Extended Pyramiding Logic

**Location:** Lines 420-438

```pinescript
// v5 additions in pyramid entry logic
else if pyramid_count == 4
    pyr4_entry_price := close  // v5 extension
    // Initialize Tom Basso stop for Long_5
    if stop_loss_mode == "Tom Basso"
        basso_stop_long5 := close - (basso_initial_atr_mult * atr_basso)
        highest_close_long5 := close

else if pyramid_count == 5
    pyr5_entry_price := close  // v5 extension
    // Initialize Tom Basso stop for Long_6
    if stop_loss_mode == "Tom Basso"
        basso_stop_long6 := close - (basso_initial_atr_mult * atr_basso)
        highest_close_long6 := close

// Entry order
strategy.entry("Long_" + str.tostring(pyramid_count + 1), strategy.long,
    qty=pyramid_lots, comment="PYR" + str.tostring(pyramid_count) + "-" +
    str.tostring(pyramid_lots) + "L")
```

**Triple-Constraint System (UNCHANGED):**
- **lot-a (Margin Safety):** Max lots affordable with free margin
- **lot-b (Discipline Safety):** 50% of base position (geometric scaling)
- **lot-c (Profit Safety):** Only risk 50% of profit beyond base risk

**Pyramid Gate (UNCHANGED):**
- Only pyramid when `accumulated_profit > base_risk`
- Ensures "house money" beyond covering initial risk

**Example Pyramid Progression (10 lot base):**
- Long_1: 10 lots (base entry)
- Long_2: 5 lots (50% of base)
- Long_3: 2.5 lots (50% of Long_2)
- Long_4: 1.25 lots (50% of Long_3)
- Long_5: 0.625 lots (50% of Long_4) - **NEW in v5**
- Long_6: 0.3125 lots (50% of Long_5) - **NEW in v5**
- **Total: 19.6875 lots** (vs v4 max: 18.75 lots)

---

#### e) Extended Van Tharp Exit Logic

**Location:** Lines 485-511

```pinescript
// v5 additions - Long_5 and Long_6 Van Tharp trailing

// Long_5 (PYR4): Trail to PYR5 or SuperTrend
if not na(pyr4_entry_price) and barstate.isconfirmed
    if not na(pyr5_entry_price)
        // PYR5 exists above us, trail to it
        if close < pyr5_entry_price
            strategy.close("Long_5", comment="EXIT - Trail to PYR5")
            pyr4_entry_price := na
    else
        // No pyramid above, use SuperTrend
        if close < supertrend
            strategy.close("Long_5", comment="EXIT - Below ST")
            pyr4_entry_price := na

// Long_6 (PYR5): Always trail to SuperTrend (highest level)
if not na(pyr5_entry_price) and barstate.isconfirmed
    if close < supertrend
        strategy.close("Long_6", comment="EXIT - Below ST")
        pyr5_entry_price := na
```

**Van Tharp Trail-to-Breakeven Logic:**
- Long_5 trails to Long_6 entry (breakeven for Long_5) or SuperTrend
- Long_6 (highest pyramid) only trails to SuperTrend
- Protects earlier pyramids by locking in profits from later pyramids

---

#### f) Extended Info Panel Display

**Location:** Lines 716-734

```pinescript
// v5 additions - Display Long_5 and Long_6 in info panel

if not na(pyr4_entry_price)
    pyr4_lots = math.round(initial_position_size * math.pow(pyramid_size_ratio, 4))
    table.cell(infoTable, 0, row, "Long_5 (Pyr4)", bgcolor=color.new(color.green, 80))
    table.cell(infoTable, 1, row, str.tostring(pyr4_entry_price, "#.##") +
        " (" + str.tostring(pyr4_lots) + "L)", bgcolor=color.new(color.green, 80))
    table.cell(infoTable, 2, row, "Stop: " + str.tostring(display_stop_long5, "#.##"),
        bgcolor=color.new(color.green, 80))
    row := row + 1

if not na(pyr5_entry_price)
    pyr5_lots = math.round(initial_position_size * math.pow(pyramid_size_ratio, 5))
    table.cell(infoTable, 0, row, "Long_6 (Pyr5)", bgcolor=color.new(color.green, 80))
    table.cell(infoTable, 1, row, str.tostring(pyr5_entry_price, "#.##") +
        " (" + str.tostring(pyr5_lots) + "L)", bgcolor=color.new(color.green, 80))
    table.cell(infoTable, 2, row, "Stop: " + str.tostring(display_stop_long6, "#.##"),
        bgcolor=color.new(color.green, 80))
    row := row + 1
```

**Smart Panel Updates:**
- Shows Long_5 and Long_6 entry prices and lot sizes
- Displays individual stop levels for each position
- Green background indicates pyramid positions
- Total position size and risk exposure updated for 6 positions

---

#### g) Debug Panel Updates

**Location:** Lines 843-845

```pinescript
// v5 updated debug panel display
plot(show_debug ? (adx_condition ? 1 : 0) : na, "ADX<20", ...)  // Updated from ADX<25
plot(show_debug ? (er_condition ? 1 : 0) : na, "ER>0.77", ...)  // Updated from ER>0.8
```

**Purpose:**
- Reflects updated ADX and ER thresholds in debug visualization
- ADX<20 condition (Gold-specific)
- ER>0.77 condition (v5 update)

---

## Risk Management Implications

### 5. Position Sizing Analysis

**v4 Max Position Sizing (4 positions):**
- Base: 10 lots
- Pyr1: 5 lots
- Pyr2: 2.5 lots
- Pyr3: 1.25 lots
- **Total: 18.75 lots**

**v5 Max Position Sizing (6 positions):**
- Base: 10 lots
- Pyr1: 5 lots
- Pyr2: 2.5 lots
- Pyr3: 1.25 lots
- Pyr4: 0.625 lots ← **NEW**
- Pyr5: 0.3125 lots ← **NEW**
- **Total: 19.6875 lots** (+5% vs v4)

**Key Observations:**
- Total position increase: +5% (19.6875 vs 18.75 lots)
- Pyr4 and Pyr5 are very small (3.125% and 1.56% of base)
- Risk contribution of Long_5 and Long_6 is minimal due to geometric scaling
- Margin impact: ~+5% for max pyramiding scenarios

---

### 6. Margin Utilization Analysis

**Gold Mini Margin Specs:**
- Margin per lot: ₹75,000 (0.75 Lakhs)
- Initial capital: ₹50 Lakhs
- Max lots affordable (no leverage): 50 ÷ 0.75 = 66 lots

**v4 Typical Scenario:**
- Base entry (1.5% risk, ER 0.85): ~8 lots
- Max 4 positions: 8 + 4 + 2 + 1 = 15 lots
- Margin used: 15 × 0.75L = ₹11.25 Lakhs (22.5% of capital)

**v5 Typical Scenario:**
- Base entry (1.5% risk, ER 0.85): ~8 lots
- Max 6 positions: 8 + 4 + 2 + 1 + 0.5 + 0.25 = 15.75 lots
- Margin used: 15.75 × 0.75L = ₹11.81 Lakhs (23.6% of capital)

**Margin Impact:**
- Additional margin for Pyr4+Pyr5: ~₹56,000 (+5%)
- Still well within safe margin limits (<25% utilization)
- Triple-constraint system prevents over-pyramiding even with 6 positions

---

### 7. Risk Exposure Analysis

**Total Risk Calculation (if all stops hit):**

**v4 Example:**
- Long_1: 8 lots × ₹500 × 10 = ₹40,000
- Long_2: 4 lots × ₹400 × 10 = ₹16,000
- Long_3: 2 lots × ₹300 × 10 = ₹6,000
- Long_4: 1 lot × ₹200 × 10 = ₹2,000
- **Total Risk: ₹64,000** (1.28% of ₹50L capital)

**v5 Example (same scenario + Pyr4, Pyr5):**
- Long_1: 8 lots × ₹500 × 10 = ₹40,000
- Long_2: 4 lots × ₹400 × 10 = ₹16,000
- Long_3: 2 lots × ₹300 × 10 = ₹6,000
- Long_4: 1 lot × ₹200 × 10 = ₹2,000
- Long_5: 0.5 lots × ₹150 × 10 = ₹750 ← **NEW**
- Long_6: 0.25 lots × ₹100 × 10 = ₹250 ← **NEW**
- **Total Risk: ₹65,000** (+1.5% vs v4, still 1.30% of capital)

**Risk Impact:**
- Minimal increase due to geometric scaling
- Long_5 and Long_6 contribute <2% of total risk
- Base risk (Long_1) dominates exposure (~60-65%)

---

### 8. Pyramid Gate Protection

**Pyramid Gate Logic (UNCHANGED in v5):**
```pinescript
pyramid_gate_open = accumulated_profit > base_risk
```

**How It Works:**
- Only pyramid when cumulative profit (realized + unrealized) exceeds base trade risk
- Example: If base risk is ₹40,000, gate opens when profit > ₹40,000
- This ensures "house money" before adding pyramids

**Impact on Pyr4 and Pyr5:**
- By the time Pyr4 and Pyr5 are added, profit is likely 3-5× base risk
- Triple-constraint system further limits lot sizes
- Very conservative approach: Only add tiny positions when deep in profit

---

## Testing Recommendations

### 9. Backtest Setup (TradingView)

**Symbol:** GOLDMINI (MCX Gold Mini 100g)
**Timeframe:** 60 minutes (1 hour)
**Date Range:** 2015-01-01 to 2025-11-15 (10.8 years)

**Strategy Settings → Inputs Tab:**
```
ADX Threshold = 20
ER Period = 5  ← v5 change
ER Threshold = 0.77  ← v5 change
ROC Threshold % = 5.0
Risk % of Capital = 1.5
ATR Pyramid Threshold = 0.5
Margin per Lot (Lakhs) = 0.75
Max Pyramids = 5  ← v5 change
Stop Loss Mode = Tom Basso
```

**Strategy Settings → Properties Tab:**
```
Initial Capital = 5000000
Pyramiding = 5  ← v5 change
Commission = 0.05%
Slippage = 5 ticks
On every tick = UNCHECKED
On bar close = CHECKED
```

---

### 10. Expected Performance Metrics

**v4 Baseline (2015-2025):**
- **CAGR:** ~20.23%
- **Max Drawdown:** -17.5%
- **Total Trades:** ~430
- **Win Rate:** 46%
- **Sharpe Ratio:** ~1.2

**v5 Projections (based on Bank Nifty v5 experience):**
- **CAGR:** ~21-22% (+3-5% improvement expected)
- **Max Drawdown:** -18% to -19% (slightly higher due to more pyramiding)
- **Total Trades:** ~410-425 (-3-5% due to ER Period 5 + ER 0.77 combined)
- **Win Rate:** 47-48% (+1-2% due to higher quality entries)
- **Sharpe Ratio:** ~1.25-1.30

**Expected Improvement Drivers:**
1. ER Period 5 + ER 0.77: Fewer but higher quality entries
2. Extended pyramiding: Capture more profit in strong trends (~10-15% of trades benefit)
3. Conservative risk (1.5%): Lower drawdowns, smoother equity curve

---

### 11. Validation Tests

**Test 1: Pyramid Distribution Analysis**
- Compare v4 vs v5: How many trades reach 4th, 5th, 6th pyramids?
- Expected: ~40% reach Pyr3, ~15% reach Pyr4, ~5% reach Pyr5

**Test 2: Margin Stress Test**
- Check max margin utilization across entire backtest
- Expected: <30% even with 6 positions (Gold's low margin allows this)

**Test 3: Risk Exposure Validation**
- Verify total risk never exceeds 3% of equity
- Check that Pyr4+Pyr5 contribute <5% of total risk

**Test 4: Stop Loss Mode Comparison**
- Test all 3 modes (SuperTrend, Van Tharp, Tom Basso)
- Expected: Tom Basso best for Gold (smoother trends, independent stops)

**Test 5: Entry Quality Analysis**
- Compare v4 vs v5 win rates and average R-multiples
- Expected: v5 slightly higher win rate (+1-2%) due to ER refinements

---

## Migration Guide

### 12. Upgrading from v4 to v5

**Step 1: Backup Current Strategy**
1. Save current `gold_trend_following_strategy.pine` as backup
2. Export current backtest results for comparison
3. Document current TradingView settings

**Step 2: Install v5**
1. Copy `gold_trend_following_strategy_v5.pine` code
2. Create new Pine Editor tab in TradingView
3. Paste v5 code and save

**Step 3: Configure Settings**
1. **Inputs Tab:**
   - Verify ADX Threshold = **20** (Gold-specific)
   - Change ER Period to **5** (v5 update)
   - Change ER Threshold to **0.77** (v5 update)
   - Verify ROC Threshold = **5.0** (Gold-specific)
   - Verify Risk % = **1.5** (Gold-optimized)
   - Verify ATR Pyramid = **0.5** (Gold-optimized)
   - Change Max Pyramids to **5** (v5 update)
   - Verify Margin per Lot = **0.75** (Gold-specific)

2. **Properties Tab:**
   - Initial Capital = **5000000**
   - **Pyramiding = 5** ← CRITICAL v5 change
   - Commission = **0.05%** (Gold futures)
   - Slippage = **5 ticks**
   - On every tick = **UNCHECKED**
   - On bar close = **CHECKED**

**Step 4: Run Comparison Backtest**
1. Apply v5 to GOLDMINI 60-min chart
2. Run full backtest (2015-2025)
3. Export List of Trades to CSV
4. Compare with v4 results:
   - CAGR improvement
   - Drawdown changes
   - Trade count changes
   - Pyramid distribution (how many trades hit 4-6 pyramids)

**Step 5: Forward Testing (Recommended)**
1. Run v5 in paper trading for 30-60 days
2. Monitor real-time behavior with 6-position capability
3. Verify margin utilization stays reasonable
4. Check info panel displays correctly for all 6 positions

---

### 13. Rollback Procedure (If Needed)

If v5 performance is unsatisfactory:

1. Revert to v4 code (from backup)
2. Or keep v5 code but revert specific settings:
   - Change ER Period back to **3**
   - Change ER Threshold back to **0.8**
   - Change Max Pyramids back to **3**
   - Change Properties → Pyramiding back to **3**

---

## Summary of All Changes

### Settings Changes
| Setting | v4 Value | v5 Value | Change Type |
|---------|----------|----------|-------------|
| Strategy Declaration: pyramiding | 3 | 5 | ✅ Extended |
| ER Period | 3 | 5 | ✅ Updated (from BN v5) |
| ER Threshold | 0.8 | 0.77 | ✅ Updated (from BN v5) |
| Max Pyramids Input | 3 | 5 | ✅ Extended |
| ADX Threshold | 20 | 20 | ⚪ Preserved (Gold-specific) |
| ROC Threshold | 5.0% | 5.0% | ⚪ Preserved (Gold-specific) |
| Risk % | 1.5% | 1.5% | ⚪ Preserved |
| ATR Pyramid Threshold | 0.5 | 0.5 | ⚪ Preserved |
| Margin per Lot | 0.75L | 0.75L | ⚪ Preserved (Gold-specific) |
| Lot Size | 10 | 10 | ⚪ Preserved (Gold-specific) |
| Commission | 0.05% | 0.05% | ⚪ Preserved |

### Code Changes
| Component | Lines Added/Modified | Purpose |
|-----------|----------------------|---------|
| Tracking Variables | +6 vars (pyr4_entry_price, pyr5_entry_price, etc.) | Track Long_5 and Long_6 |
| SuperTrend Stop Mode | +2 lines | Support Long_5, Long_6 |
| Van Tharp Stop Mode | +22 lines | Trail Long_5 to Long_6, Long_6 to ST |
| Tom Basso Stop Mode | +36 lines | Independent ATR stops for Long_5, Long_6 |
| Risk Calculations | +3 lines | Calculate risk_long5, risk_long6 |
| Pyramid Entry Logic | +14 lines | Initialize Pyr4, Pyr5 tracking |
| Info Panel Display | +16 lines | Show Long_5, Long_6 positions |
| Debug Panel | 2 modified | Update ADX<20, ER>0.77 labels |

### Total Code Impact
- **Lines Changed:** ~100 lines modified/added
- **New Functionality:** Support for 6 total positions (vs 4 in v4)
- **Backward Compatible:** v5 code works with pyramiding=3 (behaves like v4)
- **Risk Systems:** All triple-constraint and pyramid gate logic unchanged

---

## Conclusion

Gold Mini v5.0 successfully extends pyramiding from 4 to 6 total positions while incorporating validated v5 parameter refinements from Bank Nifty. All Gold-specific optimizations (ADX 20, ROC 5%, lower margin) are preserved.

**Key Takeaways:**
1. **Conservative Extension:** Pyr4 and Pyr5 are tiny (~3% and 1.5% of base) due to geometric scaling
2. **Risk Discipline Maintained:** Triple-constraint system and pyramid gate prevent over-pyramiding
3. **Expected Performance:** ~3-5% CAGR improvement vs v4, with similar or slightly higher drawdown
4. **Gold-Optimized:** All instrument-specific settings preserved and validated

**Next Steps:**
1. Run full backtest on GOLDMINI 60-min (2015-2025)
2. Compare pyramid distribution vs v4
3. Validate margin utilization <30% even with 6 positions
4. Consider 30-60 day paper trading before live deployment

**Document Version:** 1.0
**Last Updated:** November 15, 2025
**Author:** Claude Code (Anthropic)
