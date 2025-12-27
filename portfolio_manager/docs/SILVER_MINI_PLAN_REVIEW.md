# Silver Mini PM Support - Plan Review & Gap Analysis

**Date:** 2025-12-24
**Reviewed Plan:** `/Users/shankarvasudevan/.cursor/plans/silver_mini_pm_support_d0239e79.plan.md`

---

## Verdict: Plan is ~70% Complete - Missing Critical Code Paths

The original plan correctly identifies core files but misses several critical code paths discovered during comprehensive codebase exploration.

---

## CRITICAL GAPS (Must Add to Plan)

### 1. Duplicate InstrumentType Enum (NOT IN PLAN)

**File:** `portfolio_manager/core/symbol_mapper.py` (Lines 24-28)

There's a **duplicate** InstrumentType enum definition that ALSO needs SILVER_MINI:
```python
class InstrumentType(Enum):
    """Instrument types"""
    GOLD_MINI = "GOLD_MINI"
    BANK_NIFTY = "BANK_NIFTY"
    COPPER = "COPPER"
    # MISSING: SILVER_MINI
```

**Impact:** Symbol translation will fail even if models.py is updated.

---

### 2. Position Sizers Dict in Engines (NOT IN PLAN)

**File:** `portfolio_manager/live/engine.py` (Lines 80-93)
```python
self.sizers = {
    InstrumentType.GOLD_MINI: TomBassoPositionSizer(...),
    InstrumentType.BANK_NIFTY: TomBassoPositionSizer(...),
    InstrumentType.COPPER: TomBassoPositionSizer(...)
    # MISSING: InstrumentType.SILVER_MINI
}
```

**File:** `portfolio_manager/backtest/engine.py` (Lines 39-52)
Same pattern - needs SILVER_MINI sizer.

**Impact:** Position sizing will crash with KeyError.

---

### 3. Portfolio State Hardcoded Values (NOT IN PLAN)

**File:** `portfolio_manager/core/portfolio_state.py`

**Margin per lot (Lines 175-180):**
```python
if instrument == "GOLD_MINI":
    margin_per_lot = 105000.0
elif instrument == "COPPER":
    margin_per_lot = 300000.0
else:  # BANK_NIFTY
    margin_per_lot = 270000.0
# MISSING: SILVER_MINI case
```

**Point value (Lines 221-226, 269-274):**
```python
if pos.instrument == "GOLD_MINI":
    point_value = 10.0
elif pos.instrument == "COPPER":
    point_value = 2500.0
else:  # BANK_NIFTY
    point_value = 30.0
# MISSING: SILVER_MINI case
```

**InstrumentType mapping (Lines 101-106):**
```python
if position.instrument == "BANK_NIFTY":
    inst_type = InstrumentType.BANK_NIFTY
elif position.instrument == "GOLD_MINI":
    inst_type = InstrumentType.GOLD_MINI
elif position.instrument == "COPPER":
    inst_type = InstrumentType.COPPER
# MISSING: SILVER_MINI case
```

**Impact:** Margin calculations, P&L, and config lookups will fail.

---

### 4. Pyramid Gate Instrument Matching (NOT IN PLAN)

**File:** `portfolio_manager/core/pyramid_gate.py` (Lines 51-56)

Same if/elif pattern for instrument type - needs SILVER_MINI case.

**Impact:** Pyramid entries will fail.

---

### 5. Stop Manager Instrument Matching (PARTIALLY IN PLAN)

**File:** `portfolio_manager/core/stop_manager.py` (Lines 65-73)

Plan mentions this file exists but doesn't specify the if/elif chain that needs updating.

---

### 6. Order Executor - Multiple Locations (NOT IN PLAN)

**File:** `portfolio_manager/core/order_executor.py`

**Exchange routing (Line 117):**
```python
if "GOLD" in instrument.upper() or "COPPER" in instrument.upper():
    exchange = "MCX"
```
Needs: `or "SILVER" in instrument.upper()`

**SimpleLimitExecutor symbol translation (Lines 148-173):**
- Has GOLD_MINI and COPPER cases
- MISSING: SILVER_MINI → SILVERM{DD}{MMM}{YY}FUT

**ProgressiveExecutor (Lines 733-758):**
Same symbol translation pattern - needs SILVER_MINI.

**Impact:** Orders won't be placed (wrong exchange, no symbol translation).

---

