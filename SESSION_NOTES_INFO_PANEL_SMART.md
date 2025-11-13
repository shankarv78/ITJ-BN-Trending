# TradingView Pine Script - Info Panel Implementation & Smart Panel Development

**Date:** November 12, 2025
**Session Summary:** Troubleshooting info panel visibility, implementing margin-aware pyramiding, and creating smart context-aware info panel

---

## Table of Contents
1. [Initial Problem](#initial-problem)
2. [Root Cause Analysis](#root-cause-analysis)
3. [Solutions Implemented](#solutions-implemented)
4. [Margin Management System](#margin-management-system)
5. [Smart Info Panel](#smart-info-panel)
6. [File Structure](#file-structure)
7. [Key Settings](#key-settings)
8. [Bug Fixes](#bug-fixes)
9. [Future Enhancements](#future-enhancements)

---

## Initial Problem

### Issue
Info panel (table) was not visible in TradingView despite being coded correctly.

### User Description
> "The info panel is now showing up now, not sure what happened to it. It was showing all conditions earlier in a table on the side, but it disappeared now without any reason."

### Environment
- **Strategy**: Trend Following Strategy (Bank Nifty)
- **Timeframe**: 75-minute
- **Capital**: ₹50L (5 million)
- **Lot Size**: 35 (synthetic futures: ATM PE Sell + ATM CE Buy)
- **Pyramiding**: Up to 3 pyramids (4 total positions)

---

## Root Cause Analysis

### Problem 1: Overlay Setting
**File**: `trend_following_strategy.pine` (line 3)
- **Issue**: `overlay=false` placed strategy in separate pane below chart
- **Impact**: Table rendered in lower pane, not visible on main chart
- **Solution**: Changed to `overlay=true`

### Problem 2: calc_on_every_tick Setting
**File**: `trend_following_strategy.pine` (line 8)
- **Issue**: `calc_on_every_tick=false`
- **Impact**: Script only recalculated at bar close (every 75 minutes)
  - Table only updated when candle closed
  - On 75-min timeframe, could wait 0-74 minutes with no table visible
- **Solution**: Changed to `calc_on_every_tick=true`
  - Table now updates in real-time
  - Trades still execute at bar close (`process_orders_on_close=true`)

### Problem 3: Table Delete/Recreate Pattern
**Initial approach**: Used `table.delete()` then immediately `table.new()`
- **Issue**: In Pine Script v5, this pattern sometimes fails
- **Solution**: Changed to `var table infoTable = na` and recreate without delete

---

## Solutions Implemented

### 1. Basic Table Visibility Fix

**Changes Made** (lines 3, 8, 480):
```pine
strategy("Trend Following Strategy",
     overlay=true,              // ✓ Changed from false
     calc_on_every_tick=true,   // ✓ Changed from false
     ...
)

// Table creation
var table infoTable = na
bgcolor(barstate.islast ? color.new(color.yellow, 90) : na, title="Table Debug Marker")

if barstate.islast
    infoTable := table.new(position.top_right, 3, 19, border_width=2, ...)
```

**Result**: Table now visible and updates in real-time

---

### 2. R-Multiple Calculation Bug Fix

**Problem**: Open P&L was showing "34.3R" when profit was only ₹0.34L
- **Expected**: 0.34R (₹34,000 profit ÷ ₹100,000 risk)
- **Actual**: 34.3R (incorrect × 100 multiplication)

**Fix** (line 195):
```pine
// Before (WRONG):
unrealized_pnl_percent = strategy.position_size > 0 ? (unrealized_pnl / (equity_high * (risk_percent / 100))) * 100 : 0

// After (CORRECT):
unrealized_pnl_r = strategy.position_size > 0 ? unrealized_pnl / (equity_high * (risk_percent / 100)) : 0
```

**What is R?**
- **R** = Risk per trade (Van Tharp terminology)
- **1R** = Initial risk amount (2% of capital = ₹1L = ₹100,000)
- **0.34R** = Profit is 34% of initial risk

---

### 3. Date Filter Implementation

**Requirement**: Start tracking from specific date (Nov 11, 2025) to avoid historical trades

**Implementation** (lines 83-84, 151):
```pine
// Inputs
use_start_date = input.bool(true, "Use Start Date Filter", tooltip="...")
start_date = input.time(timestamp("11 Nov 2025 00:00 +0000"), "Trade Start Date", tooltip="...")

// Filter logic
date_filter = use_start_date ? time >= start_date : true
long_entry = rsi_condition and ema_condition and dc_condition and adx_condition and er_condition and st_condition and not_doji and date_filter
```

**Result**: Strategy only takes trades from Nov 11, 2025 onwards

---

## Margin Management System

### Problem Identified

**User Observation**:
> "For current open position of 12 base position and 6 lots 1st pyramid, it's already consuming 47L capital as margin."

**Issue**: Pyramiding logic calculated position size based on **RISK (2%)** but didn't check **MARGIN AVAILABILITY**
- Synthetic futures require ~₹2.6L margin per lot
- 18 lots = ₹46.8L margin (93.6% of capital!)
- Only ₹3.2L remaining, but strategy tried to add 3rd pyramid

### Solution: Margin-Aware Pyramiding

**New Inputs** (lines 62-65):
```pine
use_margin_check = input.bool(true, "Enable Margin Check", tooltip="...")
max_margin_available = input.float(50.0, "Max Margin Available (Lakhs)", ...)
margin_per_lot = input.float(2.6, "Margin per Lot (Lakhs)", ...)
```

**Margin Tracking** (lines 206-209):
```pine
current_margin_used_display = strategy.position_size * margin_per_lot
margin_remaining = max_margin_available - current_margin_used_display
margin_utilization_pct = (current_margin_used_display / max_margin_available) * 100
```

**Pyramiding Check** (lines 250-260):
```pine
// Before pyramiding, check margin
current_margin_used = strategy.position_size * margin_per_lot
pyramid_margin_required = pyramid_lots * margin_per_lot
total_margin_after_pyramid = current_margin_used + pyramid_margin_required

// Only pyramid if sufficient margin
margin_available = use_margin_check ? total_margin_after_pyramid <= max_margin_available : true
pyramid_trigger = atr_moves >= atr_pyramid_threshold and position_is_profitable and margin_available
```

**Display** (Info Table rows 19-20):
- **Margin Used**: ₹46.8L (93.6%) 🔴 Red if >90%
- **Margin Free**: ₹3.2L (Available)

---

## Smart Info Panel

### Problem
Original info panel showed ALL information always (23 rows):
- Indicators (8 rows)
- Entry conditions
- Position info
- Capital details
- Margin info

**User Request**:
> "Create an option to selectively display running trade information only after trade has entered... only when not in trade, the indicator values need to be displayed."

### Solution: Context-Aware Smart Panel

**File Created**: `trend_following_strategy_smart.pine`

**New Toggle** (lines 55-56):
```pine
smart_panel = input.bool(true, "Smart Info Panel", tooltip="Show indicators when flat, trade info when in position")
show_all_info = input.bool(false, "Show All Info (Debug)", tooltip="Show both indicators and trade info always")
```

### Smart Panel Behavior

#### When **NOT in Trade** (Flat Position):
Shows **ENTRY CONDITIONS** (12 rows):
```
┌─────────────┬────────┬──────────┐
│ Indicator   │ Value  │ Status   │
├─────────────┼────────┼──────────┤
│ Close       │ 58566  │ Current  │
│ RSI(6)      │ 74.58  │ ✓ >70    │
│ EMA(200)    │ 57111  │ ✓ Above  │
│ DC Upper    │ 58650  │ ✗ Below  │
│ ADX(30)     │ 9.91   │ ✓ <25    │
│ ER(3)       │ 1.00   │ ✓ >0.8   │
│ SuperTrend  │ 58291  │ ✓ Above  │
│ Doji Check  │ 0.2    │ ✓ Not    │
│ ENTRY       │ WAITING│ NO POS   │
│ Capital     │ ₹50L   │ Initial  │
│ Lot Size    │ 11 Lots│ If entry │
│ Margin Avl  │ ₹50L   │ Ready    │
└─────────────┴────────┴──────────┘
```

#### When **IN Trade**:
Shows **TRADE MANAGEMENT** (15 rows):
```
┌──────────────┬────────────┬─────────────┐
│ Position     │ Value      │ Status      │
├──────────────┼────────────┼─────────────┤
│ ENTRY SIGNAL │ WAITING    │ IN TRADE    │
│ Long_1 Entry │ 57500 (12L)│ Stop: 58291 │
│ Long_2 Pyr1  │ 57800 (6L) │ Stop: 58291 │
│ Long_3 Pyr2  │ 58000 (3L) │ Stop: 58291 │
│ Total Pos    │ 21 Lots    │ @ 58566     │
│ Risk Exposure│ ₹1.2L      │ If stop hit │
│ Open P&L     │ ₹0.34L     │ 0.34R       │
│ Margin Used  │ ₹54.6L     │ 109.2% 🔴   │
│ Margin Free  │ -₹4.6L     │ 2/3 Pyrs    │
└──────────────┴────────────┴─────────────┘
```

### Key Features of Smart Panel

1. **Stop Loss Display**
   - Shows current SL for each position
   - Adapts to mode: SuperTrend / Van Tharp / Tom Basso

2. **Risk Exposure**
   - Calculates total ₹ loss if ALL stops hit on current candle
   - Formula: `(Entry Price - Stop Price) × Lots × Lot Size`

3. **Position Breakdown**
   - Each pyramid entry shown separately with lots and stop
   - Color coded: Blue (initial), Green (pyramids)

4. **Margin Monitoring**
   - Color coded: Green (<75%), Orange (75-90%), Red (>90%)
   - Shows pyramids used (e.g., "2/3 Pyrs")

---

## File Structure

### Current Files

```
/Users/shankarvasudevan/claude-code/ITJ-BN-Trending/
├── trend_following_strategy.pine            # Original with full table (656 lines)
├── trend_following_strategy_smart.pine      # NEW: Smart context panel (708 lines) ⭐
├── trend_following_strategy_v6.pine         # Pine Script v6 version
├── trend_following_strategy_backup_*.pine   # Backups
└── SESSION_NOTES_INFO_PANEL_SMART.md        # This file
```

### Recommended File to Use

**`trend_following_strategy_smart.pine`** ⭐

**Why?**
- ✅ Smart context-aware panel (clean, focused display)
- ✅ All margin checks included
- ✅ Stop loss and risk exposure display
- ✅ Real-time updates (`calc_on_every_tick=true`)
- ✅ All bug fixes applied
- ✅ R-multiple calculation corrected

---

## Key Settings

### Strategy Parameters (Lines 2-12)
```pine
overlay = true                          // Display on main chart
pyramiding = 3                          // Max 3 pyramids (4 total positions)
initial_capital = 5000000               // ₹50L
calc_on_every_tick = true               // Real-time updates ✓
process_orders_on_close = true          // Trades execute at bar close ✓
commission_value = 0.1                  // 0.1% commission
```

### Position Sizing (Lines 59-60)
```pine
risk_percent = 2.0                      // Risk 2% per trade
lot_size = 35                           // Bank Nifty lot size
```

### Margin Management (Lines 63-65)
```pine
use_margin_check = true                 // Enable margin protection ✓
max_margin_available = 50.0             // ₹50L total margin
margin_per_lot = 2.6                    // ₹2.6L per lot (synthetic futures)
```

### Pyramiding (Lines 68-71)
```pine
enable_pyramiding = true
max_pyramids = 3                        // 4 total positions
atr_pyramid_threshold = 0.5             // Add every 0.5 ATR move
pyramid_size_ratio = 0.5                // Each pyramid is 50% of previous
```

### Stop Loss Mode (Line 74)
```pine
stop_loss_mode = "SuperTrend"           // Options: SuperTrend | Van Tharp | Tom Basso
```

### Date Filter (Lines 83-84)
```pine
use_start_date = true
start_date = timestamp("11 Nov 2025 00:00 +0000")
```

### Smart Panel (Lines 55-56)
```pine
smart_panel = true                      // Auto-switch: indicators ↔ trade info
show_all_info = false                   // Debug mode (show everything)
```

---

## Bug Fixes

### Fix #1: Table Not Visible
**Lines**: 3, 8
- Changed `overlay=false` → `overlay=true`
- Changed `calc_on_every_tick=false` → `calc_on_every_tick=true`

### Fix #2: R-Multiple Display Error
**Line**: 195
- Removed `× 100` multiplication
- Changed variable name from `unrealized_pnl_percent` to `unrealized_pnl_r`

### Fix #3: Commission Confusion
**Clarification**: ₹0.25L deduction from ₹50L was commission, not a previous losing trade

### Fix #4: Pyramiding Without Margin Check
**Lines**: 250-260
- Added margin availability check before pyramiding
- Prevents over-leveraging

### Fix #5: Table Out of Bounds Error
**Line**: 552
- Fixed row count calculation
- Changed from 12 rows to 13 (when flat)
- Changed from 15 rows to 16 (when in position)

### Fix #6: Undeclared Variable `infoTable`
**Line**: 542
- Added `var table infoTable = na` declaration

---

## Stop Loss Modes Explained

### Mode 1: SuperTrend
**All positions use SuperTrend as stop**
- Long_1, Long_2, Long_3, Long_4 → All use current SuperTrend value
- Simple, consistent
- All positions exit together if price crosses below SuperTrend

### Mode 2: Van Tharp (Trail to Breakeven)
**Earlier positions trail to later entry prices**
- Long_1 → Trails to Long_2 entry (or SuperTrend if no Long_2)
- Long_2 → Trails to Long_3 entry (or SuperTrend if no Long_3)
- Long_3 → Trails to Long_4 entry (or SuperTrend if no Long_4)
- Long_4 → Uses SuperTrend

**Effect**: Protects earlier entries at breakeven, lets winners run

### Mode 3: Tom Basso (ATR Trailing Stop)
**Each position has independent ATR-based trailing stop**
- Initial Stop: Entry - (1.0 × ATR)
- Trailing Stop: Highest Close - (2.0 × ATR)
- Trails upward only
- Each position exits independently

---

## Risk Exposure Calculation

**Formula** (Lines 238-242):
```pine
risk_long1 = (initial_entry_price - display_stop_long1) × initial_position_size × lot_size
risk_long2 = (pyr1_entry_price - display_stop_long2) × pyramid_1_size × lot_size
risk_long3 = (pyr2_entry_price - display_stop_long3) × pyramid_2_size × lot_size
risk_long4 = (pyr3_entry_price - display_stop_long4) × pyramid_3_size × lot_size

total_risk_exposure = risk_long1 + risk_long2 + risk_long3 + risk_long4
```

**Example**:
```
Long_1: (57,500 - 58,291) × 12 × 35 = ₹0.33L loss
Long_2: (57,800 - 58,291) × 6 × 35  = ₹0.10L loss
Long_3: (58,000 - 58,291) × 3 × 35  = ₹0.03L loss
─────────────────────────────────────────────
Total Risk Exposure: ₹0.46L
```

**Displayed in table**: "Risk Exposure | ₹0.46L | If stopped out"

---

## Info Table Display Logic

### Table Size Calculation (Line 552)
```pine
num_rows = show_all_info ? 25 : (in_position ? 16 : 13)
```

| Condition | Rows | What's Shown |
|-----------|------|--------------|
| Flat (no position) | 13 | Header + 8 indicators + Entry Signal + 3 capital rows |
| In Position | 16 | Header + Entry Signal + up to 4 position rows + Total + Risk + P&L + 2 margin rows |
| Debug Mode (all) | 25 | Everything together |

### Conditional Sections

**Section 1: Indicators** (Lines 562-598)
```pine
if show_indicators  // True when: (smart_panel AND flat) OR debug mode
    // Show RSI, EMA, DC, ADX, ER, SuperTrend, Doji
```

**Section 2: Entry Signal** (Always shown, Line 601)
```pine
// Always visible - shows current entry status
```

**Section 3: Trade Info** (Lines 612-670)
```pine
if show_trade_info  // True when: (smart_panel AND in_position) OR debug mode
    // Show positions, stops, risk, P&L, margin
```

**Section 4: Capital Info** (Lines 672-694)
```pine
if not in_position or show_all_info
    // Show capital, lot preview, margin available
```

---

## Future Enhancements

### Potential Improvements

1. **Alert System**
   - Alert when margin utilization > 90%
   - Alert when all entry conditions met
   - Alert when risk exposure exceeds threshold

2. **Performance Metrics**
   - Win rate display
   - Average R per trade
   - Max drawdown tracking

3. **Position Heatmap**
   - Visual representation of pyramid levels
   - Color-coded based on P&L

4. **Trailing Stop Visualization**
   - Plot stop loss lines on chart for each position
   - Different colors for each pyramid level

5. **Risk Meter**
   - Visual gauge showing risk exposure vs capital
   - Warning levels at 5%, 10%, 15%

6. **Trade Journal Integration**
   - Export trade data to CSV
   - Include entry reason, stop levels, exit reason

---

## Important Notes for Future Sessions

### ⚠️ Remember These Issues

1. **Commission Setting**: The `commission_value=0.1` (0.1%) is currently set high
   - Actual Bank Nifty futures commission is much lower
   - Consider adjusting based on actual broker rates

2. **Margin Per Lot**: Set to ₹2.6L based on synthetic futures
   - **Verify** this matches your actual broker margin requirement
   - Update `margin_per_lot` input if different

3. **Lot Size**: Currently 35
   - Bank Nifty standard lot = 15
   - User specified 35 (perhaps 2x + buffer)
   - **Confirm** this is intentional

4. **calc_on_every_tick = true**
   - Provides real-time updates but uses more resources
   - On historical backtests, this increases computation time
   - Strategy still executes at bar close (safe)

5. **Smart Panel Toggle**
   - If user wants to see both indicators AND trade info together, toggle `show_all_info = true`
   - This overrides smart switching

### 📝 Key Variables to Track

```pine
// Position tracking
pyramid_count                    // Current number of pyramids (0-3)
initial_position_size            // Size of first entry
strategy.position_size           // Total lot size across all positions

// Margin tracking
current_margin_used_display      // Total margin used
margin_remaining                 // Margin available for pyramiding
margin_utilization_pct           // Percentage of margin used

// Risk tracking
total_risk_exposure              // Total ₹ at risk if all stops hit
unrealized_pnl                   // Current open profit/loss
unrealized_pnl_r                 // Current P&L in R-multiples

// Stop loss levels
display_stop_long1/2/3/4         // Current stop for each position
```

---

## Testing Checklist

Before deploying to live trading:

- [ ] Verify margin per lot matches broker requirement
- [ ] Test pyramiding with margin check enabled
- [ ] Confirm stop loss mode is set correctly
- [ ] Verify commission value matches actual broker fees
- [ ] Test smart panel switching (flat → in position → flat)
- [ ] Verify risk exposure calculation accuracy
- [ ] Test all 3 stop loss modes (SuperTrend, Van Tharp, Tom Basso)
- [ ] Confirm date filter is working (no trades before start date)
- [ ] Check R-multiple calculation (should be decimal, not percentage)
- [ ] Test on historical data for validation

---

## Contact & Support

**Created By**: Claude (Anthropic)
**User**: Shankar Vasudevan
**Session Date**: November 12, 2025
**Pine Script Version**: v5
**TradingView**: Bank Nifty Index Futures (75-min timeframe)

For questions or issues with this implementation, refer to:
- TradingView Pine Script documentation: https://www.tradingview.com/pine-script-docs/
- This session notes file
- Code comments in `trend_following_strategy_smart.pine`

---

## Quick Start Guide

### To Use Smart Panel File:

1. **Open TradingView**
2. **Load Bank Nifty Futures chart** (75-min timeframe)
3. **Pine Editor** → Open file: `trend_following_strategy_smart.pine`
4. **Add to Chart**
5. **Settings → Inputs** → Verify:
   - Smart Info Panel: ✓ ON
   - Enable Margin Check: ✓ ON
   - Max Margin Available: 50L
   - Margin per Lot: 2.6L (adjust if needed)
   - Use Start Date Filter: ✓ ON
   - Trade Start Date: Set to your desired start date

6. **Check top-right corner** for info panel
   - When flat: Shows entry conditions
   - When in trade: Shows positions, stops, risk, margin

### To Debug:

1. Enable **"Show All Info (Debug)"** in Settings → Inputs
2. This shows BOTH indicators and trade info together
3. Check if any rows are missing or incorrectly positioned
4. Verify margin calculations match expectations

---

**End of Session Notes**
