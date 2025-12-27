# Pine Script Pyramid Alert Timing Bug - Analysis

**Date:** 2025-12-26
**Status:** Analysis Complete - Awaiting User Review

---

## Problem Statement

**Issue:** Missing Long_2 (first pyramid, PYR1) alert at 10am

**User observed at 10am (after 9am-10am bar close):**
- Chart shows 3 pyramid arrows labeled "PYR1-1L" on the same bar
- Info table shows ALL pyramid conditions are met:
  - Pyramid Gate: OPEN (v5.2: Price > 1R)
  - ATR Spacing: 3.63 ATR (need 1.5)
  - Lot-A (Margin): 21 lots
  - Lot-B (50%): 1 lots
  - Lot-C (Risk): 1 lots
  - Next Pyramid: 1 lots (limited by 50% Rule)
- But the webhook ALERT didn't fire at 10am
- Alert fired at 11am instead (1 hour late, verified in TradingView alert log)

**Core Mystery:** Why does `strategy.entry()` show executed (arrows visible) but `alert()` didn't fire at the same time?

---

## Code Analysis (Verified from SilverMini_TF_V8.0.pine)

### Strategy Settings

```pine
strategy("Silver Mini Trend Following Strategy v8.0 (EOD PreClose)",
     calc_on_every_tick=false,     // Code says once at bar close
     process_orders_on_close=true, // Orders execute at bar close price
     ...)
```

**CRITICAL: UI Override**
- TradingView Properties panel has "On every tick" **CHECKED**
- This **overrides** the code setting `calc_on_every_tick=false`
- Script runs on every price update during live bars

### Pyramid Entry Logic (NO barstate.isconfirmed)

```pine
// Trigger: Gate open AND price moved AND ROC OK AND >= 1 lot
pyramid_trigger = pyramid_gate_open and atr_moves_from_last >= atr_pyramid_threshold and roc_ok_for_pyramid and pyramid_lots >= 1

if pyramid_trigger    // <-- NO barstate.isconfirmed check

    // Update tracking
    pyramid_count := pyramid_count + 1
    last_pyramid_price := close

    // ... pyramid entry and stop initialization ...

    // Enter pyramid
    strategy.entry("Long_" + str.tostring(pyramid_count + 1), strategy.long, qty=pyramid_lots,
                   comment="PYR" + str.tostring(pyramid_count) + "-" + str.tostring(pyramid_lots) + "L")

    // JSON Alert for PYRAMID
    alert(json_pyramid, alert.freq_once_per_bar_close)
```

### Exit Logic (HAS barstate.isconfirmed)

```pine
if close < supertrend and barstate.isconfirmed    // <-- HAS barstate.isconfirmed
    // ... exit logic ...
    // Comment: "ONLY check at bar close (not on every tick) to avoid premature exits"
```

---

## Key Evidence

| Evidence | Implication |
|----------|-------------|
| 3 arrows with "PYR1-1L" on same bar | Script executed 3 times, or rendering artifact |
| All 3 arrows have SAME label "PYR1-1L" | `pyramid_count` not persisting between executions |
| Alert log shows 11am | Alert fired at 10am-11am bar close, not 9am-10am |
| Info panel shows conditions met | Pyramid logic evaluated as TRUE |
| Long_2 SL: NaN | Stop was never initialized (pyramid_count issue?) |

### Why 3 Identical "PYR1-1L" Labels?

If `pyramid_count` was incrementing correctly between executions:
- 1st execution: pyramid_count=0 -> 1, label="PYR1-1L"
- 2nd execution: pyramid_count=1 -> 2, label="PYR2-1L"
- 3rd execution: pyramid_count=2 -> 3, label="PYR3-1L"

**All showing "PYR1-1L" suggests:**
- `var` variables (pyramid_count) NOT persisting between preview renders
- Each preview starts fresh with pyramid_count=0
- Only the "official" bar close run persists state

---

## Entry vs Exit Logic Discrepancy

**EXIT logic uses `barstate.isconfirmed`** (13 places in the script):
- Comment: "ONLY check at bar close (not on every tick) to avoid premature exits"

**ENTRY logic does NOT use `barstate.isconfirmed`**:
- Base entry (long_entry check) - no check
- Pyramid entry (pyramid_trigger check) - no check

**This is an inconsistency!** Exits are guarded against preview execution, but entries are not.

---

## Root Cause Analysis (REVISED)

### Critical Clarification from User

**User confirmed:** All 3 arrows appeared **AT THE END** of the 9am-10am candle (at bar close), NOT during candle formation.

This means:
- Arrows ARE on the 9am-10am bar
- Arrows appeared at exactly 10:00 (bar close)
- This is NOT preview behavior - it's a **genuine timing bug**

### What Actually Happened

