# Task 30: Critical Bug Fixes - Test Plan

## Bug #1: Missing Enum Import in Alerts

### Test Objective
Verify that `AlertSeverity(Enum)` can be imported and instantiated without `NameError`.

### Test Cases

#### TC-30.1.1: Import Test
- **Description:** Verify module imports successfully
- **Steps:**
  1. Import `SignalValidationAlerts` from `core.signal_validation_alerts`
  2. Import `AlertSeverity` from `core.signal_validation_alerts`
- **Expected:** No ImportError or NameError
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug1_enum_import`

#### TC-30.1.2: Enum Instantiation Test
- **Description:** Verify AlertSeverity enum values work correctly
- **Steps:**
  1. Create `AlertSeverity.WARNING`
  2. Create `AlertSeverity.CRITICAL`
  3. Verify enum comparison works
- **Expected:** Enum values created successfully, comparisons work
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug1_enum_values`

#### TC-30.1.3: Alert Creation Test
- **Description:** Verify Alert dataclass can be created with AlertSeverity
- **Steps:**
  1. Create Alert instance with `severity=AlertSeverity.WARNING`
  2. Create Alert instance with `severity=AlertSeverity.CRITICAL`
  3. Verify severity field is correct
- **Expected:** Alert objects created successfully
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug1_alert_creation`

#### TC-30.1.4: SignalValidationAlerts Integration Test
- **Description:** Verify full alerting system works
- **Steps:**
  1. Create SignalValidationAlerts instance
  2. Trigger alert condition (high rejection rate)
  3. Verify alert is created with correct severity
- **Expected:** Alert generated with AlertSeverity enum
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug1_alerting_system`

---

## Bug #2: AttributeError on severity Field

### Test Objective
Verify that execution validation metrics are recorded correctly without accessing non-existent `severity` field.

### Test Cases

#### TC-30.2.1: Execution Validation Metric Recording (BASE_ENTRY)
- **Description:** Verify metrics recorded for BASE_ENTRY execution validation
- **Steps:**
  1. Create LiveTradingEngine with metrics
  2. Process BASE_ENTRY signal
  3. Trigger execution validation (passed)
  4. Verify metrics.record_validation called WITHOUT severity parameter
- **Expected:** No AttributeError, metrics recorded correctly
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug2_base_entry_metrics`

#### TC-30.2.2: Execution Validation Metric Recording (PYRAMID)
- **Description:** Verify metrics recorded for PYRAMID execution validation
- **Steps:**
  1. Create LiveTradingEngine with metrics
  2. Process PYRAMID signal
  3. Trigger execution validation (passed)
  4. Verify metrics.record_validation called WITHOUT severity parameter
- **Expected:** No AttributeError, metrics recorded correctly
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug2_pyramid_metrics`

#### TC-30.2.3: Execution Validation Rejection Metrics
- **Description:** Verify metrics recorded when execution validation fails
- **Steps:**
  1. Create LiveTradingEngine with metrics
  2. Process signal with high price divergence
  3. Trigger execution validation (failed)
  4. Verify rejection_reason recorded, no severity field accessed
- **Expected:** Rejection metrics recorded without AttributeError
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug2_rejection_metrics`

#### TC-30.2.4: Metrics Structure Validation
- **Description:** Verify recorded metrics have correct structure
- **Steps:**
  1. Record execution validation metric
  2. Inspect metric structure
  3. Verify severity field is NOT present
  4. Verify divergence_pct, risk_increase_pct ARE present
- **Expected:** Correct metric structure without severity
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug2_metrics_structure`

---

## Bug #3: Performance Test ValueError

### Test Objective
Verify that p95 latency calculation handles small sample sizes correctly.

### Test Cases

#### TC-30.3.1: Small Sample Size (10 samples)
- **Description:** Verify quantiles fallback works with 10 samples
- **Steps:**
  1. Run test with 10 signal processing iterations
  2. Calculate p95 latency
  3. Verify no ValueError raised
- **Expected:** Uses max(times) fallback, no error
- **Automated:** Yes - `tests/performance/test_signal_validation_performance.py::test_overall_latency_small_sample`

#### TC-30.3.2: Large Sample Size (100 samples)
- **Description:** Verify quantiles works with sufficient samples
- **Steps:**
  1. Run test with 100 signal processing iterations
  2. Calculate p95 latency using quantiles
  3. Verify correct p95 value
- **Expected:** Uses statistics.quantiles, correct p95 calculation
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug3_large_sample`

#### TC-30.3.3: Edge Case - Exactly 20 samples
- **Description:** Verify quantiles works at boundary condition
- **Steps:**
  1. Create list with exactly 20 samples
  2. Calculate p95 using quantiles
  3. Verify no error
- **Expected:** Uses statistics.quantiles successfully
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug3_boundary_condition`

