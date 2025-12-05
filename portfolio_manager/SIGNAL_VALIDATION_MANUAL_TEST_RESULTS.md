# Signal Validation Manual Testing Guide

**Date:** 2025-12-02  
**Status:** Ready for Testing  
**Environment:** Paper Trading Account

---

## Overview

This document provides a comprehensive guide for manually testing the Signal Validation and Execution System with a paper trading account. The tests verify end-to-end functionality including validation, execution strategies, and error handling.

---

## Prerequisites

1. **Paper Trading Account Setup:**
   - OpenAlgo paper trading account configured
   - Sufficient paper trading capital (recommended: ₹10L+)
   - TradingView alerts configured and tested
   - Webhook endpoint accessible from TradingView

2. **System Configuration:**
   - Signal validation enabled: `config.signal_validation_enabled = True`
   - Execution strategy: `config.execution_strategy = "progressive"` (or "simple_limit")
   - Validation thresholds configured appropriately

3. **Monitoring:**
   - Access to application logs
   - Database access for position verification
   - TradingView alert logs

---

## Test Scenarios

### Test 1: Normal Flow - BASE_ENTRY with No Divergence

**Objective:** Verify normal signal processing when broker price matches signal price

**Steps:**
1. Send BASE_ENTRY signal from TradingView at current market price
2. Monitor webhook logs for validation stages
3. Verify order execution
4. Check database for position creation

**Expected Results:**
- ✅ Condition validation: PASSED (signal fresh)
- ✅ Execution validation: PASSED (no divergence)
- ✅ Order executed: SUCCESS
- ✅ Position created in database with correct entry price
- ✅ Logs show: "Entry executed: X lots @ ₹Y"

**Validation Points:**
- [ ] Signal age < 10 seconds
- [ ] Broker price divergence < 0.5%
- [ ] Order filled at or near signal price
- [ ] Position entry_price = execution price (not signal price)

---

### Test 2: Price Divergence - BASE_ENTRY with Acceptable Divergence

**Objective:** Verify signal processing when broker price diverges but within threshold

**Steps:**
1. Send BASE_ENTRY signal at price P
2. Wait 30 seconds (market may move)
3. Verify broker price is different but within 2% threshold
4. Monitor validation and execution

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED with WARNING (divergence > 0.5%)
- ✅ Position size may be adjusted if risk increased
- ✅ Order executed successfully
- ✅ Logs show: "execution_validated_with_warning"

**Validation Points:**
- [ ] Divergence logged: "Broker price: ₹X (signal: ₹Y)"
- [ ] Warning logged if divergence > 0.5%
- [ ] Position size adjusted if risk increase > 50%
- [ ] Execution price used for position entry

---

### Test 3: Excessive Divergence - BASE_ENTRY Rejection

**Objective:** Verify signal rejection when divergence exceeds threshold

**Steps:**
1. Send BASE_ENTRY signal at price P
2. Wait 60 seconds (market moves significantly)
3. Verify broker price diverges > 2% from signal
4. Monitor validation rejection

**Expected Results:**
- ✅ Condition validation: PASSED (if signal age < 60s)
- ❌ Execution validation: REJECTED
- ❌ Order NOT executed
- ❌ No position created
- ✅ Logs show: "Signal rejected at execution validation: Price divergence too high"

**Validation Points:**
- [ ] Rejection reason includes divergence percentage
- [ ] No order placed with broker
- [ ] No position in database
- [ ] Stats updated: `entries_blocked` or `orders_failed`

---

### Test 4: Market Surge - Position Size Adjustment

**Objective:** Verify position size adjustment when market surges after signal

**Steps:**
1. Send BASE_ENTRY signal at ₹50,000
2. Market surges to ₹50,500 (1% divergence, increases risk)
3. Monitor validation and size adjustment

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED with WARNING
- ✅ Position size adjusted: 12 lots → 10 lots (risk increase ~50%)
- ✅ Order executed with adjusted size
- ✅ Logs show: "Position size adjusted: 12 → 10 lots (risk increase: 50.00%)"

**Validation Points:**
- [ ] Original lots calculated correctly
- [ ] Adjusted lots calculated: `original_lots * (original_risk / execution_risk)`
- [ ] Order placed with adjusted lots
- [ ] Position created with adjusted lots

---

### Test 5: Market Pullback - Favorable Execution

**Objective:** Verify execution proceeds when market pulls back (favorable)

**Steps:**
1. Send BASE_ENTRY signal at ₹51,000
2. Market pulls back to ₹50,800 (favorable divergence)
3. Monitor validation and execution

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED (favorable movement)
- ✅ Order executed at better price
- ✅ Position created with execution price
- ✅ Logs show: "favorable_divergence" or similar

