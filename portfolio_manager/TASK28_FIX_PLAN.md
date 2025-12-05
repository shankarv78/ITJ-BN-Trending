# Task 28: Fix Plan Based on Code Review

**Date:** 2025-12-02  
**Review Reference:** TASK28_CODE_REVIEW.md  
**Status:** Ready for Implementation

---

## Executive Summary

This fix plan addresses all issues identified in the code review, organized by priority. The fixes are designed to be implemented incrementally, allowing Phase 3 integration to proceed after high-priority items are completed.

**Total Issues:** 15  
**High Priority:** 4 (must fix before Phase 3)  
**Medium Priority:** 6 (fix before production)  
**Low Priority:** 5 (nice to have)

---

## High Priority Fixes (Must Fix Before Phase 3 Integration)

### Fix 1: MockBroker - Implement Partial Fill Logic

**File:** `tests/mocks/mock_broker.py`  
**Lines:** 149-152  
**Issue:** Partial fills never actually occur (filled_lots always 0 or full)  
**Impact:** Cannot test partial fill handling in OrderExecutor

**Implementation Plan:**

1. Add `partial_fill_probability` parameter to `__init__` (default: 0.1 = 10%)
2. Modify `place_limit_order()` to simulate partial fills:
   ```python
   # After determining fill_prob, check for partial fill
   if random.random() < fill_prob:
       # Decide: full fill or partial fill?
       if random.random() < self.partial_fill_probability:
           # Partial fill: fill 30-70% of lots
           fill_percentage = random.uniform(0.3, 0.7)
           filled_lots = int(lots * fill_percentage)
           remaining_lots = lots - filled_lots
           
           order_status = {
               'status': 'success',
               'orderid': order_id,
               'fill_status': 'PARTIAL',
               'lots': lots,
               'filled_lots': filled_lots,
               'remaining_lots': remaining_lots,
               'avg_fill_price': fill_price
           }
       else:
           # Full fill (existing logic)
   ```

3. Update `get_order_status()` to return partial fill status correctly
4. Add test in `test_mock_broker.py`:
   ```python
   def test_partial_fill_simulation(self):
       broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
       broker.partial_fill_probability = 1.0  # Force partial fills
       order = broker.place_limit_order("BANKNIFTY-I", 10, 50000, "BUY")
       assert order['fill_status'] == 'PARTIAL'
       assert 0 < order['filled_lots'] < 10
   ```

**Estimated Time:** 1 hour  
**Dependencies:** None

---

### Fix 2: SignalValidator - Inject Time Source for Testability

**File:** `core/signal_validator.py`  
**Lines:** 231, 467  
**Issue:** Hardcoded `datetime.now()` makes time-sensitive tests flaky  
**Impact:** Cannot reliably test edge cases (exactly 10s, 30s, 60s boundaries)

**Implementation Plan:**

1. Add `time_source` parameter to `__init__`:
   ```python
   def __init__(
       self,
       config: SignalValidationConfig = None,
       portfolio_manager: Optional[PortfolioStateManager] = None,
       time_source=None  # Callable that returns datetime
   ):
       self.config = config or SignalValidationConfig()
       self.portfolio_manager = portfolio_manager
       self.time_source = time_source or datetime.now
       self._validate_config()
   ```

2. Replace all `datetime.now()` calls:
   ```python
   def _validate_signal_age(self, signal_timestamp: datetime) -> ConditionValidationResult:
       current_time = self.time_source()  # Use injected time source
       age_seconds = (current_time - signal_timestamp).total_seconds()
       # ... rest unchanged
   ```

3. Update `validate_execution_price()` to use time source for age checks
4. Update tests to use mock time source:
   ```python
   def test_signal_age_exactly_at_threshold(self):
       fixed_time = datetime(2025, 12, 2, 10, 0, 0)
       time_source = lambda: fixed_time
       validator = SignalValidator(time_source=time_source)
       
       signal = Signal(
           timestamp=fixed_time - timedelta(seconds=10),  # Exactly at threshold
           # ... rest of signal
       )
       result = validator.validate_conditions_with_signal_price(signal)
       assert result.severity == ValidationSeverity.NORMAL
   ```

**Estimated Time:** 1.5 hours  
**Dependencies:** None  
**Breaking Changes:** None (backward compatible with default)

---

### Fix 3: OrderExecutor - Address Blocking I/O

