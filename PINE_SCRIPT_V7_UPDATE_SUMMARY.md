# Pine Script V7.0 Update Summary

**Date:** 2025-11-27  
**Status:** ✅ Complete

## Overview

Updated both Pine Scripts to generate complete JSON alerts matching the portfolio manager's `Signal` dataclass requirements. Files renamed to V7.0 with comprehensive version headers.

## Files Updated

### 1. Bank Nifty Script
- **Old:** `trend_following_strategy_v6.pine`
- **New:** `BankNifty_TF_V7.0.pine`
- **Status:** ✅ Complete

### 2. Gold Mini Script
- **Old:** `gold_mini_strategy_v5.2_final_1.pine`
- **New:** `GoldMini_TF_V7.0.pine`
- **Status:** ✅ Complete

## Changes Applied

### Version Headers
- ✅ Updated to V7.0 with today's date (2025-11-27)
- ✅ Added comprehensive changelog documenting JSON alert additions
- ✅ Maintained all inherited features from previous versions

### JSON Alert Format

#### BASE_ENTRY Alerts
**Required Fields:**
- `type`: "BASE_ENTRY"
- `instrument`: "BANK_NIFTY" or "GOLD_MINI"
- `position`: "Long_1"
- `price`: Current close price
- `stop`: Stop loss price (SuperTrend)
- `lots`: Calculated lot size
- `atr`: Current ATR value
- `er`: Efficiency Ratio
- `supertrend`: Current SuperTrend value
- `roc`: Rate of Change
- `timestamp`: ISO 8601 format (YYYY-MM-DDTHH:MM:00Z)

**Status:** ✅ Complete in both scripts

#### PYRAMID Alerts
**Required Fields:**
- `type`: "PYRAMID"
- `instrument`: "BANK_NIFTY" or "GOLD_MINI"
- `position`: "Long_2", "Long_3", etc. (calculated correctly)
- `price`: Current close price
- `stop`: Current stop price (SuperTrend or Tom Basso stop)
- `lots`: Calculated pyramid lot size
- `atr`: Current ATR value
- `er`: Efficiency Ratio
- `supertrend`: Current SuperTrend value
- `roc`: Rate of Change
- `timestamp`: ISO 8601 format

**Status:** ✅ Complete in both scripts
**Note:** Bank Nifty uses `pyramid_count + 2` (alert runs before increment), Gold Mini uses `pyramid_count + 1` (alert runs after increment)

#### EXIT Alerts
**Required Fields:**
- `type`: "EXIT"
- `instrument`: "BANK_NIFTY" or "GOLD_MINI"
- `position`: "Long_1" through "Long_6" or "ALL" (for SuperTrend exit)
- `price`: Current close price
- `stop`: Stop price that was hit
- `entry_price`: Original entry price
- `lots`: Position size in lots
- `reason`: "TOM_BASSO_STOP" or "SuperTrend"
- `atr`: Current ATR value (atr_basso for Tom Basso, atr_pyramid for SuperTrend)
- `er`: Efficiency Ratio
- `supertrend`: Current SuperTrend value
- `roc`: Rate of Change
- `timestamp`: ISO 8601 format

**Status:** ✅ Complete in both scripts
- SuperTrend exits: ✅ Added
- Tom Basso exits (Long_1 through Long_6): ✅ Added
- Van Tharp exits: ⚠️ Not added (not default mode, can be added if needed)

## JSON Format Examples

### Bank Nifty BASE_ENTRY
```json
{
  "type": "BASE_ENTRY",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 52000.0,
  "stop": 51500.0,
  "lots": 5,
  "atr": 500.0,
  "er": 0.75,
  "supertrend": 51500.0,
  "roc": 2.5,
  "timestamp": "2025-11-27T10:30:00Z"
}
```

### Gold Mini PYRAMID
```json
{
  "type": "PYRAMID",
  "instrument": "GOLD_MINI",
  "position": "Long_2",
  "price": 72500.0,
  "stop": 72000.0,
  "lots": 2,
  "atr": 450.0,
  "er": 0.8,
  "supertrend": 72000.0,
  "roc": 1.2,
  "timestamp": "2025-11-27T14:15:00Z"
}
```

### Bank Nifty EXIT (Tom Basso)
```json
{
  "type": "EXIT",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 51800.0,
  "stop": 51800.0,
  "entry_price": 52000.0,
  "lots": 5,
  "reason": "TOM_BASSO_STOP",
  "atr": 500.0,
  "er": 0.75,
  "supertrend": 51500.0,
  "roc": 2.5,
  "timestamp": "2025-11-27T15:00:00Z"
}
```

## Validation Checklist

- [x] All JSON alerts include `instrument` field
- [x] All JSON alerts include `atr`, `er`, `supertrend`, `roc` fields
- [x] BASE_ENTRY alerts include `stop` field
- [x] PYRAMID alerts include `stop` field
- [x] EXIT alerts include `stop`, `entry_price`, `reason` fields
- [x] All EXIT alerts include `position` field
- [x] Timestamp format is ISO 8601 (YYYY-MM-DDTHH:MM:00Z)
- [x] Numeric fields are not quoted in JSON
- [x] String fields are quoted in JSON
- [x] Version headers updated with V7.0 and today's date
- [x] Files renamed correctly

## Technical Notes

### Position Numbering
- **Bank Nifty:** Alert section runs BEFORE entry section, so uses `pyramid_count + 2` to account for increment that happens in entry section
- **Gold Mini:** Alert section runs AFTER entry section (after increment), so uses `pyramid_count + 1`

### ATR Usage
- **BASE_ENTRY/PYRAMID:** Uses `atr_pyramid` (ATR for pyramiding calculations)
- **EXIT (Tom Basso):** Uses `atr_basso` (ATR for Tom Basso stop calculations)
- **EXIT (SuperTrend):** Uses `atr_pyramid`

### Stop Price Logic
- **BASE_ENTRY:** Uses `supertrend` as stop
- **PYRAMID:** Uses current stop (SuperTrend or Tom Basso stop for Long_1)
- **EXIT:** Uses the actual stop price that was hit

## Compatibility

✅ **JSON format matches** `portfolio_manager/core/models.py` Signal dataclass  
✅ **Ready for webhook processing** - All required fields present  
✅ **Tom Basso position sizing** - All required fields for calculations  

## Next Steps

1. **Test in TradingView:**
   - Load scripts in TradingView
   - Verify JSON alerts are generated correctly
   - Test with sample signals

2. **Webhook Integration:**
   - Configure TradingView alerts to send to portfolio manager webhook
   - Test signal parsing in `portfolio_manager.py`
   - Verify Signal objects are created correctly

3. **End-to-End Testing:**
   - Send test alert from TradingView
   - Verify webhook receives JSON
   - Verify portfolio manager processes signal correctly

## Files Summary

| File | Status | Lines | Alerts Added |
|------|--------|-------|--------------|
| `BankNifty_TF_V7.0.pine` | ✅ Complete | 1,237 | 9 alerts (1 BASE, 1 PYRAMID, 7 EXIT) |
| `GoldMini_TF_V7.0.pine` | ✅ Complete | 1,070 | 8 alerts (1 BASE, 1 PYRAMID, 6 EXIT) |

## Notes

- Van Tharp exit mode alerts were not added (not the default mode)
- All alerts use `alert.freq_once_per_bar_close` to prevent duplicates
- JSON syntax validated (no syntax errors)
- All numeric values properly formatted (no quotes)
- All string values properly quoted

---

**Implementation Complete:** ✅  
**Ready for Testing:** ✅  
**Date:** 2025-11-27