**Validation Points:**
- [ ] Execution proceeds despite divergence
- [ ] Entry price = broker price (better than signal)
- [ ] No position size adjustment (risk decreased)

---

### Test 6: Execution Timeout - SimpleLimitExecutor

**Objective:** Verify timeout handling when order doesn't fill

**Steps:**
1. Configure execution strategy: `simple_limit`
2. Send BASE_ENTRY signal
3. Market moves away from limit price
4. Wait 30+ seconds for timeout

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED
- ❌ Order execution: TIMEOUT
- ❌ Order cancelled after 30 seconds
- ❌ No position created
- ✅ Logs show: "Order timeout after 30s, cancelling"

**Validation Points:**
- [ ] Order placed with broker
- [ ] Status polled every 2 seconds
- [ ] Order cancelled after timeout
- [ ] No position created
- [ ] Stats updated: `orders_failed`

---

### Test 7: Progressive Fill Success - ProgressiveExecutor

**Objective:** Verify progressive price improvement strategy

**Steps:**
1. Configure execution strategy: `progressive`
2. Send PYRAMID signal
3. Market price slightly above signal price
4. Monitor multiple execution attempts

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED
- ✅ Order execution: FILLED on attempt 2 or 3
- ✅ Position created
- ✅ Logs show: "Order filled on attempt X: Y lots @ ₹Z (slippage: W%)"

**Validation Points:**
- [ ] Multiple order attempts logged
- [ ] Price improved progressively: +0%, +0.5%, +1.0%, +1.5%
- [ ] Fill price within hard slippage limit (2%)
- [ ] Slippage calculated correctly

---

### Test 8: PYRAMID Signal - 1R Movement Validation

**Objective:** Verify PYRAMID requires 1.5R movement from base entry

**Steps:**
1. Create base position at ₹50,000
2. Send PYRAMID signal at ₹50,100 (only 0.5R move, insufficient)
3. Monitor validation rejection

**Expected Results:**
- ❌ Condition validation: REJECTED
- ❌ Reason: "Pyramid conditions not met: price move (100.00) < 1.5R ATR threshold (150.00)"
- ❌ No order placed
- ❌ No pyramid position created

**Validation Points:**
- [ ] Base position found correctly
- [ ] Price move calculated: `signal.price - base_position.entry_price`
- [ ] ATR threshold: `signal.atr * 1.5`
- [ ] Rejection reason clear and specific

---

### Test 9: PYRAMID Signal - Excessive Divergence

**Objective:** Verify PYRAMID has stricter divergence threshold (1% vs 2%)

**Steps:**
1. Create base position
2. Send PYRAMID signal at ₹50,000
3. Market moves to ₹50,600 (1.2% divergence, exceeds 1% threshold)
4. Monitor validation rejection

**Expected Results:**
- ✅ Condition validation: PASSED (1R movement OK)
- ❌ Execution validation: REJECTED
- ❌ Reason: "Price divergence too high: 1.20% (threshold: 1.00%)"
- ❌ No order placed

**Validation Points:**
- [ ] PYRAMID threshold stricter than BASE_ENTRY
- [ ] Rejection at 1.2% divergence (would pass for BASE_ENTRY)
- [ ] Clear rejection reason

---

### Test 10: Stale Signal Rejection

**Objective:** Verify signals older than 60 seconds are rejected

**Steps:**
1. Send signal from TradingView
2. Manually delay processing (or wait 70+ seconds)
3. Monitor validation rejection

**Expected Results:**
- ❌ Condition validation: REJECTED
- ❌ Reason: "signal_stale_70s"
- ❌ No order placed
- ✅ Logs show: "Signal rejected at condition validation: signal_stale_70s"

**Validation Points:**
- [ ] Signal age calculated correctly
- [ ] Rejection at > 60 seconds
- [ ] Age logged in rejection reason

---

### Test 11: Partial Fill Handling

**Objective:** Verify partial fill handling (if broker supports)

**Steps:**
1. Place order for 10 lots
2. Broker fills 6 lots, 4 remain
3. Monitor partial fill handling

**Expected Results:**
- ✅ Order execution: PARTIAL
- ✅ Remaining 4 lots cancelled
- ✅ Position created with 6 lots (filled amount)
- ✅ Logs show: "Partial fill: 6/10 lots filled, remaining 4 cancelled"

**Validation Points:**
- [ ] Partial fill detected correctly
- [ ] Remaining lots cancelled
- [ ] Position created with filled lots only
- [ ] Execution result includes `partial_fill: True`

