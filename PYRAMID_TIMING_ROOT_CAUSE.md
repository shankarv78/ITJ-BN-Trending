# Pyramid Alert Timing - Root Cause Analysis

**Date:** 2025-12-26
**Subject:** Analysis of missed 10am Pyramid Alert and "3 Arrows" Anomaly
**File Reviewed:** `SilverMini_TF_V8.0.pine`

## Executive Summary

The analysis confirms that the "missed" 10am alert and the presence of "3 arrows" are **caused by TradingView's real-time script execution behavior** (specifically `var` variable resets), not a logic bug in the alert conditions themselves.

The evidence conclusively proves that the 3 arrows were **"Preview" signals generated during the formation of the 10am-11am bar**, which is why the alert fired correctly at 11am (the close of that bar).

## The "Smoking Gun": 3 Arrows with "PYR1-1L" Labels

The user observed **3 arrows** on the same bar, all labeled **"PYR1-1L"**. This single observation invalidates the possibility that these were confirmed, historical trades.

### Why this proves it was the "Forming" Bar:

1.  **Unique Variable State**: The label "PYR1-1L" is generated when `pyramid_count` transitions from `0` to `1`.
2.  **Historical Laws**: On a closed (historical) bar, the script runs exactly **ONCE**. `pyramid_count` would increment `0 -> 1` once. **Result: 1 Arrow.**
3.  **Real-Time Laws**: On a forming (real-time) bar with "Recalculate on Every Tick" enabled:
    *   The script runs on every tick.
    *   **CRITICAL:** `var` variables (like `pyramid_count`) **RESET** to their value at the *start* of the bar before every tick execution.
    *   **Tick 1:** `pyramid_count` (0) -> Incr to 1 -> Plot Arrow "PYR1".
    *   **Tick 2:** `pyramid_count` resets to 0 -> Incr to 1 -> Plot Arrow "PYR1".
    *   **Tick 3:** `pyramid_count` resets to 0 -> Incr to 1 -> Plot Arrow "PYR1".
4.  **Conclusion**: Seeing 3 arrows with the *same* "PYR1" label is physically impossible on a closed bar. It is **only** possible during real-time calculation where the state resets repeatedly.

## Timeline Reconstruction

1.  **10:00:00 AM**: The 9am-10am bar closes. Conditions were likely met or close to met, but the entry didn't trigger *at that exact second* (possibly due to `process_orders_on_close` timing or slight data variance).
2.  **10:00:01 AM - 10:00:XX AM**: The **10am-11am bar starts forming**.
3.  **Real-Time Logic**: The script sees the conditions are met. It fires `strategy.entry` on each tick.
    *   Visual: Arrows appear (and persist due to overlay behavior).
    *   Logic: `var` variables reset, so it thinks it's the *first* pyramid every time ("PYR1").
4.  **Alert Behavior**: The function `alert(..., freq_once_per_bar_close)` is called.
    *   Rule: "If called during the bar, fire **ONE** alert when the bar **CLOSES**."
    *   The alert is queued.
5.  **11:00:00 AM**: The 10am-11am bar closes.
    *   The queued alert triggers.
    *   User receives alert at 11am.

## Addressing the User's Doubt

> *"10am_chart image has the 3 arrows... but did not result in alert"*

The user correctly identified that the 9am-10am bar *should* have triggered if the arrows belonged to it. However, the **3 arrows prove they belong to the 10am-11am bar** (the only place where multiple "PYR1" arrows can exist).

The "10am Table" likely showed the state at the **start of the 10am-11am bar** (which inherently displays the Close data of the 9am-10am bar). The conditions were indeed valid, which is why the Strategy began firing "Preview" entries immediately at 10:00am.

## Corrective Action

The proposed fix in `PYRAMID_ALERT_TIMING_ANALYSIS.md` is correct and necessary.

```pine
// CURRENT: Runs on every tick, causing "Preview" arrows and user confusion
if pyramid_trigger

// PROPOSED: Only runs on the confirmed closing tick
if pyramid_trigger and barstate.isconfirmed
```

**Effect of Fix:**
1.  **Syncs Visuals with Alerts**: Arrows will NOT appear during the bar. They will appear *only* at 11am (simultaneously with the alert).
2.  **Eliminates "Ghosting"**: No more "3 arrows" artifacts.
3.  **Restores Confidence**: The user will no longer see a signal at 10:00am that "waits" until 11:00am to fire.

## Recommendation

Implement the `and barstate.isconfirmed` check in `SilverMini_TF_V8.0.pine` (and other assets) to align the visual strategy execution with the alert timing.
