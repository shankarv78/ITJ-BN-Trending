# Task #27: Next Steps Plan

**Date:** November 30, 2025  
**Status:** Integration Complete - Test Fixes Applied  
**Based on:** `TASK27_INTEGRATION_REVIEW.md`

---

## ✅ Completed Actions

1. **Integration Tests Fixed** ✅
   - Updated `test_persistence.py::TestRecoveryFlow` (2 tests)
   - Added explicit `CrashRecoveryManager.load_state()` calls
   - Tests now use new recovery approach

---

## 🚀 Immediate Next Steps (Priority Order)

### Step 1: Verify Test Fixes (5 minutes) ⚠️ CRITICAL

**Action:** Run the fixed integration tests

```bash
# Run the specific test class
pytest tests/integration/test_persistence.py::TestRecoveryFlow -v

# Expected result: 2/2 tests PASS ✅
```

**Success Criteria:**
- ✅ `test_recovery_loads_positions` passes
- ✅ `test_recovery_allows_continued_trading` passes

**If tests fail:**
- Check error messages
- Verify database is running
- Check test database setup

---

### Step 2: Run All Tests (10 minutes) ⚠️ CRITICAL

**Action:** Run complete test suite

```bash
# Run all unit tests
pytest tests/unit/test_crash_recovery.py -v

# Run all integration tests
pytest tests/integration/ -v

# Run everything with coverage
pytest tests/ -v --cov=live.recovery --cov-report=term-missing
```

**Success Criteria:**
- ✅ All unit tests pass (15/15)
- ✅ All integration tests pass (including fixed tests)
- ✅ Coverage > 90% for `live/recovery.py`

---

### Step 3: Create Comprehensive Integration Test (30 minutes) 🔥 HIGH PRIORITY

**File:** `tests/integration/test_crash_recovery_integration.py`

**Test Cases to Add:**

1. **Full Recovery Flow with Signal Processing**
   ```python
   def test_full_recovery_with_signal_processing(test_db, mock_openalgo):
       """Test that recovered state allows continued signal processing"""
       # 1. Create engine, process signal, save state
       # 2. Simulate crash - create new engine
       # 3. Explicit recovery
       # 4. Process pyramid signal with recovered engine
       # 5. Verify both positions exist
   ```

2. **Recovery with Multiple Positions**
   ```python
   def test_recovery_with_multiple_positions(test_db, mock_openalgo):
       """Test recovery with 3+ positions (base + pyramids)"""
       # Create multiple positions
       # Recover
       # Verify all positions restored
   ```

3. **Recovery Failure Scenarios**
   ```python
   def test_recovery_validation_failure(test_db, mock_openalgo):
       """Test recovery halts on validation failure"""
       # Corrupt database state
       # Attempt recovery
       # Verify recovery fails with VALIDATION_FAILED
   ```

4. **HA Integration Test**
   ```python
   def test_recovery_with_coordinator(test_db, mock_openalgo):
       """Test recovery updates instance status in HA system"""
       # Create coordinator
       # Run recovery
       # Verify status: recovering → active
   ```

**Reference:** See `TASK27_INTEGRATION_REVIEW.md` Section 7.1 for detailed examples

---

### Step 4: Manual Testing (1 hour) 🔥 HIGH PRIORITY

**Test all 4 scenarios from review document:**

#### Scenario 1: Normal Recovery
```bash
# Terminal 1: Start application
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json

# Send BASE_ENTRY webhook signal
# Kill application (Ctrl+C)

# Terminal 1: Restart application
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json

# Expected logs:
# "Fetched 1 open positions from database"
# "✅ Crash recovery completed successfully - state restored"

# Send PYRAMID webhook signal
# Expected: Pyramid executed successfully
```

#### Scenario 2: Database Unavailable
```bash
# Stop PostgreSQL
sudo service postgresql stop

# Start application
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json

# Expected logs:
# "Failed to fetch state data after 3 attempts"
# "Database unavailable - starting with empty state"
# "⚠️  WARNING: If positions exist in database, they will not be tracked"

# Application should START (not halt)
```

#### Scenario 3: State Corruption
```sql
-- Manually corrupt data in database
UPDATE portfolio_state SET total_risk_amount = 999999.99;
```

```bash
# Start application
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json

# Expected logs:
# "Risk amount mismatch: DB=999999.99, Calculated=100000.00"
# "🚨 CRITICAL: State corruption detected - HALTING STARTUP"

# Application should EXIT (exit code 1)
```

#### Scenario 4: HA Recovery
```bash
# Terminal 1: Start instance A with HA
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json \
  --redis-config redis_config.json

# Terminal 2: Start instance B with HA
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json \
  --redis-config redis_config.json

# Terminal 1: Send signal, kill instance A
# Terminal 1: Restart instance A

# Expected logs:
# "Instance status set to 'recovering' in HA system"
# "Loaded 1 open positions from database"
# "✅ Crash recovery completed successfully"
# "Instance status set to 'active' in HA system - ready for leader election"
```

**Reference:** See `TASK27_INTEGRATION_REVIEW.md` Section 7.2 for detailed scenarios

---

## 📋 Pre-Deployment Checklist

### Before Merge to Main Branch

- [x] **Integration tests fixed** ✅
- [ ] **All tests passing** (pytest tests/ -v)
- [ ] **Comprehensive integration test created**
- [ ] **Manual testing completed** (all 4 scenarios)
- [ ] **Code review completed** (already done in review doc)

### Before Production Deployment

- [ ] **Load testing** - Test recovery with 10+ positions
- [ ] **Performance testing** - Measure recovery time (target: < 5 seconds)
- [ ] **Documentation updated**
  - [ ] Update `ARCHITECTURE.md` - Add recovery section
  - [ ] Update `README.md` - Document `--redis-config` argument
  - [ ] Create `RUNBOOK.md` - Recovery failure procedures