### 7. Strategy Manager Point Value (NOT IN PLAN)

**File:** `portfolio_manager/core/strategy_manager.py` (Line 415-417)
```python
point_value = 30 if position.instrument == 'BANK_NIFTY' else 10
```

**Impact:** Trade history P&L will be wrong for SILVER_MINI.

---

### 8. Signal Validator Point Value (NOT IN PLAN)

**File:** `portfolio_manager/core/signal_validator.py` (Lines 294-299)
```python
if signal.instrument == "BANK_NIFTY":
    point_value = 30.0
elif signal.instrument == "COPPER":
    point_value = 2500.0
else:  # GOLD_MINI
    point_value = 10.0
```

**Impact:** Pyramid 1R validation will use wrong point value.

---

### 9. Sync From Broker (NOT IN PLAN)

**File:** `portfolio_manager/sync_from_broker.py` (Lines 52-57)
```python
if 'COPPER' in symbol.upper():
    instrument = 'COPPER'
elif 'GOLDMINI' in symbol.upper():
    instrument = 'GOLD_MINI'
elif 'BANKNIFTY' in symbol.upper():
    instrument = 'BANK_NIFTY'
# MISSING: SILVERM detection
```

**Impact:** Manual position sync won't recognize Silver Mini.

---

### 10. Import From CSV Script (NOT IN PLAN)

**File:** `portfolio_manager/scripts/import_from_csv.py` (Line 158)
```python
lot_size = 10 if instrument == 'GOLD_MINI' else 15
```

**Impact:** CSV import will use wrong lot size.

---

## CORRECTIONS TO EXISTING PLAN ITEMS

### 1. Expiry Pattern - CONFIRMED

**Correct pattern:** Feb, Apr, Jun, Aug, Nov (5 months)
- NOT standard bimonthly (Oct/Dec)
- November replaces December (MCX-specific)
- Silver Main (30kg) uses Dec; Silver Mini (5kg) uses Nov

---

### 2. Rollover Executor Exchange Detection

Plan mentions adding SILVER_MINI to MCX handling but doesn't specify the exchange detection logic at line 926:
```python
exchange = "MCX" if ("GOLD" in symbol_upper or "COPPER" in symbol_upper) else "NFO"
```
Needs: `or "SILVER" in symbol_upper`

---

## ALREADY READY (No Changes Needed)

These files already have partial SILVER_MINI support:

| File | Line | Status |
|------|------|--------|
| `live/recovery.py` | 426 | `valid_instruments` includes SILVER_MINI |
| `portfolio_manager.py` | 2484-2486 | SILVERM symbol parsing ready |
| `core/broker_sync.py` | 481 | SILVERM detection ready |

---

## COMPLETE FILE LIST (Updated)

### Must Modify (35 locations across ~20 files):

| # | File | Location | Change |
|---|------|----------|--------|
| 1 | `core/models.py` | L10-14 | Add SILVER_MINI to InstrumentType enum |
| 2 | `core/models.py` | L107 | Add to Signal validation list |
| 3 | `core/models.py` | L443 | Add to Position validation (verify exists) |
| 4 | `core/symbol_mapper.py` | L24-28 | Add to DUPLICATE InstrumentType enum |
| 5 | `core/symbol_mapper.py` | L111-115 | Add to LOT_SIZES dict |
| 6 | `core/symbol_mapper.py` | translate() | Add SILVER_MINI case + symbol format |
| 7 | `core/config.py` | L9-52 | Add InstrumentConfig |
| 8 | `core/config.py` | L170-174 | Add market_close_times |
| 9 | `core/config.py` | L185-189 | Add eod_instruments_enabled |
| 10 | `core/config.py` | ~L84 | Add silver_mini_rollover_days |
| 11 | `core/portfolio_state.py` | L101-106 | Add InstrumentType mapping |
| 12 | `core/portfolio_state.py` | L175-180 | Add margin_per_lot |
| 13 | `core/portfolio_state.py` | L221-226 | Add point_value |
| 14 | `core/pyramid_gate.py` | L51-56 | Add InstrumentType mapping |
| 15 | `core/stop_manager.py` | L65-73 | Add InstrumentType mapping |
| 16 | `core/signal_validator.py` | L294-299 | Add point_value case |
| 17 | `core/order_executor.py` | L117 | Add SILVER to MCX exchange check |
| 18 | `core/order_executor.py` | L148-173 | Add symbol translation |
| 19 | `core/strategy_manager.py` | L415-417 | Add point_value case |
| 20 | `core/expiry_calendar.py` | L59-62 | Add DEFAULT_ROLLOVER_DAYS |
| 21 | `core/expiry_calendar.py` | L297-301 | Add to exchange mapping |
| 22 | `core/lot_size_history.py` | L71-89 | Add SILVER_MINI case |
| 23 | `live/engine.py` | L80-93 | Add to sizers dict |
| 24 | `live/expiry_utils.py` | NEW | Add get_silver_mini_expiry() |
| 25 | `live/expiry_utils.py` | NEW | Add format_silver_mini_futures_symbol() |
| 26 | `live/expiry_utils.py` | L555 | Add to MCX market hours |
| 27 | `live/rollover_scanner.py` | L161-167 | Add rollover_days case |
| 28 | `live/rollover_scanner.py` | L211-215 | Add to MCX futures group |
| 29 | `live/rollover_executor.py` | L185-200 | Add dispatch case |
| 30 | `live/rollover_executor.py` | NEW | Add _rollover_silver_mini_position() |
| 31 | `live/rollover_executor.py` | L926 | Add SILVER to exchange detection |
| 32 | `backtest/engine.py` | L39-52 | Add to sizers dict |
| 33 | `sync_from_broker.py` | L52-57 | Add SILVERM detection |
| 34 | `core/voice_announcer.py` | TBD | Add pronunciation |
| 35 | `scripts/import_from_csv.py` | L158 | Fix lot_size logic |

