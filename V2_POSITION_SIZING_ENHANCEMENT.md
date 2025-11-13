# V2 Position Sizing Enhancement - Complete Specification

## Overview
Version 2 implements an advanced position sizing mechanism that ensures:
1. **Risk per entry** cannot exceed 2% of current account equity
2. **Pyramiding is gated** - only allowed when accumulated profit > base trade risk
3. **Pyramid sizing** uses the minimum of three independent constraints

## Key Changes from V1

### 1. Risk Calculation Base
- **V1**: Used highest realized equity (equity_high) for risk calculations
- **V2**: Uses **current equity** (realized + unrealized) for risk calculations
  ```
  current_equity = strategy.equity  // Includes all P&L
  risk_per_entry = current_equity × 2%
  ```

### 2. Pyramid Gating Logic
**NEW in V2**: Pyramids are only allowed when profit covers base risk

```
accumulated_profit = current_equity - initial_capital
base_risk = (entry_price - stop_loss) × base_lots × lot_size

Gate: accumulated_profit > base_risk
```

**Why this matters:**
- Ensures we have "house money" before adding risk
- Base position must be profitable enough to cover its own risk
- Prevents pyramiding into losing or break-even positions

### 3. Three-Factor Pyramid Sizing

**V2 Formula: pyramid_lots = min(lot-a, lot-b, lot-c)**

#### lot-a: Margin Constraint
```
available_margin = current_equity_lakhs (or × leverage if enabled)
current_margin_used = position_size × margin_per_lot
free_margin = available_margin - current_margin_used

lot-a = floor(free_margin ÷ margin_per_lot)
```
**Purpose**: Ensure we never exceed available margin

#### lot-b: Traditional Pyramiding Rule
```
lot-b = floor(base_position_size × 50%)
```
**Purpose**: Maintain geometric scaling (each pyramid = 50% of base)

#### lot-c: Risk Budget Based
```
profit_after_base_risk = accumulated_profit - base_risk
lotc_risk = profit_after_base_risk × 50%

pyramid_stop = SuperTrend or (close - ATR × multiplier) for Tom Basso
SL_per_lot = (close - pyramid_stop) × lot_size

lot-c = floor(lotc_risk ÷ SL_per_lot)
```
**Purpose**: Only risk 50% of the "excess profit" after base risk is covered

## Complete Logic Flow

### Initial Entry
```
1. Calculate risk_amount = current_equity × 2%
2. Calculate SL distance = entry_price - SuperTrend
3. Calculate risk_based_lots = (risk_amount ÷ SL_distance) ÷ lot_size × ER
4. Calculate margin_based_lots = available_margin ÷ margin_per_lot
5. entry_lots = min(risk_based_lots, margin_based_lots)
6. Enter if entry_lots >= 1
```

### Pyramid Entry Decision Tree
```
IF (enable_pyramiding AND in_position AND pyramid_count < max_pyramids)
  ├─ Calculate price_move_from_last ÷ ATR
  ├─ IF (price_move >= ATR_threshold)
  │   ├─ Calculate base_risk (ongoing risk for Long_1)
  │   ├─ Calculate accumulated_profit (realized + unrealized)
  │   ├─ CHECK GATE: accumulated_profit > base_risk?
  │   │   ├─ NO → BLOCK pyramid (display "GATE BLOCKED")
  │   │   └─ YES → PROCEED
  │   │       ├─ Calculate profit_after_base_risk = profit - base_risk
  │   │       ├─ Calculate lot-a (margin constraint)
  │   │       ├─ Calculate lot-b (50% of base)
  │   │       ├─ Calculate lot-c (risk budget)
  │   │       ├─ pyramid_lots = min(lot-a, lot-b, lot-c)
  │   │       └─ IF pyramid_lots >= 1 → ENTER PYRAMID
  │   └─ ELSE → WAIT for price movement
  └─ ELSE → max pyramids reached
```

## Stop Loss Handling

### SuperTrend Mode
- All positions use SuperTrend(10, 1.5) as stop
- `display_stop_long1/2/3/4 = supertrend`