**File:** `core/order_executor.py`  
**Lines:** 328, 485  
**Issue:** `time.sleep()` blocks event loop if integrated into async system  
**Impact:** Could freeze live/engine.py if it's async

**Analysis:**
- ✅ **Finding:** `live/engine.py` is **NOT async** (uses blocking I/O in `rollover_executor.py`)
- ✅ **Finding:** `rollover_executor.py` uses `time.sleep()` (line 723)
- ✅ **Conclusion:** Current blocking I/O is acceptable for Phase 3

**Implementation Plan:**

**Option A: Document as Blocking (Recommended for Phase 3)**
1. Add clear documentation that OrderExecutor is blocking:
   ```python
   class OrderExecutor(ABC):
       """
       Abstract base class for order execution strategies
       
       NOTE: This executor uses blocking I/O (time.sleep).
       It is designed for synchronous use in live/engine.py.
       If integrating into async systems, run in thread pool.
       """
   ```

2. Add comment in `execute()` methods:
   ```python
   # NOTE: This method blocks with time.sleep().
   # For async systems, wrap in asyncio.run_in_executor() or use AsyncOrderExecutor.
   ```

**Option B: Create Async Version (Future Enhancement)**
- Create `AsyncOrderExecutor` base class
- Implement `AsyncSimpleLimitExecutor` and `AsyncProgressiveExecutor`
- Use `asyncio.sleep()` instead of `time.sleep()`
- **Decision:** Defer to Phase 4 (Production Hardening)

**Recommended Action:** Implement Option A for Phase 3, document Option B for future

**Estimated Time:** 30 minutes (documentation only)  
**Dependencies:** None

---

### Fix 4: MockBroker - Add Configurable Bid/Ask Spread

**File:** `tests/mocks/mock_broker.py`  
**Lines:** 81-82  
**Issue:** Hardcoded 0.01% spread is unrealistic for Bank Nifty options  
**Impact:** Tests won't catch real-world bid/ask issues

**Implementation Plan:**

1. Add `bid_ask_spread_pct` parameter to `__init__`:
   ```python
   def __init__(
       self,
       scenario: str = "normal",
       base_price: float = 50000.0,
       bid_ask_spread_pct: float = 0.002  # 0.2% default (realistic for Bank Nifty)
   ):
       self.scenario = MarketScenario(scenario) if isinstance(scenario, str) else scenario
       self.base_price = base_price
       self.bid_ask_spread = bid_ask_spread_pct
       # ... rest unchanged
   ```

2. Update `get_quote()` to use configurable spread:
   ```python
   simulated_price = max(self.base_price * (1 + divergence), 1.0)
   
   return {
       'ltp': round(simulated_price, 2),
       'bid': round(simulated_price * (1 - self.bid_ask_spread/2), 2),
       'ask': round(simulated_price * (1 + self.bid_ask_spread/2), 2),
       'timestamp': datetime.now().isoformat()
   }
   ```

3. Add test for spread configuration:
   ```python
   def test_configurable_bid_ask_spread(self):
       broker = MockBrokerSimulator(
           scenario="normal",
           base_price=50000.0,
           bid_ask_spread_pct=0.005  # 0.5% spread
       )
       quote = broker.get_quote("BANKNIFTY-I")
       spread = (quote['ask'] - quote['bid']) / quote['ltp']
       assert abs(spread - 0.005) < 0.0001  # Within tolerance
   ```

**Estimated Time:** 45 minutes  
**Dependencies:** None

---

## Medium Priority Fixes (Fix Before Production)

### Fix 5: OrderExecutor - Add Retry Logic for Transient Errors

**File:** `core/order_executor.py`  
**Lines:** 256, 488  
**Issue:** Single network glitch causes rejection  
**Impact:** Production systems need resilience

**Implementation Plan:**

1. Create custom exception hierarchy (see Fix 8)
2. Add retry logic with exponential backoff:
   ```python
   def _place_order_with_retry(
       self,
       instrument: str,
       action: str,
       quantity: int,
       order_type: str,
       price: float,
       max_retries: int = 3
   ) -> Dict:
       """Place order with retry logic for transient errors"""
       for attempt in range(max_retries):
           try:
               return self.place_order(instrument, action, quantity, order_type, price)
           except TransientBrokerError as e:
               if attempt < max_retries - 1:
                   wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                   logger.warning(
                       f"Transient error on attempt {attempt + 1}/{max_retries}, "
                       f"retrying in {wait_time}s: {e}"
                   )
                   time.sleep(wait_time)
                   continue
               raise
           except Exception as e:
               # Non-retryable errors
               logger.error(f"Non-retryable error placing order: {e}")
               raise
       
       raise BrokerAPIError("Max retries exceeded")
   ```