#### TC-30.3.4: Edge Case - 19 samples
- **Description:** Verify fallback works just below boundary
- **Steps:**
  1. Create list with 19 samples
  2. Calculate p95 using fallback
  3. Verify uses max(times)
- **Expected:** Uses fallback, returns max value
- **Automated:** Yes - `tests/unit/test_bug_fixes.py::test_bug3_fallback_boundary`

---

## Test Execution Plan

### Phase 1: Unit Tests (15 minutes)
```bash
# Run all bug fix unit tests
pytest tests/unit/test_bug_fixes.py -v

# Expected: All 11 tests pass
```

### Phase 2: Integration Tests (5 minutes)
```bash
# Run signal validation integration tests
pytest tests/integration/test_signal_validation_integration.py -v

# Verify no regressions from bug fixes
```

### Phase 3: Performance Tests (10 minutes)
```bash
# Run performance tests with bug fix
pytest tests/performance/test_signal_validation_performance.py -v

# Verify no ValueError on small sample sizes
```

### Phase 4: Full Test Suite (30 minutes)
```bash
# Run entire test suite
pytest tests/ -v --cov=core --cov=live

# Verify no regressions anywhere
```

---

## Success Criteria

### Bug #1 Success Criteria
- ✅ All 4 test cases pass
- ✅ No ImportError or NameError
- ✅ Alerting system functional
- ✅ Alert severity enum works correctly

### Bug #2 Success Criteria
- ✅ All 4 test cases pass
- ✅ No AttributeError in engine.py
- ✅ Metrics recorded correctly for BASE_ENTRY and PYRAMID
- ✅ Rejection metrics work without severity field

### Bug #3 Success Criteria
- ✅ All 4 test cases pass
- ✅ No ValueError on small sample sizes
- ✅ Quantiles work correctly on large samples
- ✅ Boundary conditions handled properly

---

## Regression Testing

### Areas to Verify
1. **Signal Validation:** Ensure validation logic unchanged
2. **Metrics Collection:** Verify all other metrics still recorded
3. **Alerting:** Verify other alert types still work
4. **Performance:** Verify no performance degradation

### Regression Test Commands
```bash
# Existing signal validator tests
pytest tests/unit/test_signal_validator.py -v

# Existing metrics tests
pytest tests/unit/test_signal_validation_metrics.py -v

# Existing engine tests
pytest tests/unit/test_engine.py -v
```

---

## Manual Testing (Optional)

### Manual Test 1: Import Verification
```bash
cd portfolio_manager
python3 -c "from core.signal_validation_alerts import SignalValidationAlerts, AlertSeverity; print('✅ Import successful')"
```

### Manual Test 2: Engine Execution
```bash
# Start engine and process test signal
# Verify no AttributeError in logs
```

### Manual Test 3: Performance Test
```bash
# Run performance test manually
pytest tests/performance/test_signal_validation_performance.py::test_overall_latency -v
```

---

## Test Coverage Requirements

- **Minimum Coverage:** 90% for modified files
- **Target Coverage:** 95% for bug fix code paths
- **Critical Paths:** 100% coverage for:
  - Enum import and usage
  - Metrics recording without severity
  - Quantiles fallback logic

---

## Test Automation Status

| Test Case | Automated | File | Status |
|-----------|-----------|------|--------|
| TC-30.1.1 | ✅ | test_bug_fixes.py | To be created |
| TC-30.1.2 | ✅ | test_bug_fixes.py | To be created |
| TC-30.1.3 | ✅ | test_bug_fixes.py | To be created |
| TC-30.1.4 | ✅ | test_bug_fixes.py | To be created |
| TC-30.2.1 | ✅ | test_bug_fixes.py | To be created |
| TC-30.2.2 | ✅ | test_bug_fixes.py | To be created |
| TC-30.2.3 | ✅ | test_bug_fixes.py | To be created |
| TC-30.2.4 | ✅ | test_bug_fixes.py | To be created |
| TC-30.3.1 | ✅ | test_signal_validation_performance.py | Already exists (modified) |
| TC-30.3.2 | ✅ | test_bug_fixes.py | To be created |
| TC-30.3.3 | ✅ | test_bug_fixes.py | To be created |
| TC-30.3.4 | ✅ | test_bug_fixes.py | To be created |

**Total Test Cases:** 12
**Automated:** 12 (100%)
**To be created:** 11
**Already exists:** 1 (modified)

