# Testing Guide - Tom Basso Portfolio Manager

## Test Suite Overview

Total Tests: **42 tests** across 3 categories

### Test Categories

| Category | Files | Tests | Purpose |
|----------|-------|-------|---------|
| **Unit** | 3 | 31 | Test individual components |
| **Integration** | 1 | 8 | Test components together |
| **End-to-End** | 1 | 3 | Test complete workflows |

## Running Tests

### Quick Test (All Tests)

```bash
./run_tests.sh
```

### Detailed Test Commands

```bash
# All unit tests
pytest tests/unit/ -v

# All integration tests  
pytest tests/integration/ -v

# All end-to-end tests
pytest tests/test_end_to_end.py -v

# Specific test file
pytest tests/unit/test_position_sizer.py -v

# Specific test function
pytest tests/unit/test_position_sizer.py::TestTomBassoPositionSizer::test_risk_based_lots_calculation -v

# With print statements (debugging)
pytest tests/ -v -s

# Stop on first failure
pytest tests/ -v -x

# Run only fast tests (skip slow)
pytest tests/ -v -m "not slow"
```

## Test Coverage

### Generate Coverage Report

```bash
pytest tests/ --cov=core --cov=backtest --cov=live --cov-report=html --cov-report=term-missing
```

### View HTML Report

```bash
open htmlcov/index.html  # Mac
xdg-open htmlcov/index.html  # Linux
```

### Target Coverage

| Module | Target | Purpose |
|--------|--------|---------|
| `core/position_sizer.py` | >90% | Critical sizing logic |
| `core/portfolio_state.py` | >85% | Risk calculations |
| `core/pyramid_gate.py` | >80% | Gate logic |
| `core/stop_manager.py` | >85% | Stop management |
| `backtest/engine.py` | >75% | Backtest workflow |

## Test Descriptions

### Unit Tests: Position Sizer

| Test | Validates |
|------|-----------|
| `test_risk_based_lots_calculation` | Lot-R formula correct |
| `test_volatility_based_lots_calculation` | Lot-V formula correct |
| `test_margin_based_lots_calculation` | Lot-M formula correct |
| `test_final_lots_takes_minimum` | MIN(R,V,M) logic |
| `test_limiter_identification` | Correct limiter identified |
| `test_zero_lots_when_invalid_risk` | Handles invalid stops |
| `test_efficiency_ratio_multiplier_effect` | ER multiplier works |
| `test_pyramid_50_percent_rule` | 50% constraint works |
| `test_peel_off_calculation` | Peel-off math correct |

### Unit Tests: Portfolio State

| Test | Validates |
|------|-----------|
| `test_initialization` | Correct initial state |
| `test_add_position` | Position tracking |
| `test_closed_equity_calculation` | Realized equity |
| `test_open_equity_with_unrealized_pnl` | Unrealized P&L |
| `test_blended_equity_calculation` | 50% unrealized weighting |
| `test_portfolio_risk_calculation` | Risk aggregation |
| `test_margin_utilization_calculation` | Margin tracking |
| `test_portfolio_gate_blocks_over_limit` | 15% cap enforced |

### Unit Tests: Stop Manager

| Test | Validates |
|------|-----------|
| `test_initial_stop_calculation` | Initial stop formula |
| `test_trailing_stop_ratchets_up` | Stop only moves up |
| `test_stop_never_moves_down` | Ratchet effect |
| `test_stop_hit_detection` | Stop triggers correctly |
| `test_independent_stops_multiple_positions` | Each position independent |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_process_base_entry_signal` | Entry workflow |
| `test_portfolio_gate_blocks_excessive_risk` | Risk cap enforced |
| `test_pyramid_requires_base_position` | Pyramid prerequisites |
| `test_full_signal_sequence` | Complete sequence processing |

### End-to-End Tests

| Test | Validates |
|------|-----------|
| `test_complete_backtest_workflow` | Full backtest cycle |
| `test_portfolio_risk_cap_enforced` | 15% cap in real scenario |
| `test_cross_instrument_portfolio` | Multi-instrument coordination |
| `test_performance_with_1000_signals` | Performance at scale |

## Debugging Failed Tests

### View Detailed Output

```bash
pytest tests/unit/test_position_sizer.py::test_name -v -s
```

The `-s` flag shows print statements and logs.

### Run with Debugger

```bash
pytest tests/unit/test_position_sizer.py::test_name --pdb
```

Drops into debugger on failure.

### Check Logs

```bash
tail -f portfolio_manager.log
```

## Continuous Integration

### Pre-Commit Checklist

Before committing code:

```bash
# 1. Run all tests
pytest tests/ -v