3. Use in `SimpleLimitExecutor.execute()` and `ProgressiveExecutor.execute()`
4. Add tests for retry logic

**Estimated Time:** 2 hours  
**Dependencies:** Fix 8 (Custom Exceptions)

---

### Fix 6: OrderExecutor - Fix Hard Slippage Limit Logic

**File:** `core/order_executor.py`  
**Lines:** 425-441  
**Issue:** Hard slippage limit checked BEFORE order placement, preventing favorable fills  
**Impact:** Could miss fills just below limit

**Implementation Plan:**

1. Remove pre-placement slippage check:
   ```python
   # REMOVE this check:
   # if slippage_vs_signal > self.hard_slippage_limit:
   #     return ExecutionResult(status=REJECTED, ...)
   ```

2. Add post-fill slippage validation:
   ```python
   # After order fills:
   if status in ['COMPLETE', 'FILLED']:
       fill_price = status_response.get('fill_price') or attempt_price
       result = ExecutionResult(...)
       result.calculate_slippage(signal_price)
       
       # Check hard slippage limit AFTER fill
       if result.slippage_pct > self.hard_slippage_limit:
           logger.warning(
               f"Fill exceeded hard slippage limit: {result.slippage_pct:.2%} > "
               f"{self.hard_slippage_limit:.2%}, cancelling order"
           )
           self.cancel_order(order_id)
           return ExecutionResult(
               status=ExecutionStatus.REJECTED,
               rejection_reason=f"hard_slippage_limit_exceeded_{result.slippage_pct:.2%}",
               attempts=attempt_num
           )
       
       return result
   ```

3. Update tests to verify post-fill validation

**Estimated Time:** 1 hour  
**Dependencies:** None

---

### Fix 7: SignalValidator - Extract Hardcoded Point Values

**File:** `core/signal_validator.py`  
**Line:** 352  
**Issue:** Point values hardcoded (35.0 for BANK_NIFTY, 10.0 for GOLD_MINI)  
**Impact:** Breaks if adding new instruments or if lot sizes change

**Implementation Plan:**

1. Use `get_instrument_config()` from `core.config`:
   ```python
   from core.config import get_instrument_config
   from core.models import InstrumentType
   
   def _validate_instrument_pnl(self, signal, portfolio_state):
       # ... existing code ...
       
       # Get point value from config instead of hardcoding
       if signal.instrument == "BANK_NIFTY":
           inst_type = InstrumentType.BANK_NIFTY
       elif signal.instrument == "GOLD_MINI":
           inst_type = InstrumentType.GOLD_MINI
       else:
           return False, f"unknown_instrument_{signal.instrument}"
       
       inst_config = get_instrument_config(inst_type)
       point_value = inst_config.point_value
       
       for pos in instrument_positions:
           pnl = pos.calculate_pnl(signal.price, point_value)
           total_pnl += pnl
   ```

2. Update tests to verify config-based point values

**Estimated Time:** 45 minutes  
**Dependencies:** None

---

### Fix 8: Add Custom Exception Hierarchy

**File:** `core/exceptions.py` (new file)  
**Issue:** Generic exceptions make error handling difficult  
**Impact:** Cannot distinguish retryable vs non-retryable errors

**Implementation Plan:**

