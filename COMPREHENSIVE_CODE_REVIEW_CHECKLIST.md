# COMPREHENSIVE CODE REVIEW CHECKLIST
## ITJ Bank Nifty Trend Following Strategy

**Created:** 2025-11-14 (After Critical Bug Discovery)
**Purpose:** Prevent critical bugs from slipping through reviews
**Trigger:** Exit timing bug that should have been caught earlier

---

## CRITICAL EXECUTION TIMING CHECKS

### 1. Bar State and Order Execution ⚠️ **CRITICAL**

- [ ] **VERIFY:** `calc_on_every_tick` setting (Line 8)
  - Current: `calc_on_every_tick=true`
  - **DANGER:** Script recalculates on EVERY PRICE TICK
  - **REQUIRED:** ALL exit logic must use `barstate.isconfirmed`

- [ ] **VERIFY:** `process_orders_on_close` setting (Line 10)
  - Current: `process_orders_on_close=true`
  - **BEHAVIOR:** Orders execute at bar close price
  - **IMPLICATION:** Entry/exit conditions must be at bar close, not intra-bar

- [ ] **VERIFY:** Exit conditions ALL use `barstate.isconfirmed`
  - **SuperTrend Mode** (Line ~384):
    ```pinescript
    if close < supertrend and barstate.isconfirmed
    ```
  - **Van Tharp Mode** (Lines ~404, 417, 430, 443):
    ```pinescript
    if not na(initial_entry_price) and barstate.isconfirmed
    ```
  - **Tom Basso Mode** (Lines ~477, 489, 501, 513):
    ```pinescript
    if close < basso_stop_long1 and barstate.isconfirmed
    ```

- [ ] **VERIFY:** Entry conditions execute at bar close
  - Entry should NOT use `barstate.isconfirmed` (want to catch the close)
  - With `process_orders_on_close=true`, entries naturally execute at close

**BUG DISCOVERED 2025-11-14:** Exits were triggering on intra-bar ticks instead of confirmed bar close, causing premature exits even when final close was above SuperTrend.

---

## PINE SCRIPT EXECUTION MODEL VERIFICATION

### 2. Repainting Prevention ⚠️ **CRITICAL**

- [ ] **No security() calls with lookahead bias**
  - Search for: `security(` or `request.security(`
  - If found: Verify `lookahead=barmerge.lookahead_off`

- [ ] **Donchian Channel uses historical data** (Lines ~105-106)
  ```pinescript
  dc_upper = ta.highest(high[1], dc_period)  // Uses [1] offset
  dc_lower = ta.lowest(low[1], dc_period)    // Excludes current bar
  ```
  - **MUST use [1] offset** to avoid lookahead bias
  - Current bar high/low not known until bar closes

- [ ] **All indicators use closed bar data**
  - RSI, EMA, ADX, SuperTrend: All use standard ta.* functions
  - **VERIFY:** No custom indicators peeking ahead

### 3. Order Execution Timing

- [ ] **Entry logic checks position size** (Line ~260)
  ```pinescript
  if long_entry and strategy.position_size == 0
  ```
  - Prevents duplicate initial entries

- [ ] **Exit logic checks position exists** (Line ~377)
  ```pinescript
  if strategy.position_size > 0
  ```
  - Prevents closing non-existent positions

- [ ] **Pyramid logic checks limits** (Line ~304)
  ```pinescript
  if enable_pyramiding and strategy.position_size > 0 and pyramid_count < max_pyramids
  ```
  - Checks position exists AND count limit

---

## STRATEGY LOGIC VERIFICATION

### 4. Entry Conditions (ALL 7 must be met)

From STRATEGY_LOGIC_SUMMARY.md requirements:

- [ ] **RSI(6) > 70** (Line ~152)
  - Period: 6
  - Threshold: 70 (configurable 70/80 levels)

- [ ] **Close > EMA(200)** (Line ~153)
  - Period: 200
  - Long-term trend filter

- [ ] **Close > Donchian Upper(20)** (Line ~154)
  - Period: 20
  - **MUST use high[1]/low[1]** for lookahead prevention

- [ ] **ADX(30) < 25** (Line ~155)
  - Period: 30
  - Threshold: < 25

- [ ] **ER(3) > 0.8** (Line ~156)
  - Period: 3
  - Directional: false
  - Threshold: 0.8

- [ ] **Close > SuperTrend(10, 1.5)** (Line ~157)
  - Period: 10
  - Multiplier: 1.5

- [ ] **NOT a Doji** (Line ~158)
  - Body/Range ratio: <= 0.1
  - Filter: NOT is_doji