### Van Tharp Mode
- Trail earlier entries to later pyramid entry prices
- Protects earlier entries at breakeven
- Last entry uses SuperTrend

### Tom Basso Mode
- Each entry has independent ATR-based trailing stop
- Initial stop: `entry - (ATR × initial_mult)`
- Trailing stop: `highest_close - (ATR × trailing_mult)`
- Pyramid stop calculation uses initial ATR stop

## Risk Exposure Calculation

For each position:
```
risk_long1 = (entry1 - stop1) × lots1 × lot_size
risk_long2 = (entry2 - stop2) × lots2 × lot_size
risk_long3 = (entry3 - stop3) × lots3 × lot_size
risk_long4 = (entry4 - stop4) × lots4 × lot_size

total_risk_exposure = sum of all risks
```

This is the **actual amount at risk** if all stops are hit simultaneously.

## Example Scenario

### Setup
- Current Equity: ₹50,00,000 (50L)
- Initial Capital: ₹50,00,000
- Risk per entry: 2% = ₹1,00,000
- Margin per lot: ₹2.6L
- Lot size: 35 points/lot

### Trade Progression

#### Entry 1 (Base)
```
Price: 50,000
SuperTrend: 49,500
SL distance: 500 points
Risk per lot: 500 × 35 = ₹17,500

risk_based_lots = 1,00,000 ÷ 17,500 × ER(0.9) = 5.14 → floor = 5 lots
margin_based_lots = 50L ÷ 2.6L = 19 lots
entry_lots = min(5, 19) = 5 lots

ENTER: 5 lots at 50,000
Base Risk: ₹87,500
```

#### Pyramid 1 Opportunity
```
Price moves to: 51,000 (+1000 points = 1.3 ATR)
Accumulated Profit: ₹1,75,000 (unrealized)
Base Risk: ₹62,500 (stop moved up to 49,750)

GATE CHECK:
  profit (₹1,75,000) > base_risk (₹62,500)? ✓ YES
  profit_after_base_risk = ₹1,12,500

lot-a (margin):
  free_margin = 50L - (5 × 2.6L) = 37L
  lot-a = floor(37L ÷ 2.6L) = 14 lots

lot-b (50% rule):
  lot-b = floor(5 × 0.5) = 2 lots

lot-c (risk budget):
  lotc_risk = ₹1,12,500 × 50% = ₹56,250
  pyramid_stop = 50,500 (SuperTrend)
  SL_per_lot = (51,000 - 50,500) × 35 = ₹17,500
  lot-c = floor(₹56,250 ÷ ₹17,500) = 3 lots

pyramid_lots = min(14, 2, 3) = 2 lots

ENTER PYRAMID: 2 lots at 51,000
```

**Key Insight**: lot-b (traditional 50% rule) is the limiting factor here, maintaining geometric scaling.

#### Pyramid 2 Opportunity
```
Price moves to: 52,500 (+1500 more points)
Accumulated Profit: ₹3,50,000
Base Risk: ₹50,000 (stop at 50,000)

GATE CHECK: ✓ YES
profit_after_base_risk = ₹3,00,000

lot-a = floor((50L - 7×2.6L) ÷ 2.6L) = 12 lots
lot-b = floor(5 × 0.5) = 2 lots (still 50% of base!)
lot-c = floor((₹3,00,000 × 50%) ÷ ₹17,500) = 8 lots

pyramid_lots = min(12, 2, 8) = 2 lots

ENTER PYRAMID: 2 lots at 52,500
```

**Note**: Even though we have plenty of profit and margin, lot-b caps us at 2 lots to maintain discipline.

## Info Panel Enhancements

### When In Position
The V2 info panel displays:

