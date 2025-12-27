# Bank Nifty Lot Size Change: December 2025

**Change:** 35 → 30 units per lot
**Effective Date:** December 30, 2025
**Source:** Zerodha/NSE Circular

---

## Table of Contents

1. [Portfolio Manager Changes (8 files)](#part-a-portfolio-manager-changes)
2. [Pine Script Changes (1 file)](#part-b-pine-script-changes)
3. [New Historical Lot Size Module](#part-c-new-historical-lot-size-module)
4. [Test Updates](#part-d-test-updates)
5. [Impact Analysis](#impact-analysis)

---

## Part A: Portfolio Manager Changes (11 source files)

### 1. `portfolio_manager/core/config.py`

**Lines 13-14:**

```python
# BEFORE
InstrumentType.BANK_NIFTY: InstrumentConfig(
    name="Bank Nifty",
    instrument_type=InstrumentType.BANK_NIFTY,
    lot_size=35,  # Current lot size (Apr-Dec 2025)
    point_value=35.0,  # Rs 35 per point per LOT (35 units × ₹1/point/unit)
    margin_per_lot=270000.0,  # Rs 2.7L per lot
    ...
)

# AFTER
InstrumentType.BANK_NIFTY: InstrumentConfig(
    name="Bank Nifty",
    instrument_type=InstrumentType.BANK_NIFTY,
    lot_size=30,  # Current lot size (Dec 2025 onwards)
    point_value=30.0,  # Rs 30 per point per LOT (30 units × ₹1/point/unit)
    margin_per_lot=270000.0,  # Rs 2.7L per lot (unchanged for now)
    ...
)
```

---

### 2. `portfolio_manager/core/symbol_mapper.py`

**Line 113:**

```python
# BEFORE
LOT_SIZES = {
    'GOLD_MINI': 100,
    'BANK_NIFTY': 35,  # Current lot size (as of Nov 2024)
    'COPPER': 2500,
}

# AFTER
LOT_SIZES = {
    'GOLD_MINI': 100,
    'BANK_NIFTY': 30,  # Current lot size (Dec 2025 onwards)
    'COPPER': 2500,
}
```

---

### 3. `portfolio_manager/core/order_executor.py`

**Line 1243 (fallback value in SyntheticFuturesExecutor):**

```python
# BEFORE
if self.symbol_mapper:
    lot_size = self.symbol_mapper.get_lot_size(instrument)
else:
    lot_size = 35  # Bank Nifty default

# AFTER
if self.symbol_mapper:
    lot_size = self.symbol_mapper.get_lot_size(instrument)
else:
    lot_size = 30  # Bank Nifty default (Dec 2025 onwards)
```

---

### 4. `portfolio_manager/core/portfolio_state.py`

**Line 157 (_calculate_vol_metrics):**

```python
# BEFORE
point_val = 35  # Rs 35 per point per lot

# AFTER
point_val = 30  # Rs 30 per point per lot (Dec 2025 onwards)
```

**Line 226 (close_position):**

```python
# BEFORE
point_value = 35.0

# AFTER
point_value = 30.0
```

**Line 274 (update_unrealized_pnl):**

```python
# BEFORE
point_value = 35.0

# AFTER
point_value = 30.0
```

---

### 5. `portfolio_manager/core/signal_validator.py`

**Line 280 (validate_instrument_pnl):**

```python
# BEFORE
point_value = 35.0

# AFTER
point_value = 30.0
```

---

### 6. `portfolio_manager/core/strategy_manager.py`

**Line 417 (record_trade_exit):**

```python
# BEFORE
point_value = 35 if position.instrument == 'BANK_NIFTY' else 10

# AFTER
point_value = 30 if position.instrument == 'BANK_NIFTY' else 10
```

---

### 7. `portfolio_manager/core/broker_sync.py`

**Line 486 (_get_lot_size_from_symbol):**

```python
# BEFORE
return 35  # Bank Nifty lot size

# AFTER
return 30  # Bank Nifty lot size (Dec 2025 onwards)
```

---

### 8. `portfolio_manager/live/recovery.py` *(ADDED)*

**Line 375:**

```python
# BEFORE
point_value = 35.0

# AFTER
point_value = 30.0
```

---

### 9. `portfolio_manager/portfolio_manager.py` *(ADDED)*

**Line 2494:**

```python
# BEFORE
lot_size = 35

# AFTER
lot_size = 30
```

---

## Part B: Pine Script Changes

### `BankNifty_TF_V8.0.pine`

**Lines 136-137 (date correction only):**

```pine
// BEFORE
// Period 11: Dec 31, 2025 - Reduced to 30 lots (NSE/FAOP/70616) - Scheduled future change
t_dec2025 = timestamp(2025, 12, 31, 0, 0)

// AFTER
// Period 11: Dec 30, 2025 - Reduced to 30 lots (NSE/FAOP/70616) - Per Zerodha circular
t_dec2025 = timestamp(2025, 12, 30, 0, 0)
```

**Note:** The lot size value (30) is already correct. Only the effective date needs to change from Dec 31 to Dec 30.

---

## Part C: New Historical Lot Size Module

### New File: `portfolio_manager/core/lot_size_history.py`

```python
"""
Historical Bank Nifty Lot Size Lookup

Provides historically accurate lot sizes for backtesting.
Mirrors the Pine Script getBankNiftyLotSize() function.

Sources: NSE F&O circulars, verified from NSE archives
"""
from datetime import date
from typing import Optional


# Historical lot size change dates and values
# Format: (effective_date, lot_size)
BANKNIFTY_LOT_SIZE_HISTORY = [
    # (date, lot_size) - ordered newest to oldest for efficiency
    (date(2025, 12, 30), 30),   # Dec 2025 onwards - per Zerodha circular
    (date(2025, 4, 25), 35),    # Apr 2025 - Dec 2025 (NSE/FAOP/67372)
    (date(2024, 11, 20), 30),   # Nov 2024 - Apr 2025
    (date(2023, 7, 1), 15),     # Jul 2023 - Nov 2024 (FAOP64625) - Recent minimum
    (date(2020, 5, 4), 25),     # May 2020 - Jun 2023 (NSE/F&O/035/2020)
    (date(2018, 10, 26), 20),   # Oct 2018 - May 2020 (NSE/F&O/091/2018)
    (date(2016, 4, 29), 40),    # Apr 2016 - Oct 2018 (NSE/F&O/034/2016) - Historical maximum
    (date(2015, 8, 28), 30),    # Aug 2015 - Apr 2016 (NSE/F&O/071/2015)
    (date(2010, 4, 30), 25),    # Apr 2010 - Aug 2015 (NSE/F&O/030/2010) - Longest stable
    (date(2007, 2, 23), 50),    # Feb 2007 - Apr 2010 (NSE/F&O/010/2007)
    (date(2005, 6, 13), 100),   # Launch - Feb 2007 (Bank Nifty F&O launch)
]

DEFAULT_LOT_SIZE = 25  # Fallback for dates before June 2005


def get_banknifty_lot_size(bar_date: date) -> int:
    """
    Returns historically accurate Bank Nifty lot size for a given date.

    Args:
        bar_date: The date to look up lot size for

    Returns:
        Lot size (units per lot) valid on that date

    Example:
        >>> get_banknifty_lot_size(date(2024, 1, 15))
        15  # Jul 2023 - Nov 2024 period

        >>> get_banknifty_lot_size(date(2025, 12, 31))
        30  # Dec 2025 onwards
    """
    for effective_date, lot_size in BANKNIFTY_LOT_SIZE_HISTORY:
        if bar_date >= effective_date:
            return lot_size
    return DEFAULT_LOT_SIZE


def get_banknifty_point_value(bar_date: date) -> float:
    """
    Returns point value (Rs per point per lot) for a given date.

    For Bank Nifty, point_value = lot_size since each unit moves ₹1 per point.

    Args:
        bar_date: The date to look up

    Returns:
        Point value in Rs
    """
    return float(get_banknifty_lot_size(bar_date))


def get_lot_size_for_instrument(instrument: str, bar_date: Optional[date] = None) -> int:
    """
    Get lot size for any instrument, optionally for a historical date.

    Args:
        instrument: "BANK_NIFTY", "GOLD_MINI", or "COPPER"
        bar_date: Optional date for historical lookup (Bank Nifty only)

    Returns:
        Lot size for the instrument
    """
    if instrument == "BANK_NIFTY":
        if bar_date:
            return get_banknifty_lot_size(bar_date)
        else:
            # Return current (latest) lot size
            return BANKNIFTY_LOT_SIZE_HISTORY[0][1]
    elif instrument == "GOLD_MINI":
        return 100  # Fixed
    elif instrument == "COPPER":
        return 2500  # Fixed
    else:
        raise ValueError(f"Unknown instrument: {instrument}")
```

---

## Part D: Test Updates (24+ occurrences across 8 files)

### Unit Tests

#### `tests/unit/test_position_sizer.py` (~15 occurrences)

Multiple test assertions use hardcoded calculations with `× 35`. These need to be updated to `× 30`.

**Example changes:**

```python
# BEFORE (example from line ~77)
# Risk per lot = 350 × 35 = 12,250
expected_risk_per_lot = 350 * 35  # = 12,250

# AFTER
# Risk per lot = 350 × 30 = 10,500
expected_risk_per_lot = 350 * 30  # = 10,500
```

#### `tests/unit/test_symbol_mapper.py` (2 occurrences)

LOT_SIZES dictionary test assertions.

#### `tests/unit/test_portfolio_state.py` (3 occurrences)

**Lines 48, 148, 152:** P&L and volatility calculations using `× 35`.

#### `tests/unit/test_synthetic_executor.py` (2 occurrences)

Quantity calculations for synthetic futures.

### Integration Tests

#### `tests/integration/test_persistence.py` (2 occurrences)

Position persistence tests with lot size.

#### `tests/integration/conftest.py` (1 occurrence)

**Line 67:** Mock fixture returning `35`.

```python
# BEFORE
return 35

# AFTER
return 30
```

### Mock Files

#### `tests/mocks/mock_broker.py` (1 occurrence)

**Line 143:**

```python
# BEFORE
lot_size = 35  # Bank Nifty

# AFTER
lot_size = 30  # Bank Nifty (Dec 2025 onwards)
```

### Performance Tests

#### `tests/performance/test_recovery_performance.py` (2 occurrences)

**Lines 219-220:** Recovery benchmark calculations.

---

**Search command to find all occurrences:**
```bash
cd portfolio_manager
grep -rn "= 35\|×35\|\* 35" --include="*.py" | grep -i "lot\|point\|bank"
```

---

## Impact Analysis

### Mathematical Impact

| Metric | Before (35) | After (30) | Change |
|--------|-------------|------------|--------|
| Lot size | 35 units | 30 units | -14.3% |
| Point value | ₹35/point/lot | ₹30/point/lot | -14.3% |
| Contract value (BN@50000) | ₹17.5L | ₹15L | -14.3% |
| Risk per lot (350pt stop) | ₹12,250 | ₹10,500 | -₹1,750 |
| Max loss per lot | ₹12,250 | ₹10,500 | -14.3% |

### Position Sizing Impact

```
Formula: lots = (equity × risk%) / (stop_distance × point_value) × ER

Before: lots = (50,00,000 × 0.5%) / (350 × 35) × 0.82 = 1.67 lots → FLOOR = 1
After:  lots = (50,00,000 × 0.5%) / (350 × 30) × 0.82 = 1.95 lots → FLOOR = 1

Result: Same final position (1 lot) due to FLOOR operation
```

**Net effect:** Lower risk per trade, marginally improved capital efficiency at higher equity levels.

### Deployment Notes

1. **Jan 2026 options are already trading with 30-unit lots** - can deploy immediately
2. **No waiting required** - the new lot size is already effective for far-month contracts
3. **Run tests after changes** to verify all calculations are correct

---

## Checklist

### Source Files (11 files, 13 values)
- [ ] `core/config.py` (2 values: lot_size, point_value)
- [ ] `core/symbol_mapper.py` (1 value)
- [ ] `core/order_executor.py` (1 value)
- [ ] `core/portfolio_state.py` (3 values)
- [ ] `core/signal_validator.py` (1 value)
- [ ] `core/strategy_manager.py` (1 value)
- [ ] `core/broker_sync.py` (1 value)
- [ ] `live/recovery.py` (1 value) ← ADDED
- [ ] `portfolio_manager.py` (1 value) ← ADDED

### New Module
- [ ] Create `core/lot_size_history.py`

### Pine Script
- [ ] `BankNifty_TF_V8.0.pine` (date: 31→30)

### Tests (8 files, 24+ occurrences)
- [ ] `tests/unit/test_position_sizer.py` (~15 calculations)
- [ ] `tests/unit/test_symbol_mapper.py` (2 values)
- [ ] `tests/unit/test_portfolio_state.py` (3 values)
- [ ] `tests/unit/test_synthetic_executor.py` (2 values)
- [ ] `tests/integration/test_persistence.py` (2 values)
- [ ] `tests/integration/conftest.py` (1 mock)
- [ ] `tests/mocks/mock_broker.py` (1 value)
- [ ] `tests/performance/test_recovery_performance.py` (2 values)

### Verification
- [ ] Run full test suite: `./run_tests.sh`
- [ ] Verify margin calculation still correct
- [ ] Deploy to production