- [ ] **Date Filter** (Lines ~161)
  - Optional start date filter
  - Prevents trades before specified date

### 5. Exit Conditions (Mode-Dependent)

- [ ] **SuperTrend Mode:** Close below SuperTrend
  - **MUST use barstate.isconfirmed** ✅ FIXED
  - All positions exit together
  - State reset properly

- [ ] **Van Tharp Mode:** Trailing to pyramids or SuperTrend
  - Long_1 → trails to pyr1_entry_price OR SuperTrend
  - Long_2 → trails to pyr2_entry_price OR SuperTrend
  - Long_3 → trails to pyr3_entry_price OR SuperTrend
  - Long_4 → uses SuperTrend
  - **MUST use barstate.isconfirmed** ✅ FIXED

- [ ] **Tom Basso Mode:** ATR trailing stops
  - Independent stop per position
  - Stop = max(initial_stop, highest_close - 2×ATR)
  - Stops only tighten, never widen
  - **MUST use barstate.isconfirmed** ✅ FIXED

---

## POSITION SIZING VERIFICATION

### 6. Position Sizing Formula

From STRATEGY_LOGIC_SUMMARY.md:

```
Risk Amount = Equity High × (Risk % / 100)
Risk Per Point = Entry Price - Stop Loss Price
Risk Per Lot = Risk Per Point × Lot Size
Number of Lots = (Risk Amount / Risk Per Lot) × ER
Final Lots = max(1, round(Number of Lots))
```

- [ ] **Uses equity_high (realized equity only)** (Line ~183)
  ```pinescript
  var float equity_high = strategy.initial_capital
  if realized_equity > equity_high
      equity_high := realized_equity
  ```

- [ ] **Risk calculation correct** (Lines ~260-274)
  ```pinescript
  risk_amount = equity_high * (risk_percent / 100)
  risk_per_point = entry_price - stop_loss
  risk_per_lot = risk_per_point * lot_size
  num_lots = risk_per_lot > 0 ? (risk_amount / risk_per_lot) * er : 0
  ```

- [ ] **Division by zero protection**
  - Check: `risk_per_lot > 0` before division
  - Fallback: 0 lots if invalid

- [ ] **Minimum position size enforced**
  - `final_lots = math.max(1, math.round(num_lots))`
  - Or margin check prevents entry if < 1 lot affordable

- [ ] **Margin-based lot calculation**
  - Calculate risk-based lots
  - Calculate margin-based lots
  - Take minimum of both
  - Ensures never exceed available margin

---

## PYRAMIDING LOGIC VERIFICATION

### 7. Pyramid Triggers

From STRATEGY_LOGIC_SUMMARY.md:

1. ATR Movement: Price moved >= 0.5 ATR from last entry
2. Profitability Check: Position must be profitable
3. Margin Availability: Sufficient margin available
4. Maximum Count: Cannot exceed 3 pyramids

- [ ] **ATR movement check** (Lines ~306-307)
  ```pinescript
  price_move_from_last = close - last_pyramid_price
  atr_moves = price_move_from_last / atr_pyramid
  ```

- [ ] **Profitability check** (Line ~310)
  ```pinescript
  position_is_profitable = unrealized_pnl > 0
  ```

- [ ] **Margin availability check** (Lines ~314-340)
  - Calculate current margin used
  - Calculate free margin
  - Calculate pyramid size from ratio
  - Calculate pyramid size from margin
  - Take minimum
  - Verify total doesn't exceed available

- [ ] **Count limit check** (Line ~304)
  ```pinescript
  pyramid_count < max_pyramids
  ```

### 8. Pyramid Position Sizing

- [ ] **Geometric scaling at 50%**
  - Long_1: base_size
  - Long_2: base_size × 0.5
  - Long_3: base_size × 0.5²
  - Long_4: base_size × 0.5³

- [ ] **Entry price tracking** (Lines ~184-187)
  ```pinescript
  var float initial_entry_price = na
  var float pyr1_entry_price = na
  var float pyr2_entry_price = na
  var float pyr3_entry_price = na
  ```

- [ ] **Entry prices set on pyramid add** (Lines ~354-371)

- [ ] **Unique entry IDs** (Line ~374)
  ```pinescript
  "Long_" + str.tostring(pyramid_count + 1)
  ```

---

## MARGIN MANAGEMENT VERIFICATION

### 9. Margin Calculations

From STRATEGY_LOGIC_SUMMARY.md:

