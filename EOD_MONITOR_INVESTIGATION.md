# EOD_MONITOR Alert Investigation

**Date:** 2025-12-27
**Issue:** EOD_MONITOR alerts not firing during 23:40-23:55 window

## Problem Statement

User reported that EOD_MONITOR alerts were not being generated during the EOD window (23:40-23:55 IST) despite:
- Valid pyramid conditions being met
- TradingView UI showing "On every tick" enabled
- Alert configured with "Order fills and alert() function" trigger

The alert only fired at **23:55:02** (bar close), not continuously during the window.

## Root Cause

**The Pine Script has `calc_on_every_tick=false` (line 85)**

```pine
strategy("Silver Mini Trend Following Strategy v8.0 (EOD PreClose)",
     ...
     calc_on_every_tick=false,  // <-- THIS IS THE ISSUE
     ...
```

### How TradingView Alert Evaluation Works

| Setting | Chart Display | Alert Evaluation |
|---------|---------------|------------------|
| UI "On every tick" checked | Updates on every tick | May still use script setting |
| Script `calc_on_every_tick=false` | Overridden by UI for display | **Respected for alerts** |

The TradingView UI "On every tick" setting affects **chart visualization** but alerts still respect the script's `calc_on_every_tick` setting.

### Timeline of What Happened

```
23:00:00 - 1-hour bar opens
23:40:00 - EOD window should start (is_eod_alert_window = true)
23:40-23:54 - Script NOT evaluating for alerts (calc_on_every_tick=false)
23:55:02 - Bar closes, script evaluates ONCE
         - timenow = 23:55, is_eod_alert_window = true
         - EOD_MONITOR alert fires (but too late for pre-close execution)
```

## EOD_MONITOR Code Analysis

### EOD Window Detection (Line 255)
```pine
is_eod_alert_window = hour(timenow) == 23 and minute(timenow) >= 40
```
- Uses `timenow` for real-time evaluation
- Requires script to run on every tick for real-time updates

### EOD_MONITOR Alert Block (Lines 1155-1177)
```pine
if enable_eod_monitoring and is_eod_alert_window
    // Build JSON with conditions, indicators, position status
    ...
    alert(eod_json, alert.freq_all)  // Fire on every tick
```
- `alert.freq_all` means fire on every occurrence
- But script only runs at bar close, so only fires once

## Solution

**Change `calc_on_every_tick=false` to `calc_on_every_tick=true`**

This is safe because:
1. Entry logic has `barstate.isconfirmed` guard (line 381)
2. Pyramid logic has `barstate.isconfirmed` guard (line 496)
3. Exit logic has `barstate.isconfirmed` guard (all exit blocks)
4. Only EOD_MONITOR (no barstate guard) will fire on every tick

### Files to Update

| File | Line | Change |
|------|------|--------|
| `SilverMini_TF_V8.0.pine` | 85 | `calc_on_every_tick=true` |
| `GoldMini_TF_V8.0.pine` | 85 | `calc_on_every_tick=true` |
| `BankNifty_TF_V8.0.pine` | 83 | `calc_on_every_tick=true` |
| `Copper_TF_V8.0.pine` | 33 | `calc_on_every_tick=true` |

## Verification Checklist

After applying the fix:
- [ ] EOD_MONITOR alerts fire continuously during 23:40-23:55
- [ ] Entry/Pyramid/Exit alerts still fire only at bar close
- [ ] Python receives multiple EOD_MONITOR signals during window
- [ ] Python executes at T-30 seconds as designed

## Related Issues Fixed in This Session

1. **Capital Injection Feature** - Added API endpoints and frontend UI for depositing/withdrawing capital
2. **Pine Script Text Visibility** - Added `textcolor=color.white` to plotshape calls
3. **barstate.isconfirmed** - Added to entry/pyramid logic for alert timing consistency

## Evidence

Alert log showing single trigger at bar close:
```
Last triggered: Fri 26 Dec 2025 23:55:02
```

Expected behavior after fix:
```
Triggered: Fri 26 Dec 2025 23:40:xx
Triggered: Fri 26 Dec 2025 23:41:xx
...
Triggered: Fri 26 Dec 2025 23:54:xx
```

---

## STATUS: UNRESOLVED (2025-12-27)

### What We Verified
1. ✅ TradingView UI "On every tick" is ENABLED (screenshot confirmed)
2. ✅ Alert configured with "Order fills and alert() function" trigger
3. ✅ `enable_eod_monitoring` input is TRUE
4. ✅ timenow returns IST correctly (verified in prior session)
5. ✅ Alert fires at bar close (23:55:02) - proves alert mechanism works

### The Problem
- EOD_MONITOR only fires ONCE at bar close (23:55)
- Does NOT fire continuously during 23:40-23:55 window
- Python needs continuous signals to execute at T-30 seconds

### Confirmed Root Cause
```pine
// Line 85 in SilverMini_TF_V8.0.pine
calc_on_every_tick=false,  // <-- THIS PREVENTS REAL-TIME ALERTS
```

The TradingView UI "On every tick" setting only affects chart display.
For ALERTS, TradingView respects the script's `calc_on_every_tick` setting.

### Fix Required (NOT YET APPLIED)
Change in ALL v8.0 Pine scripts:
```pine
calc_on_every_tick=true,
```

Files to modify:
- `SilverMini_TF_V8.0.pine` (line 85)
- `GoldMini_TF_V8.0.pine` (line 85)
- `BankNifty_TF_V8.0.pine` (line 83)
- `Copper_TF_V8.0.pine` (line 33)

### Why This is Safe
Entry/Pyramid/Exit logic already has `barstate.isconfirmed` guards:
- Line 381: `if long_entry and strategy.position_size == 0 and barstate.isconfirmed`
- Line 496: `if pyramid_trigger and barstate.isconfirmed`
- All exit blocks have `barstate.isconfirmed`

Only EOD_MONITOR (line 1155) has no guard - it SHOULD fire on every tick.

### Next Session Action
1. Apply `calc_on_every_tick=true` fix to all v8.0 scripts
2. Update script in TradingView
3. Test during next trading session (verify alerts fire during 23:40-23:55)
4. Confirm Python receives continuous EOD_MONITOR signals