# 2. Check coverage
pytest tests/ --cov=core --cov-report=term-missing

# 3. Verify no warnings
pytest tests/ -v --tb=short

# 4. Format code (if using black)
black core/ backtest/ live/ tests/

# 5. Lint (if using flake8)
flake8 core/ backtest/ live/
```

## Test Data

### Mock Fixtures

Located in `tests/fixtures/`:
- `mock_signals.py` - Sample signals
- Sample positions
- Mock CSV data

### Adding New Test Data

```python
# In tests/fixtures/mock_signals.py
def create_custom_signal():
    return Signal(
        timestamp=datetime(2025, 11, 15),
        instrument="GOLD_MINI",
        signal_type=SignalType.BASE_ENTRY,
        # ... your data
    )
```

## Common Test Patterns

### Testing Position Sizing

```python
def test_my_sizing_scenario():
    sizer = TomBassoPositionSizer(config)
    
    result = sizer.calculate_base_entry_size(
        signal,
        equity=5000000.0,
        available_margin=3000000.0
    )
    
    assert result.final_lots == expected_lots
    assert result.limiter == expected_limiter
```

### Testing Portfolio State

```python
def test_my_portfolio_scenario(portfolio_manager):
    # Add positions
    portfolio_manager.add_position(position1)
    portfolio_manager.add_position(position2)
    
    # Get state
    state = portfolio_manager.get_current_state()
    
    # Assert metrics
    assert state.total_risk_percent < 15.0
```

### Testing Complete Workflow

```python
def test_my_workflow():
    engine = PortfolioBacktestEngine(5000000.0)
    signals = [signal1, signal2, signal3]
    
    results = engine.run_backtest(signals)
    
    assert results['stats']['entries_executed'] > 0
```

## Troubleshooting

### Tests Fail Due to Import Errors

```bash
# Ensure you're in portfolio_manager directory
cd portfolio_manager

# Run from correct location
python -m pytest tests/ -v
```

### Coverage Report Empty

```bash
# Ensure modules are importable
python -c "from core.position_sizer import TomBassoPositionSizer"

# If fails, check PYTHONPATH or run from project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Tests Pass but Coverage Low

Check which lines are not covered:
```bash
pytest tests/ --cov=core --cov-report=term-missing
```

Add tests for uncovered lines.

## Test Metrics

### Current Test Stats

- **Total Tests:** 42
- **Unit Tests:** 31 (74%)
- **Integration Tests:** 8 (19%)
- **E2E Tests:** 3 (7%)
- **Target Coverage:** >80%

### Test Execution Time

- Unit tests: <1 second
- Integration tests: <2 seconds
- E2E tests: <5 seconds
- **Total:** <10 seconds

## Adding New Tests

### 1. Create Test File

```python
# tests/unit/test_new_component.py
import pytest
from core.new_component import NewComponent

class TestNewComponent:
    def test_functionality(self):
        component = NewComponent()
        assert component.method() == expected
```

### 2. Run New Tests

```bash
pytest tests/unit/test_new_component.py -v
```

### 3. Verify Coverage

```bash
pytest tests/unit/test_new_component.py --cov=core.new_component --cov-report=term-missing
```

## Quality Assurance

All tests verify:
- ✅ Correct calculations (math formulas)
- ✅ Edge cases (zero equity, invalid stops)
- ✅ Integration (components work together)
- ✅ Performance (handles 1000+ signals)
- ✅ Error handling (graceful failures)

Tests are **auditable** - each test has:
- Clear name describing what it tests
- Docstring explaining the scenario
- Expected values calculated and documented
- Assertions with meaningful error messages