1. 9am-10am bar closes at 10:00
2. Script evaluates at bar close (multiple times due to "On every tick")
3. `pyramid_trigger` = TRUE
4. `strategy.entry()` executes → 3 arrows appear on 9am-10am bar at 10:00
5. `alert()` called with `freq_once_per_bar_close`
6. **Alert SHOULD fire at 10:00 but DIDN'T**
7. Alert fired at 11:00 instead (next bar close)

### Why 3 "PYR1-1L" markers on same bar?

With "On every tick" enabled, script runs multiple times at bar close:
- Each execution starts with `pyramid_count = 0` (from previous bar)
- Each increments to 1 and generates "PYR1-1L"
- `var` variable assignments don't persist until the "final" bar close calculation
- Only 3 markers appeared (not 100+) - TradingView likely throttles visualizations

### Most Likely Root Cause (RESEARCH COMPLETED - HYPOTHESIS DISPROVEN)

**Research Findings (from TradingView official documentation):**

1. **`freq_once_per_bar_close` works correctly** regardless of `calc_on_every_tick` setting
2. **Multiple `alert()` calls are independent** - each fires once per bar, no timing issues
3. **No documented bug** about alerts being delayed to next bar close
4. The alert frequency parameter **takes precedence** over calculation frequency

**Original hypothesis was WRONG:**
- "On every tick" + `freq_once_per_bar_close` does NOT cause alert queue confusion
- This is NOT a documented TradingView behavior

**The 1-hour delay remains UNEXPLAINED by official TradingView documentation.**

**Possible remaining explanations:**
1. Undocumented TradingView behavior/edge case
2. Network/webhook delivery issue (though user verified via TV alert log)
3. Something specific to the chart/instrument/timeframe combination
4. TradingView internal processing delay during high-activity periods

**Sources:**
- [TradingView Pine Script Docs - Alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/)
- [TradingView Support - Alert Frequencies](https://www.tradingview.com/support/solutions/43000474415-differences-between-alert-frequencies/)
- [TradingView Pine Script Docs - Execution Model](https://www.tradingview.com/pine-script-docs/language/execution-model/)

---

## Proposed Fix

### Add `barstate.isconfirmed` to Pyramid Entry

**Before:**
```pine
if pyramid_trigger
```

**After:**
```pine
// ONLY execute at confirmed bar close (consistent with exit logic)
if pyramid_trigger and barstate.isconfirmed
```

### Files to Update

| File | Search for | Add `and barstate.isconfirmed` |
|------|------------|-------------------------------|
| `SilverMini_TF_V8.0.pine` | `if pyramid_trigger` | Yes |
| `GoldMini_TF_V8.0.pine` | `if pyramid_trigger` | Yes |
| `BankNifty_TF_V8.0.pine` | `if pyramid_trigger` | Yes |
| `Copper_TF_V8.0.pine` | `if pyramid_trigger` | Yes |

### Expected Outcome

After this change:
- Pyramid arrows will ONLY appear at confirmed bar close (no preview arrows)
- Alert and visualization will be synchronized
- Behavior consistent with exit logic (which already uses `barstate.isconfirmed`)
- No more confusing "early" arrows that suggest alert should have fired
- No more 3 identical "PYR1-1L" labels on same bar

---

## Why `barstate.isconfirmed` Should Help

Adding `barstate.isconfirmed` to the pyramid entry condition should fix this by:

1. **Ensuring exactly ONE execution at confirmed bar close** - eliminates the 3 duplicate executions
2. **Eliminating multiple `alert()` calls** - only one call, less chance of alert queue confusion
3. **Making behavior consistent with exit logic** - exits already use `barstate.isconfirmed` and don't have this timing issue

---

## Status

**Analysis complete (RESEARCH UPDATED 2025-12-26):**

**What we know:**
- This is a genuine timing anomaly, not preview behavior
- Arrows appeared at 9am-10am bar close (10:00)
- Alert fired at 11:00 (next bar close) - verified in TV alert log
- TradingView UI has "On every tick" enabled

**Research conclusion:**
- Original hypothesis about `freq_once_per_bar_close` + "On every tick" interaction was WRONG
- No documented TradingView bug explains the 1-hour delay
- The root cause remains **UNKNOWN**

**Proposed fix (still recommended despite unknown root cause):**
Adding `barstate.isconfirmed` to pyramid entry logic would:
1. Ensure exactly ONE execution at confirmed bar close (eliminates 3 duplicate arrows)
2. Make behavior consistent with exit logic (which works correctly)
3. Is a defensive coding best practice per TradingView documentation

**Open questions:**
- Why did alert fire at 11:00 instead of 10:00?
- Is this reproducible or a one-time occurrence?
- Would `barstate.isconfirmed` fix prevent this (uncertain)?

Awaiting user decision on whether to implement the proposed fix.