1. Create `core/exceptions.py`:
   ```python
   """
   Custom exception hierarchy for portfolio manager
   """
   
   class PortfolioManagerError(Exception):
       """Base exception for portfolio manager errors"""
       pass
   
   class ValidationError(PortfolioManagerError):
       """Signal validation failed"""
       pass
   
   class SignalTooOldError(ValidationError):
       """Signal exceeded age threshold"""
       def __init__(self, age_seconds: float, max_age: float):
           self.age_seconds = age_seconds
           self.max_age = max_age
           super().__init__(
               f"Signal age {age_seconds:.0f}s exceeds max {max_age:.0f}s"
           )
   
   class DivergenceTooHighError(ValidationError):
       """Price divergence exceeds threshold"""
       def __init__(self, divergence_pct: float, threshold: float):
           self.divergence_pct = divergence_pct
           self.threshold = threshold
           super().__init__(
               f"Divergence {divergence_pct:.2%} exceeds threshold {threshold:.2%}"
           )
   
   class ExecutionError(PortfolioManagerError):
       """Order execution failed"""
       pass
   
   class BrokerAPIError(ExecutionError):
       """Broker API call failed"""
       pass
   
   class TransientBrokerError(BrokerAPIError):
       """Temporary broker error (retryable)"""
       pass
   
   class OrderPlacementError(BrokerAPIError):
       """Order placement failed"""
       pass
   
   class OrderTimeoutError(ExecutionError):
       """Order execution timeout"""
       pass
   ```

2. Update `SignalValidator` to raise custom exceptions:
   ```python
   from core.exceptions import SignalTooOldError, DivergenceTooHighError
   
   def _validate_signal_age(self, signal_timestamp):
       # ... existing logic ...
       if age_seconds >= self.config.max_signal_age_stale:
           raise SignalTooOldError(age_seconds, self.config.max_signal_age_stale)
   ```

3. Update `OrderExecutor` to raise custom exceptions
4. Update tests to catch specific exceptions

**Estimated Time:** 2 hours  
**Dependencies:** None

---

### Fix 9: MockBroker - Add Random Seed Control

**File:** `tests/mocks/mock_broker.py`  
**Line:** 58  
**Issue:** Non-deterministic tests could be flaky  
**Impact:** Tests using simulator could fail randomly

**Implementation Plan:**

1. Add `_random_seed` attribute and `set_seed()` method:
   ```python
   def __init__(self, ...):
       # ... existing code ...
       self._random_seed = None
   
   def set_seed(self, seed: int):
       """Set random seed for deterministic testing"""
       self._random_seed = seed
       random.seed(seed)
   ```

2. Update tests to use fixed seeds:
   ```python
   def test_normal_scenario_quote_generation(self):
       broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)
       broker.set_seed(42)  # Deterministic
       quote = broker.get_quote("BANKNIFTY-I")
       # ... assertions ...
   ```

**Estimated Time:** 30 minutes  
**Dependencies:** None

---

### Fix 10: Tests - Add Boundary Condition Tests

**File:** `tests/unit/test_signal_validator.py`  
**Issue:** Missing tests for exact threshold boundaries  
**Impact:** Could miss off-by-one errors

**Implementation Plan:**

1. Add parametrized tests for boundary conditions:
   ```python
   @pytest.mark.parametrize("divergence_pct,expected_valid", [
       (0.0199, True),   # Just below 2% threshold
       (0.0200, True),  # Exactly at threshold
       (0.0201, False), # Just above threshold
   ])
   def test_base_entry_divergence_boundaries(self, validator, divergence_pct, expected_valid):
       signal = Signal(...)  # BASE_ENTRY signal
       broker_price = signal.price * (1 + divergence_pct)
       result = validator.validate_execution_price(signal, broker_price)
       assert result.is_valid == expected_valid
   
   @pytest.mark.parametrize("age_seconds,expected_severity", [
       (9.9, ValidationSeverity.NORMAL),
       (10.0, ValidationSeverity.WARNING),
       (29.9, ValidationSeverity.WARNING),
       (30.0, ValidationSeverity.ELEVATED),
       (59.9, ValidationSeverity.ELEVATED),
       (60.0, ValidationSeverity.REJECTED),
   ])
   def test_signal_age_boundaries(self, validator, age_seconds, expected_severity):
       fixed_time = datetime(2025, 12, 2, 10, 0, 0)
       time_source = lambda: fixed_time
       validator = SignalValidator(time_source=time_source)
       
       signal = Signal(
           timestamp=fixed_time - timedelta(seconds=age_seconds),
           # ... rest of signal
       )
       result = validator.validate_conditions_with_signal_price(signal)
       assert result.severity == expected_severity
   ```

**Estimated Time:** 1.5 hours  
**Dependencies:** Fix 2 (Time Injection)

---

## Low Priority Fixes (Nice to Have)

### Fix 11: OrderExecutor - Derive Action from Signal

