# Task 32.9: EOD_MONITOR Alert Generation - Corrected Implementation

## Overview

Add EOD_MONITOR alert generation to `BankNifty_TF_V7.0.pine` (NOT v6) to enable pre-close order execution.

**Target File:** `/Users/shankarvasudevan/claude-code/ITJ-BN-Trending/BankNifty_TF_V7.0.pine`

---

## Python Backend Requirements

The webhook parser (`core/webhook_parser.py:288-339`) expects this exact JSON structure:

```json
{
    "type": "EOD_MONITOR",
    "instrument": "BANK_NIFTY",
    "timestamp": "2025-12-02T15:25:00Z",
    "price": 52450.50,
    "conditions": {
        "rsi_condition": true,
        "ema_condition": true,
        "dc_condition": true,
        "adx_condition": true,
        "er_condition": true,
        "st_condition": true,
        "not_doji": true,
        "long_entry": true,
        "long_exit": false
    },
    "indicators": {
        "rsi": 72.5,
        "ema": 51800.25,
        "dc_upper": 52300.00,
        "adx": 28.5,
        "er": 0.85,
        "supertrend": 52100.00,
        "atr": 180.5
    },
    "position_status": {
        "in_position": false,
        "pyramid_count": 0
    },
    "sizing": {
        "suggested_lots": 8,
        "stop_level": 52100.00
    }
}
```

### Required Fields (must match exactly)

| Section | Fields |
|---------|--------|
| Top-level | `type`, `instrument`, `timestamp`, `price`, `conditions`, `indicators`, `position_status`, `sizing` |
| conditions | `rsi_condition`, `ema_condition`, `dc_condition`, `adx_condition`, `er_condition`, `st_condition`, `not_doji`, `long_entry`, `long_exit` |
| indicators | `rsi`, `ema`, `dc_upper`, `adx`, `er`, `supertrend`, `atr` |
| position_status | `in_position`, `pyramid_count` |
| sizing | `suggested_lots`, `stop_level` |

---

## v7.0 Existing Infrastructure to Leverage

### Already Available Variables

| Variable | Line | Purpose |
|----------|------|---------|
| `timestamp_str` | 1183 | ISO 8601 timestamp |
| `rsi_condition` | 302 | RSI > 70 |
| `ema_condition` | 303 | Close > EMA(200) |
| `dc_condition` | 304 | Close > DC Upper |
| `adx_condition` | 305 | ADX < 30 (LOW ADX!) |
| `er_condition` | 306 | ER > 0.8 |
| `st_condition` | 307 | Close > SuperTrend |
| `not_doji` | 308 | Body > 10% of range |
| `long_entry` | 314 | All 7 conditions combined |
| `long_exit` | 317 | Close < SuperTrend |
| `is_eod_candle` | 294 | hour >= 14 and minute >= 15 |
| `is_market_close` | 295 | hour == 15 and minute >= 15 |
| `rsi`, `ema`, `dc_upper`, `adx`, `er`, `supertrend`, `atr_pyramid` | Various | Indicator values |
| `pyramid_count` | 342 | Current pyramid count |
| `initial_position_size` | 344 | Base position size |
| `initial_entry_price` | 335 | Entry price |

---

## Implementation Plan

### Step 1: Add EOD Configuration Inputs (after line 221)

Insert after the "Trade Start Date Filter" section:

```pine
// ========================================
// EOD PRE-CLOSE MONITORING SETTINGS
// ========================================
enable_eod_monitoring = input.bool(true, "Enable EOD Pre-Close Monitoring", group="EOD Settings",
    tooltip="Send EOD_MONITOR alerts during the last bar before market close for pre-close execution")
```

### Step 2: Add EOD_MONITOR Alert Generation (after line 1282, end of existing alerts)

Insert after the existing EXIT alerts:

```pine
// ========================================
// EOD PRE-CLOSE MONITORING ALERT
// ========================================
// Sends EOD_MONITOR signal during the last bar of the day (2:15-3:30 PM for Bank Nifty)
// Python uses this to execute orders ~30 seconds before market close
//
// On 75-min timeframe, the last bar covers 2:15-3:30 PM, which is the entire EOD window.
// We send one alert per bar with all current indicator values.

// EOD window: After 2:15 PM but before 3:30 PM (is_eod_candle is defined at line 294)
// Only send if we're in the last bar and EOD monitoring is enabled
if enable_eod_monitoring and is_eod_candle

    // Calculate suggested lots for potential entry
    eod_suggested_lots = 0
    eod_stop_level = supertrend

    // If not in position, calculate entry lots
    if strategy.position_size == 0 and long_entry
        eod_risk_amount = current_equity * (risk_percent / 100)
        eod_risk_per_lot = (close - supertrend) * lot_size
        eod_risk_lots = eod_risk_per_lot > 0 ? (eod_risk_amount / eod_risk_per_lot) * er : 0
        eod_risk_lots_floored = math.floor(eod_risk_lots)
        eod_margin_lots = available_margin_lakhs > 0 ? math.floor(available_margin_lakhs / margin_per_lot) : 0
        eod_suggested_lots := math.max(0, math.min(eod_risk_lots_floored, eod_margin_lots))

    // If in position with pyramid potential, calculate pyramid lots
    else if strategy.position_size > 0 and enable_pyramiding and pyramid_count < max_pyramids
        eod_gate_open = use_1r_gate ? (price_move_from_entry > initial_risk_points) : (accumulated_profit > base_risk)
        eod_price_move = close - last_pyramid_price
        eod_atr_moves = eod_price_move / atr_pyramid
        eod_roc_ok = use_roc_for_pyramids ? roc > roc_threshold : true

        if eod_gate_open and eod_atr_moves >= atr_pyramid_threshold and eod_roc_ok
            // Calculate triple-constraint lots
            eod_margin_used = strategy.position_size * margin_per_lot
            eod_free_margin = available_margin_lakhs - eod_margin_used
            eod_lot_a = eod_free_margin > 0 ? math.floor(eod_free_margin / margin_per_lot) : 0
            eod_lot_b = math.floor(initial_position_size * 0.5)
            eod_profit_after_risk = accumulated_profit - base_risk
            eod_risk_budget = eod_profit_after_risk * 0.5
            eod_pyr_stop = stop_loss_mode == "SuperTrend" ? supertrend : (not na(basso_stop_long1) ? basso_stop_long1 : supertrend)
            eod_pyr_risk_lot = (close - eod_pyr_stop) * lot_size
            eod_lot_c = eod_pyr_risk_lot > 0 ? math.floor(eod_risk_budget / eod_pyr_risk_lot) : 0
            eod_suggested_lots := math.max(0, math.min(eod_lot_a, math.min(eod_lot_b, eod_lot_c)))
            eod_stop_level := eod_pyr_stop

    // If in position and should exit, set lots to current position
    else if strategy.position_size > 0 and long_exit
        eod_suggested_lots := strategy.position_size

    // Build EOD_MONITOR JSON - MUST match Python webhook_parser.py expected structure
    // Field names must match exactly: rsi_condition, ema_condition, etc.

    json_conditions = '"conditions":{' +
        '"rsi_condition":' + str.tostring(rsi_condition) + ',' +
        '"ema_condition":' + str.tostring(ema_condition) + ',' +
        '"dc_condition":' + str.tostring(dc_condition) + ',' +
        '"adx_condition":' + str.tostring(adx_condition) + ',' +
        '"er_condition":' + str.tostring(er_condition) + ',' +
        '"st_condition":' + str.tostring(st_condition) + ',' +
        '"not_doji":' + str.tostring(not_doji) + ',' +
        '"long_entry":' + str.tostring(long_entry) + ',' +
        '"long_exit":' + str.tostring(long_exit) + '}'

    json_indicators = '"indicators":{' +
        '"rsi":' + str.tostring(rsi) + ',' +
        '"ema":' + str.tostring(ema) + ',' +
        '"dc_upper":' + str.tostring(dc_upper) + ',' +
        '"adx":' + str.tostring(adx) + ',' +
        '"er":' + str.tostring(er) + ',' +
        '"supertrend":' + str.tostring(supertrend) + ',' +
        '"atr":' + str.tostring(atr_pyramid) + '}'

    json_position = '"position_status":{' +
        '"in_position":' + str.tostring(strategy.position_size > 0) + ',' +
        '"pyramid_count":' + str.tostring(pyramid_count) + '}'

    json_sizing = '"sizing":{' +
        '"suggested_lots":' + str.tostring(eod_suggested_lots) + ',' +
        '"stop_level":' + str.tostring(eod_stop_level) + '}'

    // Complete EOD_MONITOR JSON
    eod_json = '{"type":"EOD_MONITOR",' +
        '"instrument":"BANK_NIFTY",' +
        '"timestamp":"' + timestamp_str + '",' +
        '"price":' + str.tostring(close) + ',' +
        json_conditions + ',' +
        json_indicators + ',' +
        json_position + ',' +
        json_sizing + '}'

    // Send alert once per bar during EOD window
    alert(eod_json, alert.freq_once_per_bar)
```

