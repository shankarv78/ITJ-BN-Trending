# Signal Validation and Execution Specification

**Version:** 1.1
**Date:** December 1, 2025
**Purpose:** Define signal validation logic, execution strategies, and risk management for live trading
**Status:** Design Specification (Not Yet Implemented)

**Related Documents:**
- `TASK28_REVIEW_FEEDBACK.md` - Review feedback and recommendations
- TaskMaster Task #28 - Implementation tracking

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Core Scenarios](#core-scenarios)
4. [Signal Validation Logic](#signal-validation-logic)
5. [EXIT Signal Validation](#exit-signal-validation) *(New in v1.1)*
6. [Signal Age Validation](#signal-age-validation) *(New in v1.1)*
7. [Execution Strategies](#execution-strategies)
8. [Risk Management](#risk-management)
9. [Configuration](#configuration)
10. [Mock Broker Simulator](#mock-broker-simulator) *(New in v1.1)*
11. [Test Scenarios](#test-scenarios)
12. [Implementation Plan](#implementation-plan)

---

## Overview

### Purpose

This document specifies how the Portfolio Manager validates TradingView signals and executes orders in live trading, balancing three critical objectives:

1. **Don't Miss Valid Opportunities** - Trust TradingView signal timing
2. **Protect Against Excessive Risk** - Validate execution prices and risk
3. **Ensure Realistic Fills** - Use broker API for actual execution prices

### Key Principle

> **Trust TradingView for CONDITION VALIDATION, Use Broker API for EXECUTION VALIDATION**

This hybrid approach ensures we capture valid trading opportunities while maintaining financial safety.

---

## Problem Statement

### The Challenge

When a TradingView signal arrives at the webhook:

```
Time T0: TradingView generates signal at price P0
Time T1: Signal arrives at webhook (network delay: 1-30 seconds)
Time T2: Query broker API, get price P1
```

**Question:** Should we execute the signal?

### Three Critical Scenarios

#### Scenario A: Market Pulled Back ⬇️

```
T0: Signal at 50,500 (valid - met all conditions)
T1: Broker API at 50,450 (pulled back 50 points)
```

**Challenge:**
- Conditions might no longer be met with broker price
- But signal WAS valid when generated
- **We don't want to miss valid entries**

**Decision:** ✅ Execute (better entry price!)

---

#### Scenario B: Market Surged Ahead ⬆️

```
T0: Signal at 50,500 (valid)
T1: Broker API at 50,800 (surged 300 points)
```

**Challenges:**
- Higher entry price = worse entry for long
- Risk increases (stop farther away)
- Could be "chasing" the market
- But trend is strong!

**Decision:** ⚠️ Execute if divergence < threshold AND risk increase < 20%

---

#### Scenario C: Aggressive Execution Slippage 📈

```
T0: Signal at 50,500
T1: Place limit order at 50,500 → No fill (5 seconds)
T2: Modify to 50,550 → No fill (5 seconds)
T3: Modify to 50,650 → No fill (5 seconds)
T4: Place market order → Filled at 50,800!
```

**Challenges:**
- Slippage: 300 points (0.6%)
- Entry price far from signal
- Risk calculation now wrong
- **When do we abort?**

**Decision:** ⚠️ Execute only if slippage < max threshold, otherwise abort

---

## Signal Validation Logic

### Two-Stage Validation

#### Stage 1: Condition Validation (Trust TradingView)

```python
def validate_conditions_with_signal_price(signal_data):
    """
    Validate trading conditions using SIGNAL price
    Trust TradingView's timing - it generated signal at the right moment
    """
    signal_price = signal_data['price']
    signal_type = signal_data['type']

    if signal_type == 'PYRAMID':
        # Check 1R movement with SIGNAL price
        base_position = get_base_position(signal_data['instrument'])
        price_move = signal_price - base_position.entry_price
        atr_threshold = signal_data['atr'] * 1.5

        if price_move < atr_threshold:
            return False, "conditions_not_met_at_signal"

        # Check instrument P&L with SIGNAL price
        # (will be updated when we query broker)

    return True, "conditions_met"
```

**Rationale:**
- TradingView evaluated conditions at T0
- Network delays (T0 → T1) shouldn't invalidate good signals
- Trust the strategy's timing

---

#### Stage 2: Execution Validation (Query Broker)

```python
def validate_execution_price(signal_data, broker_price):
    """
    Validate execution is safe using BROKER price
    Protect against excessive divergence and risk
    """
    signal_price = signal_data['price']
    signal_type = signal_data['type']
    stop_price = signal_data['stop']

    # Calculate divergence
    divergence = broker_price - signal_price
    divergence_pct = abs(divergence / signal_price)

    # Set thresholds based on signal type
    if signal_type == 'BASE_ENTRY':
        max_divergence = 0.02  # 2% for base entry
    else:  # PYRAMID
        max_divergence = 0.01  # 1% for pyramid (stricter!)

    if divergence_pct > max_divergence:
        return False, f"divergence_too_high_{divergence_pct:.2%}"

    # Calculate risk increase (CRITICAL for pyramids!)
    original_risk = signal_price - stop_price
    execution_risk = broker_price - stop_price
    risk_increase = (execution_risk - original_risk) / original_risk

    MAX_RISK_INCREASE = 0.20  # Max 20% risk increase

    if risk_increase > MAX_RISK_INCREASE:
        if signal_type == 'PYRAMID':
            return False, f"risk_increase_too_high_{risk_increase:.2%}"
        else:
            # For base entry, reduce position size
            return True, "accepted_with_size_adjustment"

    return True, "execution_validated"
```

**Rationale:**
- Broker price is what we'll actually get filled at
- Protect against excessive slippage
- Ensure risk doesn't increase beyond acceptable levels

---

### Decision Matrix

#### For BASE_ENTRY:

| Divergence | Risk Increase | Market Direction | Action |
|------------|---------------|------------------|--------|
| < 1% | < 10% | Any | ✅ Execute at broker price |
| 1-2% | 10-20% | Pulled back | ✅ Execute (better entry!) |
| 1-2% | 10-20% | Surged ahead | ✅ Execute, reduce lots by risk% |
| 1-2% | > 20% | Surged ahead | ⚠️ Reduce lots by 30-50% |
| > 2% | Any | Any | ❌ Reject (too much divergence) |

#### For PYRAMID:

| Divergence | Risk Increase | Market Direction | Action |
|------------|---------------|------------------|--------|
| < 0.5% | < 10% | Any | ✅ Execute at broker price |
| 0.5-1% | 10-20% | Pulled back | ✅ Execute (better entry!) |
| 0.5-1% | 10-20% | Surged ahead | ⚠️ Warning log, but execute |
| 0.5-1% | > 20% | Surged ahead | ❌ Reject (risk too high) |
| > 1% | Any | Surged ahead | ❌ Reject (don't chase pyramids) |
| > 1% | Any | Pulled back | ⚠️ Accept if risk decrease |

#### For EXIT:

| Divergence | Market Direction | Action |
|------------|------------------|--------|
| < 0.5% | Any | ✅ Execute at broker price |
| 0.5-1% | Favorable (higher) | ✅ Execute (better exit!) |
| 0.5-1% | Unfavorable (lower) | ⚠️ Warning but execute |
| > 1% | Favorable (higher) | ✅ Execute (much better exit!) |
| > 1% | Unfavorable (lower) | ❌ Reject (missed exit opportunity) |

---

## EXIT Signal Validation

### Overview

EXIT signals require different validation logic than entry signals:
- **No risk increase validation** - We're closing risk, not adding to it
- **Divergence direction matters differently** - Lower price = worse exit for LONG
- **Urgency is higher** - Delayed exits can miss trailing stop protection

### EXIT Validation Logic

```python
def validate_exit_execution(signal_data, broker_price):
    """
    Validate EXIT signal execution.

    For LONG positions:
    - broker_price > signal_price = favorable (better exit)
    - broker_price < signal_price = unfavorable (missed better exit)

    Args:
        signal_data: EXIT signal with price, instrument
        broker_price: Current broker quote

    Returns:
        (is_valid, reason)
    """
    signal_price = signal_data['price']

    # Calculate divergence (positive = favorable for LONG exit)
    divergence = broker_price - signal_price
    divergence_pct = divergence / signal_price

    # For LONG exits:
    # - Positive divergence = favorable (price went up, better exit)
    # - Negative divergence = unfavorable (price dropped, worse exit)

    if divergence_pct >= 0:
        # Favorable or neutral - always accept
        if divergence_pct > 0.005:  # > 0.5% better
            return True, "exit_favorable_divergence"
        return True, "exit_validated"

    # Unfavorable divergence (price dropped)
    if abs(divergence_pct) > 0.01:  # More than 1% worse
        return False, f"exit_unfavorable_{divergence_pct:.2%}"

    # Small unfavorable divergence - accept with warning
    return True, f"exit_slightly_unfavorable_{divergence_pct:.2%}"
```

### EXIT Decision Matrix

| Scenario | Divergence | Action | Rationale |
|----------|------------|--------|-----------|
| Price unchanged | 0% | ✅ Execute | Ideal scenario |
| Price improved | +0.5% to +2% | ✅ Execute | Better than expected exit |
| Price slightly worse | -0.5% | ✅ Execute with warning | Acceptable slippage |
| Price significantly worse | -1% to -2% | ❌ Reject | Missed exit, re-evaluate |
| Price crashed | > -2% | ❌ Reject + Alert | Major adverse move |

### EXIT Test Cases (5 tests)

```python
def test_exit_at_signal_price():
    """EXIT at signal price (no divergence) → Accept"""

def test_exit_favorable_divergence():
    """EXIT at +1% above signal → Accept (better exit)"""

def test_exit_small_unfavorable():
    """EXIT at -0.3% below signal → Accept with warning"""

def test_exit_large_unfavorable():
    """EXIT at -1.5% below signal → Reject"""

def test_exit_signal_age():
    """EXIT signal 45s old with -0.8% divergence → Reject (stale + unfavorable)"""
```

---

## Signal Age Validation

### Tiered Signal Age Handling

Signal age affects validation strictness. Older signals require tighter divergence thresholds.

```python
def validate_signal_age(signal_timestamp: str) -> tuple[bool, str, str]:
    """
    Tiered signal age validation.

    Tiers:
    - Fresh (< 10s): Normal thresholds
    - Slightly delayed (10-30s): Warning logged
    - Delayed (30-60s): Stricter divergence thresholds
    - Stale (> 60s): Reject

    Returns:
        (is_valid, severity, message)
    """
    age_seconds = (datetime.now() - parse_timestamp(signal_timestamp)).total_seconds()

    if age_seconds < 10:
        return True, "normal", "signal_fresh"

    elif age_seconds < 30:
        return True, "warning", f"signal_slightly_delayed_{age_seconds:.0f}s"

    elif age_seconds < 60:
        # Accept but require stricter divergence check
        return True, "elevated", f"signal_delayed_{age_seconds:.0f}s"

    else:
        return False, "rejected", f"signal_stale_{age_seconds:.0f}s"
```

### Adjusted Thresholds for Delayed Signals

```python
def get_divergence_threshold(signal_type: str, signal_age_severity: str) -> float:
    """
    Reduce divergence threshold for delayed signals.

    Delayed signals (30-60s) get 50% stricter thresholds.
    """
    base_threshold = {
        'BASE_ENTRY': 0.02,  # 2%
        'PYRAMID': 0.01,     # 1%
        'EXIT': 0.01         # 1%
    }[signal_type]

    if signal_age_severity == "elevated":
        return base_threshold * 0.5  # Halve threshold for delayed signals

    return base_threshold
```

### Signal Age Decision Matrix

| Signal Age | Severity | Divergence Threshold Adjustment | Action |
|------------|----------|--------------------------------|--------|
| < 10s | Normal | 100% (no change) | Process normally |
| 10-30s | Warning | 100% (no change) | Log warning, process |
| 30-60s | Elevated | 50% (halved) | Stricter validation |
| > 60s | Rejected | N/A | Reject signal |

### Signal Age + Divergence Examples

| Signal Type | Age | Divergence | Normal Threshold | Adjusted Threshold | Result |
|-------------|-----|------------|------------------|-------------------|--------|
| BASE_ENTRY | 5s | 1.5% | 2% | 2% | ✅ Accept |
| BASE_ENTRY | 45s | 1.5% | 2% | 1% | ❌ Reject |
| PYRAMID | 25s | 0.8% | 1% | 1% | ✅ Accept |
| PYRAMID | 50s | 0.8% | 1% | 0.5% | ❌ Reject |
| EXIT | 40s | -0.6% | 1% | 0.5% | ❌ Reject |

### Signal Age Test Cases (3 tests)

```python
def test_fresh_signal_full_threshold():
    """Signal age 5s, divergence 1.5% BASE_ENTRY → Accept (under 2%)"""

def test_delayed_signal_stricter_threshold():
    """Signal age 45s, divergence 1.5% BASE_ENTRY → Reject (over 1% adjusted)"""

def test_stale_signal_rejected():
    """Signal age 70s → Reject regardless of divergence"""
```

---

## Execution Strategies

### Strategy 1: Single Limit Order (Default)

**Use Case:** Normal market conditions, small spreads

```python
def execute_simple_limit(signal_data, execution_price):
    """
    Place single limit order at broker price
    Wait 10 seconds for fill
    Cancel if not filled
    """
    order_id = place_limit_order(
        instrument=signal_data['instrument'],
        lots=signal_data['lots'],
        price=execution_price
    )

    time.sleep(10)

    status = check_order_status(order_id)

    if status == 'FILLED':
        return get_fill_details(order_id)
    else:
        cancel_order(order_id)
        return {'status': 'cancelled', 'reason': 'no_fill_timeout'}
```

**Pros:**
- Simple, predictable
- No slippage beyond limit price

**Cons:**
- May not fill in fast markets
- Misses opportunities if market moves

---

### Strategy 2: Progressive Price Improvement (Aggressive)

**Use Case:** Volatile markets, important signals (base entries)

```python
def execute_with_progressive_improvement(
    signal_data,
    initial_price,
    max_attempts=3,
    max_total_slippage_pct=0.01
):
    """
    Try multiple price levels with progressive improvement
    Abort if slippage exceeds threshold
    """
    max_fill_price = initial_price * (1 + max_total_slippage_pct)

    # Attempt 1: Limit at initial price
    order_id = place_limit_order(price=initial_price)
    time.sleep(5)
    if check_filled(order_id):
        return get_fill_details(order_id)

    # Attempt 2: Improve by 0.3%
    improved_price_1 = initial_price * 1.003
    if improved_price_1 > max_fill_price:
        cancel_order(order_id)
        return {'status': 'aborted', 'reason': 'max_slippage_exceeded'}

    modify_order(order_id, price=improved_price_1)
    time.sleep(5)
    if check_filled(order_id):
        return get_fill_details(order_id)

    # Attempt 3: Check current market before final attempt
    current_price = get_current_quote()['ltp']

    if current_price > max_fill_price:
        cancel_order(order_id)
        return {'status': 'aborted', 'reason': 'market_moved_too_far'}

    final_price = min(current_price * 1.001, max_fill_price)
    modify_order(order_id, price=final_price)
    time.sleep(5)

    if check_filled(order_id):
        return get_fill_details(order_id)

    # Failed after max attempts
    cancel_order(order_id)
    return {'status': 'failed', 'reason': 'too_many_attempts'}
```

**Pros:**
- Higher fill rate
- Captures opportunities in fast markets
- Controlled slippage (max limit)

**Cons:**
- More complex
- Multiple API calls
- Could chase market

---

### Strategy 3: Market Order (NOT RECOMMENDED)

**Use Case:** NEVER for pyramids, ONLY for critical base entries with explicit approval

```python
def execute_market_order(signal_data):
    """
    ⚠️ WARNING: Use only for BASE_ENTRY with explicit approval
    ❌ NEVER use for PYRAMID
    """
    if signal_data['type'] == 'PYRAMID':
        raise ValueError("Market orders not allowed for pyramids!")

    # Log warning
    logger.warning("🚨 MARKET ORDER - Slippage unknown!")

    order_id = place_market_order(...)

    # Get actual fill price
    fill_price = get_fill_price(order_id)

    # Validate fill price after the fact
    if fill_price > signal_data['price'] * 1.02:  # More than 2% slippage
        logger.error(f"Excessive slippage: {fill_price} vs {signal_data['price']}")
        # Consider reversing trade or alerting

    return get_fill_details(order_id)
```

**Cons:**
- Unpredictable fill price
- Could get terrible fill in volatile markets
- Risk calculation becomes uncertain

---

## Risk Management

### Risk Increase Validation

```python
def validate_risk_increase(signal_price, broker_price, stop_price, signal_type):
    """
    Ensure risk doesn't increase beyond acceptable thresholds
    Critical for pyramids - prevents overleveraging
    """
    # Calculate risks
    original_risk = signal_price - stop_price
    execution_risk = broker_price - stop_price
    risk_increase_pct = (execution_risk - original_risk) / original_risk

    # Log risk analysis
    logger.info(
        f"Risk Analysis: "
        f"Original={original_risk:.2f}, "
        f"Execution={execution_risk:.2f}, "
        f"Increase={risk_increase_pct:.2%}"
    )

    # Thresholds
    MAX_RISK_INCREASE_PYRAMID = 0.20  # 20%
    MAX_RISK_INCREASE_BASE = 0.50     # 50%

    threshold = (
        MAX_RISK_INCREASE_PYRAMID if signal_type == 'PYRAMID'
        else MAX_RISK_INCREASE_BASE
    )

    if risk_increase_pct > threshold:
        return False, f"risk_increase_{risk_increase_pct:.2%}_exceeds_{threshold:.2%}"

    return True, risk_increase_pct
```

### Position Size Adjustment

```python
def adjust_position_size_for_risk(original_lots, risk_increase_pct):
    """
    Reduce position size when risk increases
    Maintains same rupee risk amount
    """
    if risk_increase_pct <= 0:
        # Risk decreased or same - no adjustment
        return original_lots

    # Reduce lots proportionally to risk increase
    adjusted_lots = int(original_lots / (1 + risk_increase_pct))

    logger.info(
        f"Position size adjusted: {original_lots} → {adjusted_lots} lots "
        f"(risk increased {risk_increase_pct:.2%})"
    )

    return max(adjusted_lots, 1)  # At least 1 lot
```

---

## Configuration

### SignalValidationConfig

```python
@dataclass
class SignalValidationConfig:
    """Configuration for signal validation logic"""

    # === Condition Validation ===
    TRUST_SIGNAL_CONDITIONS: bool = True
    """Trust TradingView signal for condition validation (1R check, P&L check)"""

    # === Divergence Thresholds ===
    MAX_DIVERGENCE_BASE_ENTRY: float = 0.02  # 2%
    """Maximum acceptable price divergence for BASE_ENTRY signals"""

    MAX_DIVERGENCE_PYRAMID: float = 0.01  # 1%
    """Maximum acceptable price divergence for PYRAMID signals (stricter!)"""

    DIVERGENCE_WARNING_THRESHOLD: float = 0.005  # 0.5%
    """Log warning if divergence exceeds this (but still accept)"""

    # === Risk Thresholds ===
    MAX_RISK_INCREASE_PYRAMID: float = 0.20  # 20%
    """Maximum acceptable risk increase for pyramids"""

    MAX_RISK_INCREASE_BASE: float = 0.50  # 50%
    """Maximum acceptable risk increase for base entries"""

    ADJUST_SIZE_ON_RISK_INCREASE: bool = True
    """Automatically reduce position size when risk increases"""

    # === Signal Age Thresholds ===
    MAX_SIGNAL_AGE_NORMAL: int = 10  # seconds
    """Normal signal age - no warnings"""

    MAX_SIGNAL_AGE_WARNING: int = 30  # seconds
    """Signal age triggers warning"""

    MAX_SIGNAL_AGE_STALE: int = 60  # seconds
    """Signal considered stale - reject if divergence also high"""

    # === Execution Strategy ===
    DEFAULT_EXECUTION_STRATEGY: str = "progressive"
    """Options: 'simple', 'progressive', 'market' (not recommended)"""

    PROGRESSIVE_MAX_ATTEMPTS: int = 3
    """Maximum price improvement attempts"""

    PROGRESSIVE_MAX_SLIPPAGE: float = 0.01  # 1%
    """Maximum total slippage for progressive execution"""

    SIMPLE_LIMIT_TIMEOUT: int = 10  # seconds
    """Timeout for simple limit orders"""

    # === Edge Case Handling ===
    ACCEPT_VALID_SIGNAL_DESPITE_PULLBACK: bool = True
    """Accept signals that were valid at generation even if market pulled back"""

    REJECT_CHASE_FOR_PYRAMIDS: bool = True
    """Reject pyramids if market surged ahead significantly"""

    ALLOW_MARKET_ORDERS_BASE_ENTRY: bool = False
    """Allow market orders for base entries (not recommended)"""

    ALLOW_MARKET_ORDERS_PYRAMID: bool = False
    """Allow market orders for pyramids (STRONGLY not recommended)"""

    # === EXIT Signal Thresholds (v1.1) ===
    MAX_DIVERGENCE_EXIT: float = 0.01  # 1%
    """Maximum unfavorable divergence for EXIT signals"""

    MAX_UNFAVORABLE_EXIT_DIVERGENCE: float = 0.01  # 1%
    """Reject EXIT if price dropped more than this (missed exit)"""
```

---

## Mock Broker Simulator

### Purpose

The MockBrokerSimulator provides a testing layer for signal validation without requiring:
- Live broker API access
- Paper trading account
- Real market data

It enables comprehensive testing of all market scenarios in a controlled, repeatable environment.

### Implementation

**File:** `tests/mocks/mock_broker.py`

```python
import random
import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class MarketScenario(Enum):
    """Predefined market behavior scenarios."""
    NORMAL = "normal"           # Small random divergence (-0.1% to +0.1%)
    VOLATILE = "volatile"       # Larger swings (-1% to +1%)
    SURGE = "surge"             # Market surged ahead (+0.5% to +2%)
    PULLBACK = "pullback"       # Market pulled back (-0.5% to -1.5%)
    GAP = "gap"                 # Price gap (+1.5% to +3%)
    FAST_MARKET = "fast_market" # Rapid movement, low fill probability


@dataclass
class MockQuote:
    """Simulated broker quote."""
    ltp: float
    bid: float
    ask: float
    timestamp: str
    scenario: str


class MockBrokerSimulator:
    """
    Simulates broker behavior for testing signal validation.

    Features:
    - Configurable market scenarios
    - Deterministic mode for reproducible tests
    - Fill probability based on scenario
    - Order modification simulation
    """

    def __init__(
        self,
        scenario: MarketScenario = MarketScenario.NORMAL,
        base_price: float = 50000.0,
        seed: Optional[int] = None
    ):
        """
        Initialize mock broker.

        Args:
            scenario: Market behavior scenario
            base_price: Base price for simulations
            seed: Random seed for reproducible tests
        """
        self.scenario = scenario
        self.base_price = base_price

        if seed is not None:
            random.seed(seed)

        self._pending_orders = {}

    def set_scenario(self, scenario: MarketScenario):
        """Switch market scenario during test."""
        self.scenario = scenario

    def set_base_price(self, price: float):
        """Set base price for divergence calculations."""
        self.base_price = price

    def get_quote(self, instrument: str) -> MockQuote:
        """
        Simulate broker quote with scenario-based behavior.

        Args:
            instrument: Trading symbol (ignored in mock)

        Returns:
            MockQuote with simulated prices
        """
        divergence = self._get_divergence_for_scenario()
        simulated_price = self.base_price * (1 + divergence)

        return MockQuote(
            ltp=simulated_price,
            bid=simulated_price * 0.9999,
            ask=simulated_price * 1.0001,
            timestamp=datetime.now().isoformat(),
            scenario=self.scenario.value
        )

    def _get_divergence_for_scenario(self) -> float:
        """Get price divergence based on current scenario."""
        divergence_ranges = {
            MarketScenario.NORMAL: (-0.001, 0.001),      # -0.1% to +0.1%
            MarketScenario.VOLATILE: (-0.01, 0.01),      # -1% to +1%
            MarketScenario.SURGE: (0.005, 0.02),         # +0.5% to +2%
            MarketScenario.PULLBACK: (-0.015, -0.005),   # -1.5% to -0.5%
            MarketScenario.GAP: (0.015, 0.03),           # +1.5% to +3%
            MarketScenario.FAST_MARKET: (-0.02, 0.02),   # -2% to +2%
        }

        min_div, max_div = divergence_ranges[self.scenario]
        return random.uniform(min_div, max_div)

    def place_limit_order(
        self,
        instrument: str,
        lots: int,
        price: float,
        side: str = "BUY"
    ) -> dict:
        """
        Simulate limit order placement.

        Fill probability varies by scenario:
        - NORMAL: 95%
        - VOLATILE: 70%
        - SURGE: 30%
        - PULLBACK: 90%
        - GAP: 10%
        - FAST_MARKET: 40%
        """
        order_id = str(uuid.uuid4())[:8]

        fill_prob = {
            MarketScenario.NORMAL: 0.95,
            MarketScenario.VOLATILE: 0.70,
            MarketScenario.SURGE: 0.30,
            MarketScenario.PULLBACK: 0.90,
            MarketScenario.GAP: 0.10,
            MarketScenario.FAST_MARKET: 0.40,
        }.get(self.scenario, 0.80)

        if random.random() < fill_prob:
            return {
                'status': 'FILLED',
                'order_id': order_id,
                'fill_price': price,
                'lots': lots
            }
        else:
            self._pending_orders[order_id] = {
                'price': price,
                'lots': lots,
                'instrument': instrument
            }
            return {
                'status': 'PENDING',
                'order_id': order_id
            }

    def modify_order(self, order_id: str, new_price: float) -> dict:
        """Simulate order modification with improved fill chance."""
        if order_id not in self._pending_orders:
            return {'status': 'ERROR', 'reason': 'order_not_found'}

        # 60% chance of fill on modification
        if random.random() < 0.60:
            order = self._pending_orders.pop(order_id)
            return {
                'status': 'FILLED',
                'order_id': order_id,
                'fill_price': new_price,
                'lots': order['lots']
            }

        self._pending_orders[order_id]['price'] = new_price
        return {'status': 'PENDING', 'order_id': order_id}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel pending order."""
        if order_id in self._pending_orders:
            self._pending_orders.pop(order_id)
            return {'status': 'CANCELLED', 'order_id': order_id}
        return {'status': 'ERROR', 'reason': 'order_not_found'}

    def check_order_status(self, order_id: str) -> dict:
        """Check if order is still pending."""
        if order_id in self._pending_orders:
            return {'status': 'PENDING', 'order_id': order_id}
        return {'status': 'UNKNOWN', 'order_id': order_id}
```

### Usage in Tests

```python
# tests/integration/test_signal_validation_integration.py

import pytest
from tests.mocks.mock_broker import MockBrokerSimulator, MarketScenario


@pytest.fixture
def mock_broker():
    """Create mock broker with deterministic seed."""
    return MockBrokerSimulator(
        scenario=MarketScenario.NORMAL,
        base_price=50000.0,
        seed=42  # Reproducible tests
    )


class TestSignalValidationWithMockBroker:

    def test_base_entry_normal_market(self, mock_broker):
        """BASE_ENTRY in normal market conditions."""
        mock_broker.set_scenario(MarketScenario.NORMAL)
        quote = mock_broker.get_quote("BANKNIFTY")

        # Divergence should be small (< 0.1%)
        divergence_pct = abs(quote.ltp - 50000) / 50000
        assert divergence_pct < 0.001

    def test_pyramid_market_surge(self, mock_broker):
        """PYRAMID rejected when market surges > 1%."""
        mock_broker.set_scenario(MarketScenario.SURGE)
        quote = mock_broker.get_quote("BANKNIFTY")

        # Divergence should be positive and significant
        divergence_pct = (quote.ltp - 50000) / 50000
        assert divergence_pct > 0.005  # > 0.5% surge

    def test_exit_market_pullback(self, mock_broker):
        """EXIT validation when market pulled back."""
        mock_broker.set_scenario(MarketScenario.PULLBACK)
        quote = mock_broker.get_quote("BANKNIFTY")

        # Price should be lower (unfavorable for LONG exit)
        assert quote.ltp < 50000

    def test_execution_volatile_market(self, mock_broker):
        """Order execution in volatile market - lower fill rate."""
        mock_broker.set_scenario(MarketScenario.VOLATILE)

        filled_count = 0
        for _ in range(100):
            result = mock_broker.place_limit_order("BANKNIFTY", 5, 50000)
            if result['status'] == 'FILLED':
                filled_count += 1

        # ~70% fill rate expected
        assert 60 <= filled_count <= 80

    def test_progressive_execution_simulation(self, mock_broker):
        """Simulate progressive execution with modifications."""
        mock_broker.set_scenario(MarketScenario.FAST_MARKET)

        # First attempt
        result = mock_broker.place_limit_order("BANKNIFTY", 5, 50000)
        if result['status'] == 'PENDING':
            # Modify with improved price
            result = mock_broker.modify_order(result['order_id'], 50100)

            if result['status'] == 'PENDING':
                # Second modification
                result = mock_broker.modify_order(result['order_id'], 50200)

        # Either filled or still pending after attempts
        assert result['status'] in ['FILLED', 'PENDING']
```

### Scenario Descriptions

| Scenario | Divergence Range | Fill Probability | Use Case |
|----------|------------------|------------------|----------|
| NORMAL | -0.1% to +0.1% | 95% | Standard market conditions |
| VOLATILE | -1% to +1% | 70% | Intraday volatility |
| SURGE | +0.5% to +2% | 30% | Market running away |
| PULLBACK | -0.5% to -1.5% | 90% | Favorable entry (worse exit) |
| GAP | +1.5% to +3% | 10% | Gap up opening |
| FAST_MARKET | -2% to +2% | 40% | Rapid price movement |

---

## Test Scenarios

### Unit Test Scenarios

#### 1. Price Divergence Scenarios

```python
def test_small_divergence_accepted():
    """Signal price: 50,000, Broker: 50,050 (0.1%) → Accept"""

def test_medium_divergence_warning():
    """Signal price: 50,000, Broker: 50,300 (0.6%) → Warning but accept"""

def test_large_divergence_rejected():
    """Signal price: 50,000, Broker: 51,000 (2%) → Reject"""

def test_pullback_accepted():
    """Signal price: 50,000, Broker: 49,950 (-0.1%) → Accept (better entry!)"""
```

#### 2. Risk Increase Scenarios

```python
def test_risk_increase_within_threshold():
    """Risk increase 15% → Accept for base entry"""

def test_risk_increase_exceeds_pyramid_threshold():
    """Risk increase 25% for pyramid → Reject"""

def test_risk_increase_adjusts_position_size():
    """Risk increase 30% → Reduce lots from 10 to 8"""

def test_risk_decrease_no_adjustment():
    """Risk decrease 10% → Keep original lot size"""
```

#### 3. Signal Age Scenarios

```python
def test_fresh_signal_accepted():
    """Signal age: 5 seconds → Accept"""

def test_old_signal_warning():
    """Signal age: 35 seconds → Warning but accept if divergence OK"""

def test_stale_signal_rejected():
    """Signal age: 70 seconds + high divergence → Reject"""
```

#### 4. Execution Strategy Scenarios

```python
def test_simple_limit_fills():
    """Simple limit order fills within timeout"""

def test_simple_limit_timeout():
    """Simple limit order doesn't fill → Cancel and report"""

def test_progressive_fills_first_attempt():
    """Progressive execution fills on first attempt"""

def test_progressive_fills_second_attempt():
    """Progressive execution fills after price improvement"""

def test_progressive_aborts_max_slippage():
    """Progressive execution aborts when max slippage reached"""

def test_progressive_aborts_market_moved():
    """Progressive execution aborts when market moved too far"""
```

### Integration Test Scenarios

#### 5. End-to-End Scenarios

```python
def test_base_entry_normal_conditions():
    """Full flow: Signal → Validate → Execute → Verify position created"""

def test_pyramid_market_pulled_back():
    """Pyramid signal, market pulled back, still accepted"""

def test_pyramid_market_surged_rejected():
    """Pyramid signal, market surged 2%, rejected"""

def test_pyramid_risk_increase_rejected():
    """Pyramid signal, risk increased 30%, rejected"""

def test_execution_slippage_within_limit():
    """Execution with 0.5% slippage → Accepted"""

def test_execution_slippage_exceeds_limit():
    """Execution with 1.5% slippage → Aborted"""
```

### Mock Market Scenarios

#### 6. Simulated Market Conditions

```python
def test_volatile_market_multiple_attempts():
    """Market volatile, takes 3 attempts to fill"""

def test_fast_market_misses_fill():
    """Market moving fast, all attempts fail"""

def test_gap_up_after_signal():
    """Market gaps up 1% after signal → Rejected"""

def test_whipsaw_pullback_then_surge():
    """Market pulls back then surges → Track behavior"""
```

---

## Implementation Plan

### Phase 1: Core Validation Logic (Week 1)

**Tasks:**
1. Implement `SignalValidator` class
2. Implement condition validation (trust signal price)
3. Implement execution validation (query broker)
4. Implement risk increase validation
5. Create unit tests for validation logic

**Deliverables:**
- `core/signal_validator.py`
- `tests/unit/test_signal_validator.py`
- Unit tests passing (55+ test cases, including EXIT and tiered age)

---

### Phase 2: Execution Strategies (Week 2)

**Tasks:**
1. Implement `OrderExecutor` base class
2. Implement `SimpleLimitExecutor`
3. Implement `ProgressiveExecutor`
4. Implement position size adjustment logic
5. Create unit tests for execution strategies

**Deliverables:**
- `core/order_executor.py`
- `tests/unit/test_order_executor.py`
- Unit tests passing (30+ test cases)

---

### Phase 0: Testing Infrastructure (Before Phase 1)

**Tasks:**
1. Create MockBrokerSimulator class
2. Implement market scenario simulation (NORMAL, VOLATILE, SURGE, PULLBACK, GAP)
3. Create deterministic mode for reproducible tests

**Deliverables:**
- `tests/mocks/mock_broker.py`
- Unit tests for MockBrokerSimulator (8 test cases)

---

### Phase 3: Integration & Testing (Week 3)

**Tasks:**
1. Integrate validator + executor into webhook handler
2. Create integration tests with MockBrokerSimulator
3. Create simulation tests with market scenarios
4. Manual testing (with mock broker or paper trading if available)
5. Documentation and runbook

**Deliverables:**
- Updated `live/engine.py` with validation
- `tests/integration/test_signal_validation_integration.py`
- `SIGNAL_VALIDATION_RUNBOOK.md`
- Integration tests passing (25+ scenarios)

---

### Phase 4: Production Hardening (Week 4)

**Tasks:**
1. Add comprehensive logging
2. Add metrics and monitoring
3. Add alerting for anomalies
4. Performance testing
5. Production deployment plan

**Deliverables:**
- Structured logging for all validation decisions
- Prometheus metrics
- Alert rules for Grafana
- Performance benchmarks
- Deployment checklist

---

## Appendix A: Example Logs

### Successful Execution

```
2025-11-30 10:30:05 INFO [SignalValidator] Validating PYRAMID signal
2025-11-30 10:30:05 INFO [SignalValidator] Stage 1: Condition validation with signal price
2025-11-30 10:30:05 INFO [SignalValidator] ✅ Conditions met: price_move=520.00 >= threshold=450.00
2025-11-30 10:30:05 INFO [SignalValidator] Stage 2: Execution validation with broker price
2025-11-30 10:30:05 INFO [SignalValidator] Broker price: 50,480 (signal: 50,500)
2025-11-30 10:30:05 INFO [SignalValidator] Divergence: -20.00 (-0.04%) - within threshold
2025-11-30 10:30:05 INFO [SignalValidator] Risk analysis: original=600.00, execution=580.00, decrease=3.33%
2025-11-30 10:30:05 INFO [SignalValidator] ✅ Execution validated
2025-11-30 10:30:05 INFO [OrderExecutor] Executing with SimpleLimitExecutor
2025-11-30 10:30:05 INFO [OrderExecutor] Placed limit order: ID=12345, Price=50,480
2025-11-30 10:30:12 INFO [OrderExecutor] ✅ Order filled: Price=50,480, Lots=5
```

### Rejected Due to High Divergence

```
2025-11-30 11:00:03 INFO [SignalValidator] Validating PYRAMID signal
2025-11-30 11:00:03 INFO [SignalValidator] Stage 1: Condition validation with signal price
2025-11-30 11:00:03 INFO [SignalValidator] ✅ Conditions met: price_move=550.00 >= threshold=450.00
2025-11-30 11:00:03 INFO [SignalValidator] Stage 2: Execution validation with broker price
2025-11-30 11:00:03 INFO [SignalValidator] Broker price: 50,800 (signal: 50,500)
2025-11-30 11:00:03 WARN [SignalValidator] Divergence: +300.00 (+0.59%) - exceeds warning threshold
2025-11-30 11:00:03 INFO [SignalValidator] Risk analysis: original=600.00, execution=900.00, increase=50.00%
2025-11-30 11:00:03 ERROR [SignalValidator] ❌ Risk increase 50.00% exceeds threshold 20.00%
2025-11-30 11:00:03 ERROR [SignalValidator] Signal rejected: risk_increase_too_high
```

---

## Appendix B: Configuration Examples

### Conservative (Low Risk)

```python
config = SignalValidationConfig(
    MAX_DIVERGENCE_BASE_ENTRY=0.01,     # 1% max
    MAX_DIVERGENCE_PYRAMID=0.005,        # 0.5% max
    MAX_RISK_INCREASE_PYRAMID=0.10,      # 10% max
    REJECT_CHASE_FOR_PYRAMIDS=True,
    DEFAULT_EXECUTION_STRATEGY="simple"
)
```

### Moderate (Balanced)

```python
config = SignalValidationConfig(
    MAX_DIVERGENCE_BASE_ENTRY=0.02,      # 2% max (default)
    MAX_DIVERGENCE_PYRAMID=0.01,         # 1% max (default)
    MAX_RISK_INCREASE_PYRAMID=0.20,      # 20% max (default)
    DEFAULT_EXECUTION_STRATEGY="progressive"
)
```

### Aggressive (High Opportunity)

```python
config = SignalValidationConfig(
    MAX_DIVERGENCE_BASE_ENTRY=0.03,      # 3% max
    MAX_DIVERGENCE_PYRAMID=0.015,        # 1.5% max
    MAX_RISK_INCREASE_PYRAMID=0.30,      # 30% max
    ACCEPT_VALID_SIGNAL_DESPITE_PULLBACK=True,
    DEFAULT_EXECUTION_STRATEGY="progressive",
    PROGRESSIVE_MAX_ATTEMPTS=5
)
```

---

## Test Count Summary (v1.1)

| Phase | Component | Test Cases |
|-------|-----------|------------|
| Phase 0 | MockBrokerSimulator | 8 |
| Phase 1 | SignalValidator (incl. EXIT, tiered age) | 55 |
| Phase 2 | OrderExecutor | 30 |
| Phase 3 | Integration Tests | 25 |
| Phase 4 | Performance Tests | 5 |
| **Total** | | **123** |

---

**Document Status:** Approved - Ready for Implementation
**Version:** 1.1 (December 1, 2025)
**Changes in v1.1:**
- Added EXIT signal validation logic
- Added tiered signal age handling (10s/30s/60s)
- Added MockBrokerSimulator specification
- Updated test count to 123
- Clarified file locations (`core/` instead of `live/` for reusable components)

**Related Documents:**
- `TASK28_REVIEW_FEEDBACK.md` - Review feedback
- TaskMaster Task #28 - Implementation tracking

**Review By:** Development Team
**Approval Required:** Yes (before implementation)