---

### Test 12: EXIT Signal Validation

**Objective:** Verify EXIT signal validation with inverted logic

**Steps:**
1. Create open position
2. Send EXIT signal at ₹50,200
3. Broker price at ₹50,100 (worse exit, -0.2% unfavorable)
4. Monitor validation

**Expected Results:**
- ✅ Condition validation: PASSED
- ✅ Execution validation: PASSED (within 1% unfavorable threshold)
- ✅ Order executed
- ✅ Position closed

**Validation Points:**
- [ ] EXIT validation uses inverted logic
- [ ] Unfavorable exit (< 1%) still accepted
- [ ] Very unfavorable exit (> 1%) rejected
- [ ] Position closed correctly

---

## Test Execution Checklist

### Pre-Test Setup
- [ ] Paper trading account configured
- [ ] Signal validation enabled in config
- [ ] Execution strategy selected (simple_limit or progressive)
- [ ] Logging level set to INFO or DEBUG
- [ ] Database accessible for position verification

### During Testing
- [ ] Monitor webhook logs in real-time
- [ ] Verify each validation stage
- [ ] Check order placement with broker
- [ ] Verify position creation in database
- [ ] Document any unexpected behavior

### Post-Test Verification
- [ ] All positions match expected state
- [ ] Execution prices recorded correctly
- [ ] Slippage calculated accurately
- [ ] Stats counters updated correctly
- [ ] No errors in logs

---

## Expected Log Patterns

### Successful Execution
```
[LIVE] Processing: BASE_ENTRY Long_1 @ ₹50000.00
[LIVE] Broker price: ₹50,005.00 (signal: ₹50,000.00)
[LIVE] Signal condition validation passed with normal severity (age: 5.2s)
[ProgressiveExecutor] Executing BASE_ENTRY order: 12 lots @ ₹50,005.00 (signal: ₹50,000.00)
[ProgressiveExecutor] Attempt 1/4: Price ₹50,005.00 (+0.00% vs limit, +0.01% vs signal)
[ProgressiveExecutor] Order filled on attempt 1: 12 lots @ ₹50,005.00 (slippage: 0.01%)
✓ [LIVE] Entry executed: 12 lots @ ₹50,005.00 (signal: ₹50,000.00, slippage: 0.01%)
```

### Rejection Due to Divergence
```
[LIVE] Processing: BASE_ENTRY Long_1 @ ₹50000.00
[LIVE] Broker price: ₹51,200.00 (signal: ₹50,000.00)
[LIVE] Signal condition validation passed with normal severity (age: 6.1s)
[LIVE] Signal rejected at execution validation: Price divergence too high: 2.40% (broker: 51200.00, signal: 50000.00) (divergence: 2.40%)
```

### Position Size Adjustment
```
[LIVE] Broker price: ₹50,500.00 (signal: ₹50,000.00)
[LIVE] Position size adjusted: 12 → 10 lots (risk increase: 50.00%)
[ProgressiveExecutor] Executing BASE_ENTRY order: 10 lots @ ₹50,500.00
```

---

## Troubleshooting

### Issue: Signals Always Rejected
**Possible Causes:**
- Signal validation too strict (check thresholds)
- Broker API returning stale prices
- Signal age exceeding threshold

**Solutions:**
- Review validation config thresholds
- Verify broker API connectivity
- Check TradingView alert timing

### Issue: Orders Not Filling
**Possible Causes:**
- Limit price too far from market
- Execution strategy timeout too short
- Broker API issues

**Solutions:**
- Use ProgressiveExecutor for better fill rate
- Increase timeout if needed
- Verify broker API status

### Issue: Position Size Always Adjusted
**Possible Causes:**
- Market moving significantly after signal
- Risk increase threshold too low
- Execution price always different

**Solutions:**
- Review risk increase thresholds
- Check market volatility
- Consider signal timing improvements

---

## Success Criteria

All tests should demonstrate:
1. ✅ Condition validation working correctly
2. ✅ Execution validation protecting against excessive divergence
3. ✅ Position size adjustment when risk increases
4. ✅ Execution strategies functioning as designed
5. ✅ Proper error handling and logging
6. ✅ Database consistency maintained

---

## Notes

- **Paper Trading:** All tests use paper trading account - no real money at risk
- **Timing:** Some tests require waiting for market movement - be patient
- **Logs:** Keep detailed logs for each test scenario
- **Database:** Verify positions after each test
- **Broker API:** Ensure broker API is responsive during testing

---

**End of Manual Testing Guide**