- [ ] **Monitoring setup**
  - [ ] Add recovery metrics to dashboard
  - [ ] Configure alerts for validation failures
  - [ ] Configure alerts for DB_UNAVAILABLE events

---

## 📊 Test Execution Plan

### Phase 1: Verify Fixes (15 minutes)

```bash
# 1. Run fixed integration tests
pytest tests/integration/test_persistence.py::TestRecoveryFlow -v

# 2. Run all crash recovery unit tests
pytest tests/unit/test_crash_recovery.py -v

# 3. Run all integration tests
pytest tests/integration/ -v
```

**Expected:** All tests pass ✅

### Phase 2: Add New Tests (30 minutes)

```bash
# Create new integration test file
touch tests/integration/test_crash_recovery_integration.py

# Add test cases (see Step 3 above)

# Run new tests
pytest tests/integration/test_crash_recovery_integration.py -v
```

**Expected:** All new tests pass ✅

### Phase 3: Full Test Suite (5 minutes)

```bash
# Run everything with coverage
pytest tests/ -v --cov=live.recovery --cov-report=html

# View coverage report
open htmlcov/index.html
```

**Target:** > 90% coverage for `live/recovery.py`

---

## 🎯 Success Metrics

### Code Quality
- ✅ All tests passing (unit + integration)
- ✅ Code coverage > 90%
- ✅ No linter errors
- ✅ No type errors

### Functionality
- ✅ Recovery loads positions correctly
- ✅ Recovery restores pyramiding state
- ✅ Recovery validates consistency
- ✅ Recovery handles all error codes
- ✅ Recovery integrates with HA system

### Production Readiness
- ✅ Manual testing completed
- ✅ Performance acceptable (< 5s recovery)
- ✅ Documentation updated
- ✅ Monitoring configured

---

## ⚠️ Known Issues & Risks

### Low Risk Issues

1. **Coordinator dependency** (Lines 100, 145 in recovery.py)
   - Uses `hasattr()` check for `_get_hostname_safe()`
   - **Impact:** LOW - Works correctly, but couples to internal API
   - **Fix:** Add public method to RedisCoordinator (nice-to-have)

2. **Missing test scenarios**
   - Invalid pyramiding_state values
   - Recovery with closed positions
   - **Impact:** LOW - Edge cases, covered by validation
   - **Fix:** Add tests in Phase 2

### Mitigation

- All critical paths tested
- Error handling comprehensive
- Fail-safe defaults (halt on corruption)
- Clear logging for debugging

---

## 📝 Documentation Updates Needed

### 1. ARCHITECTURE.md

Add section:
```markdown
## Crash Recovery System

The application uses `CrashRecoveryManager` to restore state from PostgreSQL on startup.

**Recovery Process:**
1. Fetch all open positions
2. Fetch portfolio state (closed_equity, risk, margin)
3. Fetch pyramiding state
4. Reconstruct PortfolioStateManager
5. Reconstruct LiveTradingEngine
6. Validate consistency
7. Set instance status to 'active'

**Error Handling:**
- VALIDATION_FAILED → Halt startup
- DATA_CORRUPT → Halt startup
- DB_UNAVAILABLE → Continue with warning
```

### 2. README.md

Update usage section:
```markdown
# With database persistence and HA
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_KEY \
  --db-config database_config.json \
  --redis-config redis_config.json
```

### 3. RUNBOOK.md (New File)

Add recovery failure procedures:
```markdown
## Recovery Failure Procedures

### VALIDATION_FAILED
1. Check logs for mismatch details
2. Review database state manually
3. Fix data corruption
4. Restart application

### DATA_CORRUPT
1. Check logs for corruption details
2. Restore from database backup
3. Verify data integrity
4. Restart application

### DB_UNAVAILABLE
1. Check PostgreSQL service status
2. Verify network connectivity
3. Check database credentials
4. Restart PostgreSQL if needed
5. Restart application
```

---

## 🚀 Deployment Plan

### Pre-Deployment

1. **Database Backup**
   ```bash
   pg_dump -U pm_user portfolio_manager > backup_$(date +%Y%m%d).sql
   ```

2. **Verify Rollback Plan**
   - Previous version available
   - Database backup ready
   - Rollback procedure documented

### Deployment

1. **Rolling Deployment**
   - Deploy to one instance first
   - Monitor logs for recovery errors
   - Verify recovery works
   - Deploy to remaining instances

2. **Monitoring**
   - Watch recovery logs
   - Monitor recovery duration
   - Alert on validation failures
   - Alert on DB_UNAVAILABLE events

### Post-Deployment

1. **Verification**
   - Test recovery on one instance
   - Verify HA recovery works
   - Check monitoring dashboards

2. **Documentation**
   - Update deployment notes
   - Record any issues
   - Update runbook if needed

---

## 📞 Support & Escalation

### If Tests Fail

1. Check error messages
2. Verify database setup
3. Check test fixtures
4. Review recent changes

### If Recovery Fails in Production

1. **Immediate:** Check logs for error code
2. **VALIDATION_FAILED/DATA_CORRUPT:** Halt all instances, investigate
3. **DB_UNAVAILABLE:** Check PostgreSQL, continue with warning
4. **Escalate:** Contact database team if needed

---

## ✅ Final Checklist

Before marking Task #27 as complete:

- [x] Integration tests fixed ✅
- [ ] All tests passing
- [ ] Comprehensive integration test created
- [ ] Manual testing completed
- [ ] Documentation updated
- [ ] Performance tested
- [ ] Monitoring configured
- [ ] Deployment plan ready

---

**Next Review:** After test execution and manual testing complete

**Status:** Ready for test execution phase

