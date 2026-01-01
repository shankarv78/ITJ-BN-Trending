## Overview

This PR implements the **Dumb Scout / Smart General** architecture for TradingView integration, separating signal generation from execution authority.

---

## Problem Statement

### Previous Architecture (V8)
- Single Pine Script strategy handled BOTH:
  - EOD_MONITOR alerts (continuous signals during EOD window)
  - Trade execution alerts (BASE_ENTRY/PYRAMID/EXIT)
- EOD_MONITOR fired on every tick → TradingView rate limiting issues
- TradingView maintained position state → could become stale/incorrect
- PM trusted TradingView's position_status blindly

### Issues Identified (Gap Analysis)
| Gap | Problem | Impact |
|-----|---------|--------|
| Gap 1 | TradingView position state can be stale | Wrong pyramid count, missed entries |
| Gap 3 | Conditions checked at T-45 may change by T-30 | Execute on outdated state |
| Gap 4 | No blocking during EOD execution | Duplicate signals |

---

## New Architecture: Dumb Scout / Smart General

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRADINGVIEW (The Scout)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────┐         ┌─────────────────────┐               │
│  │   EOD Scout         │         │   Strategy V9       │               │
│  │   (Indicator)       │         │   (Executor)        │               │
│  ├─────────────────────┤         ├─────────────────────┤               │
│  │ • Sends conditions  │         │ • Fires only on     │               │
│  │   every 15 seconds  │         │   trade execution   │               │
│  │ • No position state │         │ • BASE_ENTRY        │               │
│  │ • Throttled alerts  │         │ • PYRAMID           │               │
│  │ • EOD window only   │         │ • EXIT              │               │
│  └─────────────────────┘         └─────────────────────┘               │
│           │                                │                            │
│           │ EOD_MONITOR                    │ Order Alerts               │
│           ▼                                ▼                            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   PYTHON PORTFOLIO MANAGER (The General)                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────┐    ┌─────────────────────┐                    │
│  │   Database          │◄───│   EOD Monitor       │                    │
│  │   (PostgreSQL)      │    │   + Executor        │                    │
│  ├─────────────────────┤    ├─────────────────────┤                    │
│  │ • Position TRUTH    │    │ • Receives signals  │                    │
│  │ • Pyramid count     │    │ • Overrides with DB │                    │
│  │ • Entry prices      │    │ • Makes decisions   │                    │
│  │ • P&L tracking      │    │ • Places orders     │                    │
│  └─────────────────────┘    └─────────────────────┘                    │
│                                                                         │
│  KEY PRINCIPLE: PM is the AUTHORITY on position state                  │
│  TradingView is BLIND - it only sends raw indicator data               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Files Added

### 1. TradingView V9.0 Strategies (3 files)
| File | Instrument | Lines |
|------|------------|-------|
| `BankNifty_TF_V9.0.pine` | Bank Nifty | 1355 |
| `GoldMini_TF_V9.0.pine` | Gold Mini | 1124 |
| `SilverMini_TF_V9.0.pine` | Silver Mini | 1121 |

**V9 Changes from V8:**
- ❌ Removed EOD_MONITOR logic entirely
- ✅ Only fires ORDER FILL alerts (BASE_ENTRY/PYRAMID/EXIT)
- ✅ `barstate.isconfirmed` on entries (prevents duplicates)
- ✅ Geometric LOT_B scaling: `0.5^(pyramid_count+1)`

### 2. EOD Scout Indicators (3 files)
| File | Instrument | EOD Window | Lines |
|------|------------|------------|-------|
| `BankNifty_EOD_Scout_V1.0.pine` | Bank Nifty | 15:15-15:30 IST | 216 |
| `GoldMini_EOD_Scout_V1.0.pine` | Gold Mini | 23:15-23:30 IST | 240 |
| `SilverMini_EOD_Scout_V1.0.pine` | Silver Mini | 23:15-23:30 IST | 212 |

**Scout Features:**
- Uses `indicator()` not `strategy()`
- `varip` throttling - fires every 15 seconds (prevents rate limiting)
- NO position_status field - PM is authority
- Sends raw conditions + indicators only

### 3. Testing Tools (3 files)
| File | Purpose | Lines |
|------|---------|-------|
| `signal_listener.py` | Webhook test server with color logging | 448 |
| `Bitcoin_EOD_Signal_Tester.pine` | Bitcoin indicator for 24/7 testing | 360 |
| `BITCOIN_EOD_TEST_GUIDE.md` | Setup documentation | 243 |

---

## Files Modified

### `portfolio_manager/live/engine.py` (+72 lines)

#### Gap 1 Fix: Database State Authority

**In `eod_condition_check()` (T-45):**
```python
# GAP 1 FIX: Override signal position_status with DATABASE truth
portfolio_state = self.portfolio.get_current_state()
db_positions = portfolio_state.get_positions_for_instrument(instrument)
db_in_position = len(db_positions) > 0
db_pyramid_count = len(db_positions) - 1 if db_in_position else 0

# Override signal's position_status with database truth
state.latest_signal.position_status.in_position = db_in_position
state.latest_signal.position_status.pyramid_count = db_pyramid_count
```

**In `eod_execute()` (T-30):**
- Re-validates with FRESH database state
- Catches any changes since T-45 check
- Logs current DB state for debugging

---

## EOD_MONITOR JSON Format (Scout → PM)

```json
{
  "type": "EOD_MONITOR",
  "instrument": "GOLD_MINI",
  "timestamp": "2025-12-28T23:45:00",
  "price": 63500.00,
  "conditions": {
    "rsi_condition": true,
    "ema_condition": true,
    "dc_condition": false,
    "adx_condition": true,
    "er_condition": true,
    "st_condition": true,
    "not_doji": true,
    "long_entry": false,
    "long_exit": false
  },
  "indicators": {
    "rsi": 72.5,
    "ema": 62800.0,
    "dc_upper": 63400.0,
    "adx": 18.5,
    "er": 0.85,
    "supertrend": 62500.0,
    "atr": 450.0
  }
}
```

**Note:** NO `position_status` field - PM queries its own database.

---

## Gap Status

| Gap | Description | Status |
|-----|-------------|--------|
| Gap 1 | Database State Authority | ✅ Fixed in this PR |
| Gap 3 | Fresh Signal Updates (T-45→T-30) | ✅ Already in main |
| Gap 4 | Race Condition Block | ✅ Already in main |

---

## Deployment Steps

1. **TradingView Setup:**
   - Add EOD Scout indicator to chart
   - Add V9 Strategy to chart
   - Create alert for Scout (EOD_MONITOR webhook)
   - Create alert for Strategy (Order webhooks)

2. **PM Configuration:**
   - Enable EOD monitoring
   - Configure EOD windows per instrument
   - Restart PM to pick up code changes

---

## Summary

| Category | Count |
|----------|-------|
| New Pine Scripts | 9 files (+5,319 lines) |
| Modified Python | 1 file (+72 lines) |
| Total Changes | 10 files (+5,391 lines) |