**File:** `core/order_executor.py`  
**Lines:** 245, 413  
**Issue:** Hardcoded `action = "BUY"` limits future extensibility  
**Impact:** Won't work for SHORT exits if system adds shorts later

**Implementation Plan:**

1. Add method to derive action from signal:
   ```python
   def _derive_action(self, signal: Signal) -> str:
       """Derive order action from signal"""
       if signal.position.startswith("Long"):
           return "BUY"
       elif signal.position.startswith("Short"):
           return "SELL"
       elif signal.signal_type == SignalType.EXIT:
           # For exits, determine based on position direction
           # For now, assume all exits are SELL (closing long positions)
           return "SELL"
       else:
           return "BUY"  # Default to BUY for long-only system
   ```

2. Replace hardcoded `action = "BUY"` with `action = self._derive_action(signal)`

**Estimated Time:** 30 minutes  
**Dependencies:** None

---

### Fix 12: Add Structured Logging

**File:** All files  
**Issue:** Logging uses string formatting instead of structured data  
**Impact:** Harder to parse logs for monitoring/alerting

**Implementation Plan:**

1. Update logging calls to use `extra` parameter:
   ```python
   logger.info("Order filled", extra={
       'signal_type': signal.signal_type.value,
       'instrument': signal.instrument,
       'lots': filled_lots,
       'price': fill_price,
       'slippage_pct': result.slippage_pct,
       'order_id': order_id,
       'attempts': attempt_num
   })
   ```

2. Configure logging formatter to output JSON in production

**Estimated Time:** 2 hours  
**Dependencies:** None

---

### Fix 13: Add Module-Level Docstring Examples

**File:** All files  
**Issue:** No usage examples in module docstrings  
**Impact:** Harder for new developers to understand usage

**Implementation Plan:**

1. Add examples to module docstrings:
   ```python
   """
   Signal Validation System
   
   Implements two-stage validation:
   1. Condition validation (trusts TradingView signal price)
   2. Execution validation (uses broker API price)
   
   Example usage:
       >>> from core.signal_validator import SignalValidator, SignalValidationConfig
       >>> from core.models import Signal, SignalType
       >>> 
       >>> config = SignalValidationConfig(max_divergence_base_entry=0.03)
       >>> validator = SignalValidator(config=config)
       >>> 
       >>> signal = Signal(...)  # Create signal
       >>> result = validator.validate_conditions_with_signal_price(signal)
       >>> if result.is_valid:
       ...     broker_price = get_broker_price()
       ...     exec_result = validator.validate_execution_price(signal, broker_price)
   """
   ```

**Estimated Time:** 1 hour  
**Dependencies:** None

---

### Fix 14: Run mypy and Fix Type Hint Gaps

**File:** All files  
**Issue:** Some methods missing return type hints  
**Impact:** Reduced type safety

**Implementation Plan:**

1. Run mypy on all files:
   ```bash
   mypy core/signal_validator.py core/order_executor.py tests/mocks/mock_broker.py
   ```

2. Fix all type hint errors
3. Add `# type: ignore` comments only where necessary with explanations

**Estimated Time:** 2 hours  
**Dependencies:** None

---

### Fix 15: Add Circuit Breaker Pattern

**File:** `core/order_executor.py`  
**Issue:** If broker API is down, executor will keep trying  
**Impact:** Wasted resources and potential cascading failures

**Implementation Plan:**

1. Create `CircuitBreaker` class:
   ```python
   class CircuitBreaker:
       def __init__(self, failure_threshold: int = 5, timeout: int = 60):
           self.failure_threshold = failure_threshold
           self.timeout = timeout
           self.failure_count = 0
           self.last_failure_time = None
           self.state = "closed"  # closed, open, half_open
       
       def call(self, func, *args, **kwargs):
           if self.state == "open":
               if time.time() - self.last_failure_time > self.timeout:
                   self.state = "half_open"
               else:
                   raise CircuitBreakerOpenError("Circuit breaker is open")
           
           try:
               result = func(*args, **kwargs)
               if self.state == "half_open":
                   self.state = "closed"
                   self.failure_count = 0
               return result
           except Exception as e:
               self.failure_count += 1
               self.last_failure_time = time.time()
               if self.failure_count >= self.failure_threshold:
                   self.state = "open"
               raise
   ```

2. Integrate into OrderExecutor for broker API calls