- [ ] **Realized equity used for margin** (Lines ~219-221)
  ```pinescript
  realized_equity_lakhs = realized_equity / 100000
  available_margin_lakhs = use_leverage ? realized_equity_lakhs * leverage_multiplier : realized_equity_lakhs
  ```

- [ ] **Current margin used calculation** (Line ~222)
  ```pinescript
  current_margin_used_display = strategy.position_size * margin_per_lot
  ```

- [ ] **Margin remaining calculation** (Line ~223)
  ```pinescript
  margin_remaining = available_margin_lakhs - current_margin_used_display
  ```

- [ ] **Margin utilization percentage** (Line ~224)
  ```pinescript
  margin_utilization_pct = available_margin_lakhs > 0 ? (current_margin_used_display / available_margin_lakhs) * 100 : 0
  ```

- [ ] **Pyramid margin checks prevent over-leverage** (Lines ~327-339)
  - Calculate margin required for pyramid
  - Calculate total margin after pyramid
  - If would exceed available, reduce pyramid size
  - Ensure total <= available margin

---

## STATE MANAGEMENT VERIFICATION

### 10. Variable Initialization

- [ ] **All state variables use `var` keyword** (Lines ~183-200)

- [ ] **Proper initialization values**
  - equity_high: strategy.initial_capital
  - Entry prices: na
  - Pyramid count: 0
  - Position size: 0
  - Stops: na

### 11. State Reset on Exit

- [ ] **SuperTrend Mode reset** (Lines ~386-392)
  ```pinescript
  initial_entry_price := na
  pyr1_entry_price := na
  pyr2_entry_price := na
  pyr3_entry_price := na
  last_pyramid_price := na
  pyramid_count := 0
  initial_position_size := 0
  ```

- [ ] **Van Tharp Mode reset** (Lines ~447-454)
  - Individual position resets when closed
  - Full reset when all positions closed

- [ ] **Tom Basso Mode reset** (Lines ~517-520)
  - Individual stop tracking reset per position
  - Pyramid tracking reset when all closed

---

## INDICATOR CALCULATIONS VERIFICATION

### 12. Efficiency Ratio (Custom Implementation)

From specifications (Lines ~113-119):

```pinescript
ER(src, p, dir) =>
    a = dir ? src - src[p] : math.abs(src - src[p])
    b = 0.0
    for i = 0 to p-1
        b := b + math.abs(src[i] - src[i+1])
    result = b != 0 ? a / b : 0
    result
```

- [ ] **Formula matches spec**
- [ ] **Period = 3**
- [ ] **Directional = false**
- [ ] **Division by zero protected** (b != 0 check)

### 13. SuperTrend

- [ ] **Period: 10** (Line ~44)
- [ ] **Multiplier: 1.5** (Line ~45)
- [ ] **Uses ta.supertrend()** - non-repainting

### 14. Donchian Channel

- [ ] **Period: 20** (Line ~27)
- [ ] **Uses [1] offset** (Lines ~105-106)
  - **CRITICAL:** Prevents lookahead bias
  - Excludes current bar from calculation

---

## DISPLAY & INFO PANEL VERIFICATION

### 15. Smart Info Panel Logic

- [ ] **Context-aware switching** (Line ~592)
  ```pinescript
  in_position = strategy.position_size > 0
  show_indicators = (smart_panel and not in_position) or show_all_info
  show_trade_info = (smart_panel and in_position) or show_all_info
  ```

- [ ] **When FLAT:** Shows entry conditions
- [ ] **When IN POSITION:** Shows trade management info

### 16. Risk Exposure Display

- [ ] **Risk calculation uses entry-to-stop distance** (Lines ~253-256)
  ```pinescript
  risk_long1 = not na(initial_entry_price) and not na(display_stop_long1) ?
      math.max(0, (initial_entry_price - display_stop_long1) * initial_position_size * lot_size) : 0
  ```

- [ ] **Total risk exposure** (Line ~257)
  ```pinescript
  total_risk_exposure = risk_long1 + risk_long2 + risk_long3 + risk_long4
  ```

---

## CODE QUALITY CHECKS

### 17. Compilation Safety

From CODE_QUALITY_CHECKLIST.md:

- [ ] **No empty code blocks**
  - Check all if/else structures have code or are removed

- [ ] **All string concatenations use str.tostring()**
  - Search for: `"string" + numeric_variable`
  - Must use: `"string" + str.tostring(numeric_variable, format)`

- [ ] **All plot() calls at global scope**
  - Use ternary: `plot(condition ? value : na, "Name")`
  - NOT inside if blocks

- [ ] **No hline() with display.pane**
  - hline() only accepts display.none or display.all
  - display.pane only works with plot()