1. **All Entry Levels** - Price, lots, and stop loss for each position
2. **Pyramid Gate Status** - Visual indicator if pyramiding is allowed
3. **Risk Breakdown**:
   - Base Risk (Long_1 ongoing risk)
   - Accumulated Profit (realized + unrealized)
   - Profit-Risk (what's left after base risk covered)
4. **Lot Calculation Breakdown**:
   - Lot-A (from margin constraint)
   - Lot-B (from 50% rule)
   - Lot-C (from risk budget)
5. **Total Risk Exposure** - Amount at risk if all stops hit
6. **Margin Utilization** - Current usage and remaining

### When Flat
Shows:
- All entry indicators (RSI, EMA, DC, ADX, ER, SuperTrend)
- Entry signal status
- Current equity vs realized equity
- Lot size preview (if entering now)
- Available margin

## Configuration Parameters

All V1 parameters remain. Key ones for position sizing:

```
risk_percent = 2.0                    // Risk % per entry
margin_per_lot = 2.6                  // Margin required per lot (lakhs)
pyramid_size_ratio = 0.5              // 50% scaling factor
use_margin_check = true               // Enable margin constraints
use_leverage = false                  // Use leverage for margin
leverage_multiplier = 1.0             // Leverage factor
```

## Risk Management Benefits

### V1 Issues Addressed
1. ❌ **V1**: Could pyramid even when base trade at breakeven
   ✅ **V2**: Gate ensures profit > base risk before pyramiding

2. ❌ **V1**: Pyramid size only limited by margin and 50% rule
   ✅ **V2**: Also limited by available risk budget from profits

3. ❌ **V1**: Used static equity high for risk calculations
   ✅ **V2**: Uses dynamic current equity including unrealized P&L

### Protection Mechanisms
- **Triple constraint** ensures smallest allocation wins
- **Gate prevents** adding risk without sufficient cushion
- **Dynamic stops** mean base_risk changes as stops move
- **50% of excess** means we always keep 50% of profit buffer

## Implementation Notes

### Variable Tracking
```pine
var float pyramid_lot_a = 0        // For display/debugging
var float pyramid_lot_b = 0
var float pyramid_lot_c = 0
var float profit_after_base_risk = 0
var bool pyramid_gated = false
```

### Calculation Order
1. Check ATR movement threshold
2. Calculate base_risk (dynamic, based on current stop)
3. Calculate accumulated_profit
4. **GATE CHECK** - if fail, skip remaining calculations
5. Calculate profit_after_base_risk
6. Calculate lot-a, lot-b, lot-c independently
7. Take minimum
8. Check ROC filter (if enabled)
9. Enter if >= 1 lot

### Edge Cases Handled
- Division by zero (pyramid_risk_per_lot check)
- Negative values (math.max ensures >= 0)
- Fractional lots (floor() always rounds down)
- No stop available (na checks throughout)

## Testing Recommendations

### Unit Tests
1. **Gate logic**: Verify pyramid blocked when profit < base_risk
2. **Lot-c calculation**: Test with various profit levels
3. **Min function**: Verify smallest constraint always wins
4. **Dynamic stop**: Test base_risk updates as stop moves

### Integration Tests
1. **Full trade cycle**: Entry → Pyr1 → Pyr2 → Exit
2. **Gate blocking**: Trade that goes sideways (no profit growth)
3. **Margin constraint**: Large profit but limited margin
4. **Traditional constraint**: All constraints except lot-b are large

### Backtest Scenarios
1. **Strong trend**: Multiple pyramids should trigger
2. **Choppy market**: Gate should block pyramids
3. **Gap up entry**: Verify current_equity includes unrealized
4. **Stop movement**: Verify base_risk decreases as stop trails

## Summary of V2 Benefits

| Feature | V1 | V2 |
|---------|----|----|
| Risk calculation base | Realized equity (static) | Current equity (dynamic) |
| Pyramid gating | Unrealized P&L > 0 | Profit > Base Risk |
| Pyramid sizing | min(margin, 50%) | min(margin, 50%, risk_budget) |
| Risk allocation | Unlimited from margin | 50% of excess profit |
| Position transparency | Basic | Full breakdown (a,b,c) |

**Result**: More conservative, risk-aware pyramiding that requires meaningful profit cushion before adding exposure.