**Estimated Time:** 3 hours  
**Dependencies:** Fix 8 (Custom Exceptions)

---

## Implementation Schedule

### Phase 1: High Priority (Before Phase 3 Integration)
- **Week 1:**
  - Day 1: Fix 1 (MockBroker Partial Fills) - 1 hour
  - Day 1: Fix 4 (Configurable Bid/Ask Spread) - 45 min
  - Day 1: Fix 3 (Document Blocking I/O) - 30 min
  - Day 2: Fix 2 (Time Injection) - 1.5 hours
  - **Total:** ~4 hours

### Phase 2: Medium Priority (Before Production)
- **Week 2:**
  - Day 1: Fix 8 (Custom Exceptions) - 2 hours
  - Day 1: Fix 5 (Retry Logic) - 2 hours
  - Day 2: Fix 6 (Hard Slippage Limit) - 1 hour
  - Day 2: Fix 7 (Point Values) - 45 min
  - Day 3: Fix 9 (Random Seed) - 30 min
  - Day 3: Fix 10 (Boundary Tests) - 1.5 hours
  - **Total:** ~7.5 hours

### Phase 3: Low Priority (Nice to Have)
- **Week 3:**
  - Fix 11 (Derive Action) - 30 min
  - Fix 12 (Structured Logging) - 2 hours
  - Fix 13 (Docstring Examples) - 1 hour
  - Fix 14 (Type Hints) - 2 hours
  - Fix 15 (Circuit Breaker) - 3 hours
  - **Total:** ~8.5 hours

**Grand Total:** ~20 hours

---

## Risk Assessment

### Low Risk Fixes
- Fix 1, 4, 9, 11, 13, 14: Isolated changes, minimal impact
- Fix 3: Documentation only, no code changes

### Medium Risk Fixes
- Fix 2: Changes constructor signature (backward compatible)
- Fix 6: Changes execution flow logic
- Fix 7: Changes calculation method

### High Risk Fixes
- Fix 5: Adds retry logic (could mask real errors)
- Fix 8: Changes exception types (breaking change for error handling)
- Fix 15: Adds circuit breaker (could block legitimate requests)

**Mitigation:** All fixes should be:
1. Implemented incrementally
2. Tested thoroughly
3. Reviewed before merge
4. Documented with examples

---

## Testing Strategy

### Unit Tests
- Each fix should include corresponding unit tests
- Maintain or improve existing test coverage
- Add boundary condition tests (Fix 10)

### Integration Tests
- Test fixes in combination (e.g., Fix 2 + Fix 10)
- Verify backward compatibility where applicable
- Test error paths with new exceptions (Fix 8)

### Manual Testing
- Test partial fills in MockBroker (Fix 1)
- Test time injection with various scenarios (Fix 2)
- Test retry logic with simulated failures (Fix 5)

---

## Success Criteria

### Phase 1 (High Priority)
- ✅ All 4 high-priority fixes implemented
- ✅ All existing tests pass
- ✅ New tests added for fixes
- ✅ Ready for Phase 3 integration

### Phase 2 (Medium Priority)
- ✅ All 6 medium-priority fixes implemented
- ✅ Test coverage maintained or improved
- ✅ Production-ready error handling
- ✅ No breaking changes (except Fix 8, which is intentional)

### Phase 3 (Low Priority)
- ✅ All 5 low-priority fixes implemented
- ✅ Code quality improvements verified
- ✅ Documentation complete

---

## Notes

1. **Blocking I/O Decision:** After analysis, `live/engine.py` is NOT async, so blocking I/O is acceptable. Document this clearly.

2. **Exception Hierarchy:** Fix 8 is a breaking change but necessary for proper error handling. Update all error handling code when implementing.

3. **Time Injection:** Fix 2 is critical for reliable testing. Implement before adding boundary tests (Fix 10).

4. **Partial Fills:** Fix 1 is needed to properly test OrderExecutor partial fill handling. Implement early.

5. **Priority Order:** Fixes are ordered by priority, but some can be done in parallel (e.g., Fix 1 and Fix 4).

---

## Approval

**Status:** Ready for Review  
**Next Steps:** 
1. Review this fix plan
2. Approve priority order
3. Begin implementation with Phase 1 (High Priority)
4. Schedule Phase 2 after Phase 3 integration
5. Schedule Phase 3 for production hardening

---

**End of Fix Plan**