---

## Key Implementation Notes

### 1. Correct Condition Logic

The v7.0 strategy conditions are already correctly defined:

```pine
// Line 302-308 in v7.0 - ALL CORRECT
rsi_condition = rsi > rsi_threshold        // RSI > 70 (NOT > 50)
ema_condition = close > ema                // Close > EMA(200)
dc_condition = close > dc_upper            // Close > DC Upper
adx_condition = adx < adx_threshold        // ADX < 30 (LOW ADX, not above!)
er_condition = er > er_threshold           // ER > 0.8 (NOT > 0.3)
st_condition = close > supertrend          // Close > SuperTrend
not_doji = not is_doji                     // 7th condition - NOT a doji
```

### 2. Timestamp Already Defined

v7.0 already has `timestamp_str` at line 1183:
```pine
timestamp_str = str.tostring(year) + "-" + str.tostring(month, "#00") + "-" +
    str.tostring(dayofmonth, "#00") + "T" + str.tostring(hour, "#00") + ":" +
    str.tostring(minute, "#00") + ":00Z"
```

### 3. EOD Window Detection

v7.0 already has EOD detection at lines 294-295:
```pine
is_eod_candle = hour(time) >= 14 and minute(time) >= 15  // After 2:15 PM
is_market_close = hour(time) == 15 and minute(time) >= 15  // After 3:15 PM
```

For EOD_MONITOR, we use `is_eod_candle` which covers the last 75-minute bar (2:15-3:30 PM).

### 4. One Alert Per Bar

On 75-minute timeframe, the last bar (2:15-3:30 PM) covers the entire EOD window. We send **one EOD_MONITOR alert per bar** using `alert.freq_once_per_bar`.

The Python EODScheduler handles precise timing:
- T-45 sec (3:29:15): Final condition check
- T-30 sec (3:29:30): Place order
- T-15 sec (3:29:45): Track completion

---

## Gold Mini Support (Future)

For Gold Mini (`GoldMini_TF_V7.0.pine`), the same pattern applies but with:
- Different close time (23:30 summer / 23:55 winter IST)
- Different instrument name: `"GOLD_MINI"`
- MCX-specific EOD detection

---

## Testing Checklist

### Pine Script Validation
- [ ] Script compiles without errors
- [ ] `enable_eod_monitoring` input appears in settings
- [ ] Alert fires during last bar (2:15-3:30 PM window)
- [ ] JSON structure matches expected format

### JSON Field Validation
- [ ] `type` = "EOD_MONITOR"
- [ ] `instrument` = "BANK_NIFTY"
- [ ] `timestamp` is valid ISO 8601
- [ ] `price` is current close
- [ ] All 9 condition fields present with correct boolean values
- [ ] All 7 indicator fields present with numeric values
- [ ] `in_position` and `pyramid_count` correct
- [ ] `suggested_lots` and `stop_level` calculated correctly

### Webhook Integration
- [ ] Portfolio manager receives EOD_MONITOR webhook
- [ ] `parse_eod_monitor_signal()` returns valid EODMonitorSignal
- [ ] EODMonitor state updates correctly
- [ ] EODScheduler triggers at correct times

---

## Comparison: Old Plan vs Corrected

| Aspect | Old Plan (Wrong) | Corrected |
|--------|------------------|-----------|
| Target file | `v6.pine` | `BankNifty_TF_V7.0.pine` |
| RSI condition | `rsi > 50` | `rsi_condition` (RSI > 70) |
| ADX condition | `adx > 25` | `adx_condition` (ADX < 30) |
| ER condition | `er > 0.3` | `er_condition` (ER > 0.8) |
| 7th condition | Missing | `not_doji` |
| timestamp_str | Create new | Use existing (line 1183) |
| EOD detection | New functions | Use existing `is_eod_candle` |
| Signal interval | 60 sec (broken) | Once per bar |
| Condition field names | Generic | Exact match to Python |

---

## Files to Modify

1. **`BankNifty_TF_V7.0.pine`** (~80 lines added)
   - Add EOD configuration input (1 line)
   - Add EOD_MONITOR alert generation (~75 lines)

2. **`GoldMini_TF_V7.0.pine`** (future, same pattern)
   - Adapt for MCX timing
   - Change instrument to "GOLD_MINI"

---

## Estimated Time

- Implementation: 1-2 hours
- TradingView testing: 1 hour
- Webhook integration testing: 1 hour
- **Total: 3-4 hours**