### Test Files:
| # | File | Change |
|---|------|--------|
| 36 | `tests/unit/test_symbol_mapper.py` | Add SILVER_MINI tests |
| 37 | `tests/unit/test_signal_validator.py` | Add SILVER_MINI tests |
| 38 | `tests/fixtures/` | Add SILVER_MINI fixtures |

---

## RESOLVED SPECIFICATIONS

| Parameter | Value | Source |
|-----------|-------|--------|
| **Expiry Pattern** | Feb, Apr, Jun, Aug, Nov | MCX circular (confirmed) |
| **Lot Size** | 5 kg per contract | MCX standard |
| **Point Value** | Rs 5 per Rs 1/kg move | 5kg x Re 1 |
| **Margin** | ~Rs 2,00,000 per lot | Estimate (verify with broker) |
| **Rollover Days** | 8 days before expiry | Tender period consideration |
| **Symbol Format** | SILVERM{YYMMMDD}FUT | e.g., SILVERM25NOV28FUT |

---

## Critical Expiry Logic Note

```python
SILVER_MINI_CONTRACT_MONTHS = [2, 4, 6, 8, 11]  # Feb, Apr, Jun, Aug, Nov

def get_next_silver_mini_contract_month(current_month: int) -> Tuple[int, bool]:
    """Returns (contract_month, rolled_to_next_year)"""
    for m in SILVER_MINI_CONTRACT_MONTHS:
        if m >= current_month:
            return m, False
    # Roll to next year's February (not December!)
    return 2, True
```

**Edge case:** In December, the active contract is February of NEXT year (not November).

---

## RECOMMENDED IMPLEMENTATION ORDER

### Phase 1 - Core Types (blocks everything else)
1. `models.py` (enum + validation)
2. `symbol_mapper.py` (enum + LOT_SIZES)
3. `config.py` (InstrumentConfig)

### Phase 2 - Instrument Logic
4. `portfolio_state.py` (margin, point_value, type mapping)
5. `pyramid_gate.py`, `stop_manager.py`, `signal_validator.py`
6. `strategy_manager.py`

### Phase 3 - Expiry & Symbols
7. `expiry_utils.py` (new functions)
8. `expiry_calendar.py`
9. `order_executor.py` (exchange + symbol)

### Phase 4 - Execution
10. `live/engine.py` + `backtest/engine.py` (sizers)
11. `rollover_scanner.py` + `rollover_executor.py`

### Phase 5 - Utilities & Tests
12. `sync_from_broker.py`, `voice_announcer.py`
13. All test files

---

## Summary

| Metric | Original Plan | After Review |
|--------|---------------|--------------|
| Files identified | 14 | 20+ |
| Code locations | ~15 | 35+ |
| Test files | 4 | 4 |
| Completeness | ~70% | 100% |
