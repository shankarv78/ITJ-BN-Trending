# Smart Order Placement Implementation

**Date:** November 27, 2025  
**Purpose:** Replace MARKET orders with intelligent LIMIT orders + retry logic

---

## Problem Statement

Original implementation used MARKET orders for synthetic futures (PE Sell + CE Buy), which:
- ❌ No price control → poor fills in volatile markets
- ❌ High slippage on illiquid strikes
- ❌ No retry mechanism → single attempt only

---

## Solution: Smart Order Placement Strategy

### Strategy Flow

```
1. Get LTP → Calculate LIMIT price (LTP ± 1%)
   ├─ BUY: LTP × 1.01 (1% above)
   └─ SELL: LTP × 0.99 (1% below)

2. Place LIMIT order → Monitor every 3 seconds

3. If NOT filled → Adjust price to mid-price
   └─ Mid = (Bid + Ask) / 2

4. Repeat for 5 attempts (15 seconds total)

5. If still NOT filled → Cancel + MARKET order
```

### Key Features

✅ **Better Fill Prices**: Start with LIMIT 1% away from LTP  
✅ **Adaptive Pricing**: Adjust to market mid-price if not filled  
✅ **Guaranteed Fills**: Fallback to MARKET after 15 seconds  
✅ **Detailed Logging**: Track all attempts and price adjustments

---

## Implementation

### New Module: `smart_order_placer.py`

**Class:** `SmartOrderPlacer`

**Method:** `place_with_retry(symbol, action, quantity, product)`

**Returns:**
```python
{
    'status': 'success' | 'failed' | 'market_pending',
    'order_id': 'primary_order_id',
    'fill_price': 123.45,
    'filled_at_attempt': 3,
    'filled_via': 'LIMIT' | 'MARKET',
    'initial_ltp': 122.00,
    'initial_limit_price': 123.22,
    'attempts': [
        {'attempt': 1, 'type': 'LIMIT', 'price': 123.22},
        {'attempt': 2, 'type': 'LIMIT_MODIFIED', 'price': 123.50, 'bid': 123.00, 'ask': 124.00},
        ...
    ]
}
```

### Updated Modules

**1. `openalgo_client.py`**
- ✅ Added `price` parameter to `place_order()` for LIMIT orders
- ✅ Added `modify_order(order_id, new_price)` method
- ✅ Existing `get_quote()` method (already had LTP, bid, ask)

**2. `synthetic_executor.py`**
- ✅ Integrated `SmartOrderPlacer` for both PE and CE legs
- ✅ Emergency MARKET cover if CE fails after retries
- ✅ Detailed attempt logging

**3. `openalgo_config.json`**
- ✅ Added `order_retry_attempts`: 5 (default)
- ✅ Added `order_retry_interval`: 3.0 seconds (default)

---

## Configuration

```json
{
  "order_retry_attempts": 5,
  "order_retry_interval": 3.0
}
```

**Tuning Recommendations:**
- **Liquid strikes (ATM):** 5 attempts × 3s = 15s total (current default)
- **OTM strikes (less liquid):** 7 attempts × 4s = 28s total
- **Market volatility high:** 3 attempts × 2s = 6s + quick MARKET
- **Paper trading/testing:** 2 attempts × 1s = 2s

---

## Execution Timeline Example

### Successful LIMIT Fill (Attempt 2)

```
T+0s   : Get quote → LTP=120.00 → LIMIT=118.80 (SELL at -1%)
T+0.1s : Place LIMIT order → Order ID: 12345
T+3s   : Check status → PENDING
         Get fresh quote → Bid=118.50, Ask=119.50 → Mid=119.00
         Modify order to 119.00
T+6s   : Check status → FILLED at ₹119.00
         ✓ Done in 2 attempts (6 seconds)
```

### Fallback to MARKET (After 5 Attempts)

```
T+0s   : Place LIMIT @ 118.80
T+3s   : PENDING → Modify to 119.00
T+6s   : PENDING → Modify to 119.20
T+9s   : PENDING → Modify to 119.50
T+12s  : PENDING → Modify to 119.80
T+15s  : PENDING → Cancel LIMIT order
T+15.5s: Place MARKET order
T+16s  : FILLED at ₹120.50 (slippage)
         ✓ Done via MARKET (16 seconds)
```

---

## Benefits

### 1. **Better Fill Prices**
- LIMIT orders typically fill at better prices than MARKET
- 1% buffer usually sufficient for ATM options
- Mid-price adjustments track market movement

### 2. **Reduced Slippage**
- Estimated savings: **₹2-5 per lot** on Bank Nifty options
- Example: 10 lots × ₹3 savings × 100 trades = **₹3,000/year**

### 3. **Guaranteed Execution**
- MARKET fallback ensures position gets filled
- No missed signals due to order rejections
- Critical for synthetic futures (need both legs)

### 4. **Operational Intelligence**
- Detailed attempt logs for post-trade analysis
- Understand fill difficulty by strike/time
- Optimize retry parameters based on data

---

## Testing Checklist

- [ ] **Unit Test:** Mock OpenAlgo client responses
- [ ] **Integration Test:** Test with live quotes (paper trading)
- [ ] **Stress Test:** Test during high volatility (15:15-15:25)
- [ ] **Edge Cases:**
  - [ ] Order rejected after modification
  - [ ] Bid/ask spread = 0 (quote fetch fails)
  - [ ] MARKET order also fails (critical path)
- [ ] **Performance:** Measure fill price improvement vs old MARKET

---

## Monitoring & Alerts

**Watch For:**
```
✓ LIMIT fills within 1-2 attempts → Good liquidity
⚠️ Frequent MARKET fallbacks → Consider wider LIMIT buffer
❌ MARKET orders failing → Exchange/broker issues
```

**Log Patterns:**
```
INFO: ✓ Order FILLED at ₹119.00 (attempt 2)  ← Good
WARNING: ⚠️ LIMIT order did not fill after 5 attempts  ← Review strike liquidity
CRITICAL: ❌ MARKET order FAILED  ← Immediate action required
```

---

## Files Modified

| File | Changes |
|------|---------|
| `openalgo_client.py` | Added `price` param, `modify_order()` method |
| `smart_order_placer.py` | **NEW** - Core retry logic |
| `synthetic_executor.py` | Integrated smart placer for PE/CE |
| `openalgo_config.json` | Added retry config parameters |
| `openalgo_bridge.py` | Updated partial fill handling (previous fix) |

---

## Rollout Plan

1. ✅ Code implementation complete
2. ⏳ Unit tests for `SmartOrderPlacer`
3. ⏳ Paper trading validation (1 week)
4. ⏳ Review fill price improvement
5. ⏳ Enable for live trading

---

**Status:** IMPLEMENTED ✅  
**Next:** Testing with paper trading account

