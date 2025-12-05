# Critical Fix: Partial Fill Position Tracking

**Issue Identified:** Codex bot review on GitHub  
**Severity:** CRITICAL - Unmanaged risk exposure  
**Date Fixed:** November 27, 2025

## Problem Statement

In `openalgo_bridge.py`, positions were only persisted to state when `execution_result['status'] == 'success'`. When partial-fill protection is enabled for synthetic futures execution:

1. PE (Sell) order fills immediately → `pe_status = 'complete'`
2. CE (Buy) order placed but pending → `ce_status = 'pending'`
3. `execute_synthetic_long()` returns `status = 'ce_pending'` (not 'success')
4. **Position state NOT saved** due to if-condition check
5. **Result:** Open PE position with NO tracking = **unmanaged risk exposure**

## Risk Impact

- **Unhedged short PE position** - unlimited downside risk
- **No stop loss management** - position cannot be exited on stop hit
- **No P&L tracking** - unrealized losses not monitored
- **Reconciliation failure** - broker shows position, bridge state empty

## Solution Implemented

### 1. Extended State Persistence Condition

**Before:**
```python
if execution_result['status'] == 'success':
    state.add_position(position_id, position_data)
```

**After:**
```python
if execution_result['status'] in ['success', 'ce_pending', 'ce_status_unknown']:
    position_data = {
        'status': 'open' if execution_result['status'] == 'success' else 'partial',
        # ... rest of data
    }
    state.add_position(position_id, position_data)
```

### 2. New Position Status: 'partial'

Introduced to distinguish:
- `'open'` - Both legs filled successfully
- `'partial'` - PE filled, CE pending (tracked for safety)
- `'closed'` - Position exited

### 3. Updated All Position Checks

**handle_base_entry:**
- Duplicate check: `status in ['open', 'partial']`

**handle_pyramid:**
- Base position check: `status in ['open', 'partial']`
- Existing pyramid check: `status in ['open', 'partial']`

**handle_exit:**
- Exit eligibility: `status in ['open', 'partial']`

### 4. Enhanced Logging

```python
if execution_result['status'] == 'success':
    logger.info(f"✓ Position {position_id} opened: {lots} lots at strike {strike}")
else:
    logger.warning(f"⚠️  Position {position_id} PARTIAL: PE filled, CE {status} - position tracked for safety")
```

## Files Modified

1. `openalgo_bridge.py` - `handle_base_entry()` (lines 64-85)
2. `openalgo_bridge.py` - `handle_pyramid()` (lines 114-138)
3. `openalgo_bridge.py` - `handle_exit()` (line 152)

## Testing Recommendations

1. **Unit Test:** Simulate `ce_pending` status in synthetic_executor mock
2. **Integration Test:** 
   - Enable partial-fill protection
   - Place entry when CE liquidity is low
   - Verify position persisted with `status='partial'`
   - Verify exit works for partial positions
3. **Reconciliation Test:**
   - Check `/reconcile` endpoint includes partial positions
   - Verify partial positions appear in `/positions` endpoint

## Rollout Plan

1. ✅ Code fix applied to all handler functions
2. ⏳ Add tests for partial fill scenarios
3. ⏳ Test in staging with low liquidity strikes
4. ⏳ Monitor production logs for "PARTIAL" warnings
5. ⏳ Add alert when partial positions persist > 30 seconds

## Monitoring

Watch for these log patterns:
```
⚠️  Position Long_1 PARTIAL: PE filled, CE ce_pending - position tracked for safety
```

**Action Required:** If partial positions don't resolve to 'open' within 30-60 seconds, investigate:
- CE order status manually in broker terminal
- Cancel CE order if needed
- Hedge PE position manually

## Credit

**Issue identified by:** chatgpt-codex-connector (GitHub bot)  
**Review comment:** "Persist entries even when CE fill is pending"

---

**Status:** FIXED ✅  
**Verification:** Pending integration tests