- [ ] **Overlay and force_overlay correct**
  - If overlay=true: everything on main chart
  - If overlay=false: use force_overlay=true for main chart plots

### 18. Logic Safety

- [ ] **No division by zero**
  - Check all divisions have denominator > 0 check
  - Check ATR > 0 before dividing

- [ ] **No infinite loops**
  - Only loop: ER calculation (fixed 3 iterations)

- [ ] **Table size matches usage**
  - Count all table.cell() calls
  - Verify table size accommodates all

---

## TESTING & VALIDATION CHECKLIST

### 19. Visual Verification (Manual)

- [ ] Load code in TradingView Pine Editor
- [ ] Verify compilation - no errors
- [ ] Add to chart (75-minute Bank Nifty)
- [ ] **CRITICAL:** Find a trade exit and verify:
  - Exit arrow appears ONLY when bar CLOSES below SuperTrend
  - NOT when price temporarily dips below during bar formation

### 20. Backtest Verification

- [ ] Run backtest on known period
- [ ] **Verify max drawdown ~ 28-29%** (established baseline)
- [ ] If DD significantly different → investigate
- [ ] Check trade list for correct entry/exit comments
- [ ] Verify position sizes make sense

### 21. Edge Case Testing

- [ ] **What happens when ATR = 0?**
  - Should not crash
  - Should fall back to minimum position

- [ ] **What happens when stop = entry?**
  - Division by zero protection
  - Should enter with minimum position or skip

- [ ] **What happens when margin exhausted?**
  - Should block pyramids
  - Should show in margin panel

---

## REGRESSION PREVENTION

### 22. Compare Against Backup

- [ ] **trend_following_strategy_backup_2025-11-10.pine** is proven version
- [ ] Any changes must not:
  - Increase max drawdown significantly (>30%)
  - Break entry/exit logic
  - Remove safety checks
  - Introduce repainting

### 23. Performance Baseline

From FINAL_PRODUCTION_CERTIFICATION.md:

**Established Baseline (SuperTrend Mode):**
- Total Return: +2,694%
- Max DD: 28.74%
- Profit Factor: 1.952
- Win Rate: 48.78%
- Total Trades: 576

- [ ] **Any code changes:** Run backtest and compare
- [ ] **If DD increases > 5%:** Investigate cause
- [ ] **If trades decrease > 20%:** Check entry logic
- [ ] **If profit factor drops > 0.3:** Review exit logic

---

## CRITICAL BUG HISTORY

### Bug #1: Exit Timing (2025-11-14)

**Issue:** Exits triggered on intra-bar ticks instead of bar close
**Cause:** `calc_on_every_tick=true` + no `barstate.isconfirmed` on exits
**Symptom:** Trades exiting even when final close above SuperTrend
**Fix:** Added `and barstate.isconfirmed` to all exit conditions
**Lines Fixed:** 384, 404, 417, 430, 443, 477, 489, 501, 513

**Prevention:**
- ALWAYS check execution timing when `calc_on_every_tick=true`
- ALWAYS use `barstate.isconfirmed` for exit conditions
- ALWAYS test visually on chart to verify exit timing

---

## FINAL SIGN-OFF CHECKLIST

Before declaring code "production ready":

- [ ] ✅ ALL execution timing checks passed
- [ ] ✅ ALL Pine Script checks passed
- [ ] ✅ ALL strategy logic verified correct
- [ ] ✅ ALL position sizing verified correct
- [ ] ✅ ALL pyramiding logic verified correct
- [ ] ✅ ALL margin management verified correct
- [ ] ✅ ALL state management verified correct
- [ ] ✅ ALL indicator calculations verified correct
- [ ] ✅ ALL code quality checks passed
- [ ] ✅ ALL display logic verified correct
- [ ] ✅ Compiled successfully in TradingView
- [ ] ✅ Visual verification on chart completed
- [ ] ✅ Backtest shows expected baseline performance
- [ ] ✅ No regressions from proven version

**ONLY THEN** can code be certified as production ready.

---

## USAGE INSTRUCTIONS

1. **ALWAYS** use this checklist before code review
2. **ALWAYS** check execution timing FIRST (most critical)
3. **NEVER** skip visual verification on TradingView
4. **NEVER** assume logic is correct without testing
5. **ALWAYS** compare backtest to baseline

**This checklist exists because we missed a critical bug. Don't let it happen again.**

---

**Document Version:** 1.0
**Created:** 2025-11-14
**Trigger:** Exit timing bug discovery
**Purpose:** Ensure comprehensive review catches all issues
**Status:** ✅ Ready for use

