# Strategy Troubleshooting Guide

## Recent Updates (v2.0)

### Fixed Issues:
1. ✅ Added `process_orders_on_close=true` - All orders now execute at bar close
2. ✅ Changed entry/exit markers to small arrows (shape.arrowup/arrowdown, size.tiny)
3. ✅ Added comprehensive DEBUG PANEL to track conditions in real-time
4. ✅ End-of-day handling: Orders execute at bar close, capturing gap-ups

### Entry Timing:
- **Normal Operation**: Entry occurs at the CLOSE of the 75m candle where all conditions are met
- **Entry Price**: Close price of the signal bar
- **End-of-Day**: Same behavior - enters at bar close to capture overnight gap-ups
- **Visual Marker**: Small green arrow appears at the bottom of the signal bar

### Exit Timing:
- **Exit Trigger**: When candle closes BELOW SuperTrend(10,1.5)
- **Exit Price**: Close price of the exit bar
- **Visual Marker**: Small red arrow appears at the top of the exit bar

## Why No Entries Are Happening

### Most Common Reasons:

#### 1. **ADX < 25 Condition is Too Restrictive**
The strategy requires BOTH:
- High momentum (RSI > 70, Close > DC Upper)
- AND Low ADX (< 25)

This combination is RARE because:
- High RSI usually comes with strong trends (high ADX)
- Breakouts typically increase ADX
- ADX < 25 indicates weak or no trend

**Solution**: Check the debug panel to see how often ADX < 25 occurs during potential entry setups.

#### 2. **Efficiency Ratio > 0.8 is Very Strict**
ER > 0.8 means price movement must be VERY efficient (minimal noise).
- ER = 1.0 = perfectly straight line
- ER = 0.8 = 80% efficiency (very rare in real markets)
- With a 3-period ER, this is especially strict

**Solution**: Watch the ER values in the debug panel. If ER rarely exceeds 0.6-0.7, the threshold might be too high.

#### 3. **All 7 Conditions Rarely Align Simultaneously**
Each condition individually might trigger often, but ALL 7 together is rare.

#### 4. **Insufficient Historical Data**
If testing on limited data, signals might be outside the test period.

## How to Debug Using New Features

### 1. Use the Debug Panel (Separate Pane)
Enable "Show Debug Panel" in settings to see:
- **Color-coded lines** for each condition (value = 1 when true, 0 when false)
- **Lime columns** showing when ALL conditions are met
- Lines shown:
  - Red: RSI > 70
  - Blue: Close > EMA
  - Green: Close > DC
  - Orange: ADX < 25
  - Purple: ER > 0.8
  - Teal: Close > ST
  - Maroon: Not Doji

### 2. Use the Info Table (Top-Right)
The info table now shows:
- Current values for ALL indicators
- Clear ✓/✗ status for each condition
- Actual values when condition fails (helps identify bottlenecks)

**Example:**
```
ADX(30)  | 45.23  | ✗ 45.23
```
This shows ADX is 45.23, way above the 25 threshold.

### 3. Visual Inspection
Look for bars where 6 out of 7 conditions are met - these show "near misses".

## Recommended Diagnostic Steps

### Step 1: Check Individual Condition Frequency
Run the strategy and observe the debug panel for a few weeks/months of data.

Count how often each condition is TRUE:
- If RSI > 70 rarely occurs → Market might be range-bound
- If ADX < 25 is almost never true → Market is strongly trending
- If ER > 0.8 never hits → This is the bottleneck

### Step 2: Identify the Bottleneck Condition
The condition that's TRUE the LEAST is your bottleneck.

Expected frequency (rough estimates):
- RSI > 70: 15-30% of bars (overbought)
- Close > EMA(200): 40-50% (uptrend)
- Close > DC Upper: 5-10% (breakouts)
- ADX < 25: 20-40% (weak trends)
- ER > 0.8: 5-15% (very efficient moves)
- Close > ST: 40-50% (bullish)
- Not Doji: 85-95% (most candles)

### Step 3: Verify on Known Trending Periods
Test the strategy on a period you KNOW had strong uptrends:
- If still no signals → Conditions too strict
- If multiple signals → Strategy working, just need right market conditions

## Potential Adjustments (If Needed)

**⚠️ WARNING**: Only adjust if you understand the implications!

### Less Restrictive Alternatives:

1. **ADX Threshold**: Change from `< 25` to `< 30` or `< 35`
   ```pinescript
   adx_threshold = input.float(30, "ADX Threshold", minval=0)
   ```

2. **Efficiency Ratio**: Change from `> 0.8` to `> 0.6` or `> 0.7`
   ```pinescript
   er_threshold = input.float(0.7, "ER Threshold", minval=0, maxval=1)
   ```

3. **RSI Threshold**: Change from `> 70` to `> 65`
   ```pinescript
   rsi_threshold = input.float(65, "RSI Threshold", minval=0, maxval=100)
   ```

4. **Doji Detection**: Make less strict (higher threshold)
   ```pinescript
   doji_threshold = input.float(0.15, "Doji Body/Range Ratio")
   ```

## Testing Checklist

- [ ] Load strategy on a symbol (e.g., NSE:BANKNIFTY)
- [ ] Set timeframe to 75 minutes
- [ ] Open Strategy Tester tab
- [ ] Extend backtest period (at least 6-12 months)
- [ ] Enable "Show Debug Panel" in strategy settings
- [ ] Check debug panel - are any conditions frequently TRUE?
- [ ] Review info table - which condition fails most often?
- [ ] Look for near-misses (6/7 conditions met)
- [ ] Check if ER values ever approach 0.8
- [ ] Check if ADX ever drops below 25 during strong moves

## Expected Behavior After Fix

1. **Small green arrows** appear below candles where all 7 conditions are met
2. **Small red arrows** appear above candles where exit is triggered
3. **Strategy Tester** shows:
   - List of trades
   - Entry price = close price of signal candle
   - Exit price = close price when close < SuperTrend
4. **Performance stats** appear in Strategy Tester panel
5. **Position tracking** shows "IN TRADE" or "NO POSITION" in info table

## Still No Entries?

If after checking all above, there are still NO entries:

### Test with Relaxed Conditions
Temporarily modify the entry logic to see which conditions are blocking:

```pinescript
// Temporarily comment out strict conditions one at a time:
long_entry = rsi_condition and
             ema_condition and
             dc_condition and
             // adx_condition and    // COMMENTED OUT FOR TESTING
             er_condition and
             st_condition and
             not_doji
```

Run the strategy after commenting out each condition to isolate the bottleneck.

## Contact & Support

If the strategy is still not working after following this guide:
1. Check the debug panel and note which condition(s) never turn TRUE
2. Take a screenshot of the debug panel over a 100+ candle period
3. Check TradingView Pine Script documentation for any version-specific issues
4. Verify the symbol you're testing has sufficient liquidity and data

## Key Insight

This is a **HIGHLY SELECTIVE** strategy by design. It's looking for a very specific market condition:
- Beginning of a new trend (low ADX)
- With strong momentum (high RSI)
- Clean, efficient price action (high ER)
- At a breakout level (above DC)

Such conditions might only occur 1-5 times per year on any given instrument. This is NORMAL for this type of strategy.

If you need more frequent signals, you'll need to relax some conditions.
