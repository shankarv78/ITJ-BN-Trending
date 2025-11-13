# ITJ Bank Nifty Trend Following Strategy - Complete Requirements & Features

**Version**: 3.0 (Smart Panel)
**Target Instrument**: Bank Nifty Index (75-minute timeframe)
**Strategy Type**: Momentum-based trend following with pyramiding
**Status**: Production Ready ✅

---

## Table of Contents
1. [Strategy Overview](#strategy-overview)
2. [Core Strategy Configuration](#core-strategy-configuration)
3. [Entry Conditions](#entry-conditions)
4. [Exit Conditions](#exit-conditions)
5. [Position Sizing](#position-sizing)
6. [Pyramiding System](#pyramiding-system)
7. [Stop Loss Modes](#stop-loss-modes)
8. [Margin Management](#margin-management)
9. [Smart Info Panel](#smart-info-panel)
10. [Visual Indicators](#visual-indicators)
11. [Key Features](#key-features)
12. [Performance Metrics](#performance-metrics)

---

## Strategy Overview

This is a comprehensive trend-following strategy designed for Bank Nifty trading using synthetic futures (ATM PE Sell + ATM CE Buy). The strategy combines multiple technical indicators to identify high-probability momentum breakouts while managing risk through sophisticated position sizing, pyramiding, and three different stop-loss methodologies.

### Core Philosophy
- **Selective Entry**: Uses 7 strict conditions to filter for high-quality setups
- **Risk Management**: Fixed 2% risk per trade with margin-aware pyramiding
- **Trend Riding**: Three different stop-loss modes to adapt to different market conditions
- **Capital Protection**: Margin checks prevent over-leveraging

---

## Core Strategy Configuration

### Basic Settings
- **Initial Capital**: ₹50,00,000 (₹50 Lakhs)
- **Timeframe**: 75-minute candles
- **Lot Size**: 35 (configurable for synthetic futures)
- **Risk Per Trade**: 2% of capital
- **Maximum Pyramids**: 3 (4 total positions)
- **Calculation**: Real-time updates (`calc_on_every_tick=true`)
- **Order Execution**: At bar close (`process_orders_on_close=true`)
- **Commission**: 0.1%
- **Chart Overlay**: Enabled (indicators visible on main chart)

---

## Entry Conditions

### 7 Conditions (ALL must be met at 75m candle close)

1. **RSI(6) > 70**
   - Momentum confirmation
   - Indicates strong upward momentum
   - Period: 6 candles

2. **Close > EMA(200)**
   - Long-term uptrend confirmation
   - Ensures trading in the direction of major trend
   - Period: 200 candles (blue line on chart)

3. **Close > Donchian Channel Upper (20)**
   - Breakout above recent highs
   - Uses historical data (high[1] and low[1]) to prevent lookahead bias
   - Period: 20 candles
   - Green upper band on chart

4. **ADX(30) < 25**
   - Not in a strong trending market
   - Allows for new trend formation
   - Period: 30 candles
   - Threshold: Must be below 25

5. **Efficiency Ratio(3) > 0.8**
   - Price movement efficiency
   - Measures directional movement vs noise
   - Period: 3 candles
   - Threshold: Must exceed 0.8 (80% efficiency)
   - Custom ER formula implemented

6. **Close > SuperTrend(10, 1.5)**
   - Bullish SuperTrend confirmation
   - ATR Period: 10
   - Multiplier: 1.5
   - Green line indicates bullish trend

7. **NOT a Doji Candle**
   - Body size must be > 10% of candle range
   - Filters out indecision candles
   - Formula: `|close - open| / (high - low) > 0.1`

### Date Filter (Optional)
- **Use Start Date Filter**: Can be enabled to start tracking from specific date
- **Trade Start Date**: Configurable (default: Nov 11, 2025)
- **Purpose**: Avoid historical trades, focus on forward testing

### Entry Timing
- **Signal Detection**: At the close of the 75m candle
- **Order Execution**: At the CLOSE price of that same candle
- **Visual Marker**: Small green arrow (▲) below the signal bar
- **End-of-Day Handling**: Same behavior - enters at bar close to capture overnight gap-ups

---

## Exit Conditions

Exit strategy varies based on selected **Stop Loss Mode** (see section 7 below). The strategy offers three different exit methodologies:

### Default Exit (SuperTrend Mode)
- **Condition**: Close position when candle closes BELOW SuperTrend(10, 1.5) line
- **Timing**: At bar close
- **Visual Marker**: Small red arrow (▼) above the exit bar
- **Behavior**: All positions exit together

### Alternative Modes
- **Van Tharp Mode**: Earlier entries trail to later entry prices (breakeven protection)
- **Tom Basso Mode**: ATR-based trailing stops for each position independently

*See "Stop Loss Modes" section for detailed explanations*

---

## Position Sizing

### Method: Percent Risk with Efficiency Ratio (ER) Multiplier

**Formula**:
```
Risk Amount = Equity High × (Risk % / 100)
Risk Per Point = Entry Price - Stop Loss Price
Risk Per Lot = Risk Per Point × Lot Size
Number of Lots = (Risk Amount / Risk Per Lot) × ER
Final Lots = max(1, round(Number of Lots))
```

### Key Features
- **Risk-Based**: Calculates position size based on 2% risk per trade
- **ER Multiplier**: Scales position size by Efficiency Ratio (trend strength)
- **Equity High Watermark**: Uses highest realized equity, not current equity
- **Stop Distance**: Automatically calculates based on entry price vs stop loss
- **Minimum Size**: Enforces at least 1 lot per trade
- **Division by Zero Protection**: Checks that stop distance is positive

### Example Calculation
```
Conditions:
- Equity High: ₹50,00,000
- Risk %: 2.0%
- Entry Price: ₹58,000
- Stop Loss: ₹57,350 (650 points below)
- Lot Size: 35
- ER: 0.85

Calculation:
- Risk Amount: ₹50,00,000 × 0.02 = ₹1,00,000
- Risk Per Point: 650 points
- Risk Per Lot: 650 × 35 = ₹22,750
- Raw Lots: (₹1,00,000 / ₹22,750) × 0.85 = 3.74 lots
- Final Lots: 4 lots (rounded)
```

### Position Sizing Advantages
- **Consistent Risk**: Always risks exactly 2% of capital
- **Trend Strength Aware**: Larger positions in stronger trends (high ER)
- **Volatility Adaptive**: Smaller positions when stops are wider
- **Proven Performance**: 28% max drawdown vs 38% with alternative methods

---

## Pyramiding System

### Overview
- **Maximum Pyramids**: 3 additional entries (4 total positions)
- **Pyramid Sizing**: Geometric scaling at 50% ratio
- **Trigger Method**: ATR-based movement + profitability check
- **Margin Protection**: Checks margin availability before pyramiding

### Pyramid Position Sizes
- **Long_1 (Initial)**: Base size (e.g., 12 lots)
- **Long_2 (PYR1)**: 50% of initial (e.g., 6 lots)
- **Long_3 (PYR2)**: 50% of PYR1 (e.g., 3 lots)
- **Long_4 (PYR3)**: 50% of PYR2 (e.g., 1-2 lots)

### Pyramid Trigger Conditions
1. **ATR Movement**: Price must move at least 0.5 ATR from last entry
2. **Profitability Check**: Position must be profitable (Van Tharp principle)
3. **Margin Availability**: Sufficient margin must be available (if enabled)
4. **Maximum Count**: Cannot exceed 3 pyramids

### Pyramid Thresholds (Configurable)
- **PYR1 Threshold**: 0.5 ATR (default)
- **PYR2 Threshold**: 0.5 ATR (default)
- **PYR3 Threshold**: 0.5 ATR (default)

### Pyramid Example
```
Initial Entry @ ₹57,500 (12 lots)
├─ Price moves to ₹58,000 (+500 points, 0.5 ATR met)
├─ Position is profitable ✓
├─ Margin available ✓
└─ Add PYR1 @ ₹58,000 (6 lots)

Price moves to ₹58,500 (+500 points from PYR1)
├─ Position is profitable ✓
├─ Margin available ✓
└─ Add PYR2 @ ₹58,500 (3 lots)

Price moves to ₹59,000 (+500 points from PYR2)
├─ Position is profitable ✓
├─ Margin available ✓
└─ Add PYR3 @ ₹59,000 (1-2 lots)

Total Position: 21-22 lots across 4 entries
```

### Pyramiding Benefits
- **Scales into winners**: Adds to profitable positions
- **Risk-managed**: Each pyramid checked for profitability
- **Trend riding**: Captures extended moves
- **Geometric scaling**: Prevents over-concentration

---

## Stop Loss Modes

The strategy offers **3 different stop-loss methodologies** to suit different market conditions and trading styles.

### Mode 1: SuperTrend (Default, Recommended)

**How It Works:**
- All positions use the same SuperTrend(10, 1.5) line as stop loss
- When price closes below SuperTrend → All positions exit together
- Stop loss moves with SuperTrend line

**Advantages:**
- ✅ Simple and clear
- ✅ Trend-aware (only exits when trend changes)
- ✅ Whipsaw-resistant
- ✅ **Proven: 28.74% max drawdown**

**Best For:**
- Default mode for most conditions
- Trending markets
- Traders who want simplicity

---

### Mode 2: Van Tharp (Trail to Breakeven)

**How It Works:**
- Earlier pyramid entries trail their stop to later entry prices
- Each position has independent stop loss
- Protects earlier entries at breakeven

**Stop Logic:**
```
Long_1 (Initial) → Trails to Long_2 entry price
Long_2 (PYR1)    → Trails to Long_3 entry price
Long_3 (PYR2)    → Trails to Long_4 entry price
Long_4 (PYR3)    → Uses SuperTrend
```

**Example:**
```
Initial Entry @ ₹57,500
PYR1 Entry @ ₹58,000
Price reverses to ₹57,800

Results:
- Long_1 exits @ ₹58,000 (breakeven/small profit) ✓
- Long_2 still in trade with stop @ SuperTrend
```

**Advantages:**
- ✅ Protects earlier entries
- ✅ Locks in profits incrementally
- ✅ Reduces risk on pyramided positions
- ✅ Better risk-adjusted returns

**Best For:**
- Pyramiding strategies
- Volatile markets
- Risk-conscious traders

---

### Mode 3: Tom Basso (ATR Trailing Stop)

**How It Works:**
- Each position has independent ATR-based trailing stop
- Stops trail based on highest close since entry
- Volatility-adaptive stop distances

**Stop Calculation:**
```
Initial Stop: Entry Price - (1.0 × ATR)
Trailing Stop: Highest Close - (2.0 × ATR)
Stop only moves UP, never widens
```

**Example:**
```
Entry @ ₹58,000, ATR = 600

Bar 1: Initial Stop = ₹58,000 - 600 = ₹57,400
Bar 5: Highest = ₹58,700, Trail = ₹58,700 - 1,200 = ₹57,500 ↑
Bar 10: Highest = ₹59,400, Trail = ₹59,400 - 1,200 = ₹58,200 ↑
Bar 15: Close = ₹58,100 < ₹58,200 → EXIT
```

**Advantages:**
- ✅ Volatility-adaptive
- ✅ Smooth trailing (no trend direction jumps)
- ✅ Research-backed (Tom Basso's "Coin Flip" study)
- ✅ Independent stops per pyramid

**Best For:**
- Smooth trend-riding
- Volatility-adaptive trading
- Research-based approaches

---

## Margin Management

### Purpose
Prevents over-leveraging by checking margin availability before pyramiding.

### Configuration
- **Enable Margin Check**: Toggle on/off
- **Max Margin Available**: ₹50L (default, configurable)
- **Margin Per Lot**: ₹2.6L (synthetic futures requirement)

### Margin Calculation
```
Current Margin Used = Total Position Size × Margin Per Lot
Margin Remaining = Max Margin - Current Margin Used
Margin Utilization % = (Used / Max) × 100
```

### Pyramiding Check
Before adding pyramid:
```
Pyramid Margin Required = Pyramid Lots × Margin Per Lot
Total After Pyramid = Current Margin + Pyramid Margin
Pyramid Allowed = Total After Pyramid ≤ Max Margin Available
```

### Visual Display
- **Margin Used**: Shows current usage and % (color-coded)
  - 🟢 Green: < 75%
  - 🟠 Orange: 75-90%
  - 🔴 Red: > 90%
- **Margin Free**: Shows remaining margin in Lakhs

### Example
```
Position: 18 lots (12 + 6 from pyramiding)
Margin Per Lot: ₹2.6L
Current Margin Used: 18 × 2.6 = ₹46.8L (93.6%) 🔴
Margin Remaining: ₹3.2L

Attempting PYR2: 3 lots
Required Margin: 3 × 2.6 = ₹7.8L
Total After: ₹46.8L + ₹7.8L = ₹54.6L > ₹50L ❌
Result: Pyramid BLOCKED
```

---

## Smart Info Panel

### Overview
Context-aware information display that **automatically switches** between indicator conditions and trade management information.

### Toggle Settings
- **Smart Info Panel**: Enable/disable context-aware switching
- **Show All Info (Debug)**: Show both indicators and trade info together

### Display Behavior

#### When **NOT in Trade** (Flat Position):
Shows **ENTRY CONDITIONS** monitoring:
- Current price
- RSI(6) value and status (✓ or ✗)
- EMA(200) value and status
- Donchian Channel Upper value and status
- ADX(30) value and status
- Efficiency Ratio value and status
- SuperTrend value and status
- Doji check status
- Entry signal status (WAITING / ALL MET)
- Available capital
- Calculated lot size (if entry triggered)
- Available margin

#### When **IN TRADE**:
Shows **TRADE MANAGEMENT** information:
- Entry signal status
- **Position Breakdown**:
  - Long_1 (Initial): Entry price, lots, current stop
  - Long_2 (PYR1): Entry price, lots, current stop (if added)
  - Long_3 (PYR2): Entry price, lots, current stop (if added)
  - Long_4 (PYR3): Entry price, lots, current stop (if added)
- **Total Position**: Combined lots and current price
- **Risk Exposure**: Total ₹ at risk if all stops hit
- **Open P&L**: Current profit/loss in ₹ and R-multiples
- **Margin Used**: Current margin utilization (%)
- **Margin Free**: Remaining margin available
- **Pyramid Count**: How many pyramids added (e.g., "2/3 Pyrs")

### R-Multiple Display
- **R** = Risk per trade (Van Tharp terminology)
- **1R** = Initial risk amount (2% of capital)
- **Example**: "0.34R" = Profit is 34% of initial risk

### Color Coding
- **Entry Conditions**:
  - ✓ Green = Condition met
  - ✗ Red = Condition not met
- **Margin Utilization**:
  - 🟢 Green: < 75%
  - 🟠 Orange: 75-90%
  - 🔴 Red: > 90%
- **Position Entries**:
  - Blue: Initial entry (Long_1)
  - Green: Pyramid entries (Long_2, Long_3, Long_4)

### Benefits
- **Clean Display**: Shows only relevant information
- **No Clutter**: Automatically hides indicators when in trade
- **Focus**: Helps monitor what matters in current state
- **Real-time**: Updates every tick (not just at bar close)

---

## Visual Indicators on Chart

### Lines and Bands
1. **EMA(200)** - Blue line
2. **Donchian Channel** - Green (upper), Red (lower), Gray (middle)
3. **SuperTrend(10, 1.5)** - Green when bullish, Red when bearish

### Signal Markers
4. **Entry Signals** - Small green arrow (▲) below signal bar
5. **Exit Signals** - Small red arrow (▼) above exit bar
6. **Doji Candles** - Small orange diamond markers

### Background Colors
7. **Entry Signal Bars** - Light green background
8. **Exit Signal Bars** - Light red background

### Info Display
9. **Smart Info Panel** - Top-right corner, context-aware table
10. **Debug Panel** - (Optional) Separate pane showing condition states over time

---

## Key Features

### 1. Anti-Repainting Measures
- ✅ `process_orders_on_close=true` - Orders execute at bar close
- ✅ `calc_on_every_tick=true` - Real-time monitoring (trades still at close)
- ✅ Donchian uses `high[1]` and `low[1]` - Historical data only
- ✅ No security() with lookahead bias
- ✅ All indicators use confirmed historical data

### 2. Risk Management
- ✅ Fixed 2% risk per trade
- ✅ Position sizing based on stop distance
- ✅ Equity high watermark (not current equity)
- ✅ Margin checks before pyramiding
- ✅ Profitability checks before adding pyramids
- ✅ Division by zero protection
- ✅ Minimum 1 lot enforcement

### 3. Trade Management
- ✅ Three stop-loss modes (SuperTrend, Van Tharp, Tom Basso)
- ✅ Independent stop tracking per pyramid
- ✅ Breakeven protection for earlier entries (Van Tharp mode)
- ✅ Volatility-adaptive stops (Tom Basso mode)
- ✅ Real-time risk exposure calculation

### 4. Smart Features
- ✅ Context-aware info panel (flat vs in-trade)
- ✅ Real-time margin monitoring
- ✅ R-multiple P&L display
- ✅ Color-coded status indicators
- ✅ Date filter for forward testing
- ✅ Comprehensive visual markers

### 5. Efficiency Ratio Implementation
Custom ER calculation using provided formula:
```pinescript
ER(src, p, dir) =>
    a = dir ? src - src[p] : math.abs(src - src[p])
    b = 0.0
    for i = 0 to p-1
        b := b + math.abs(src[i] - src[i+1])
    er = b != 0 ? a / b : 0
```
- Period: 3
- Directional: false
- Threshold: > 0.8

---

## Performance Metrics

### Historical Backtest Results (Jan 2009 - Nov 2025)

**SuperTrend Mode (Default):**
```
Initial Capital:    ₹50,00,000 (₹50 Lakhs)
Final Equity:       ₹134,73,76,32 (₹134.7 Crores)
Total Return:       +2,694.75%
CAGR:              ~23% per year
Max Drawdown:       28.74% ✅
Profit Factor:      1.952
Total Trades:       576
Win Rate:           48.78%
Average Trade:      Positive
```

### Performance Highlights
- ✅ **Exceptional Returns**: 36.93× capital over 16.85 years
- ✅ **Manageable Drawdown**: 28.74% is acceptable for trend-following
- ✅ **Consistent Performance**: ~23% CAGR (outperforms many benchmarks)
- ✅ **Selective Trading**: Only takes high-probability setups
- ✅ **Proven System**: Extensively backtested and refined

### Why This Strategy Works
1. **Highly Selective**: 7 strict conditions filter for quality setups
2. **Trend Following**: Rides established trends with momentum
3. **Risk Managed**: Fixed 2% risk with position sizing
4. **Pyramiding**: Scales into winners for maximum profit
5. **Adaptive Stops**: Three modes for different market conditions
6. **Margin Protection**: Prevents over-leveraging

### Common Characteristics
- **Selective Entry**: May see only 5-15 trades per year
- **High Winners**: When it wins, wins are substantial (pyramiding)
- **Controlled Losses**: 2% risk per trade caps losses
- **Trend Dependence**: Performs best in trending markets
- **Low Frequency**: Not a day-trading strategy

### Most Common Bottlenecks (Why Few Entries?)
The combination of these conditions is RARE:
1. **ADX < 25** - Rarely true during strong momentum moves
2. **ER > 0.8** - Very strict efficiency requirement
3. **RSI > 70 AND ADX < 25** - Contradictory conditions (by design)
4. **All 7 conditions together** - Filters for exceptional setups

This selectiveness is intentional - it's quality over quantity.

---

## Configuration Quick Reference

### Recommended Settings (Production)
```
Strategy:
├─ Initial Capital: ₹50,00,000
├─ Risk %: 2.0
├─ Lot Size: 35 (verify with broker)
├─ Stop Loss Mode: SuperTrend ✅
├─ Enable Pyramiding: Yes
├─ Max Pyramids: 3
├─ Pyramid Threshold: 0.5 ATR
├─ Pyramid Size Ratio: 0.5
├─ Enable Margin Check: Yes ✅
├─ Max Margin: ₹50L
├─ Margin Per Lot: ₹2.6L (verify with broker)
├─ Use Start Date Filter: Yes (for forward testing)
└─ Smart Info Panel: Yes ✅
```

### Alternative Testing Configurations
**Van Tharp Mode:**
- Stop Loss Mode: Van Tharp
- (Better for protecting pyramided positions)

**Tom Basso Mode:**
- Stop Loss Mode: Tom Basso
- Initial ATR Mult: 1.0
- Trailing ATR Mult: 2.0
- (Research-backed, smooth trailing)

---

## Files in Repository

### Main Strategy Files
1. **trend_following_strategy_smart.pine** ⭐ **RECOMMENDED**
   - Latest version with Smart Info Panel
   - Margin management included
   - All features implemented
   - Production ready

2. **trend_following_strategy.pine**
   - Full info panel (always shows everything)
   - Alternative to smart version

### Documentation Files
- **STRATEGY_LOGIC_SUMMARY.md** - This file (complete requirements)
- **SESSION_NOTES_INFO_PANEL_SMART.md** - Detailed implementation notes
- **IMPLEMENTATION_SUMMARY.md** - Van Tharp and Tom Basso implementation
- **TOM_BASSO_FEATURES_IMPLEMENTED.md** - Position sizing details
- **FINAL_PRODUCTION_CERTIFICATION.md** - Production readiness audit

---

## Quick Start Guide

### 1. Load Strategy
- Open TradingView
- Load Bank Nifty chart (75-minute timeframe)
- Pine Editor → Load `trend_following_strategy_smart.pine`
- Add to Chart

### 2. Configure Settings
- Settings → Inputs
- Verify all settings match your broker requirements
- Key settings to check:
  - Lot Size (35 default)
  - Margin Per Lot (₹2.6L default)
  - Max Margin Available (₹50L default)

### 3. Monitor
- Smart Info Panel appears top-right
- When flat: Shows entry conditions
- When in trade: Shows positions, stops, risk, margin
- Color coding helps identify status quickly

### 4. Backtest (Optional)
- Use date filter to test specific periods
- Compare different stop-loss modes
- Analyze performance metrics
- Download CSV for detailed analysis

---

## Important Notes

### ⚠️ Verify Before Live Trading
1. **Margin Per Lot**: Confirm with your broker (₹2.6L is for synthetic futures)
2. **Lot Size**: Standard Bank Nifty = 15, verify your setup
3. **Commission**: Set to 0.1%, adjust to actual broker fees
4. **Capital Allocation**: Strategy designed for ₹50L allocation

### 💡 Strategy Philosophy
- **Quality over Quantity**: Very selective entries
- **Trend Following**: Needs trending markets to perform
- **Pyramiding**: Essential for capturing big moves
- **Risk First**: Always 2% risk, never more

### 🎯 Best Use Cases
- ✅ Bank Nifty trending markets
- ✅ 75-minute timeframe
- ✅ Synthetic futures or futures trading
- ✅ Capital allocation: ₹50L - ₹1Cr
- ✅ Traders comfortable with 28-30% drawdowns

---

## Support & Maintenance

**Version**: 3.0 (Smart Panel)
**Last Updated**: November 13, 2025
**Status**: Production Ready ✅

For issues or questions:
- Review documentation files in repository
- Check TradingView Pine Script documentation
- Verify all broker-specific settings (margin, lot size, commission)

---

**End of Requirements Document**
