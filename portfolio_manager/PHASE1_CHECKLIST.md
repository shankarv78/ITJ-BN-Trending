# Phase 1: Database Schema + Basic Persistence - Implementation Checklist

**Duration:** Week 1  
**Goal:** Implement PostgreSQL persistence layer with basic CRUD operations for positions and portfolio state

---

## Prerequisites

### 1. Environment Setup

- [ ] **PostgreSQL Installation**
  - [ ] Install PostgreSQL 14+ (local or Docker)
  - [ ] Create database: `portfolio_manager`
  - [ ] Create user: `pm_user` with password
  - [ ] Grant privileges: `GRANT ALL ON DATABASE portfolio_manager TO pm_user;`
  - [ ] Verify connection: `psql -U pm_user -d portfolio_manager -c "SELECT version();"`

- [ ] **Python Dependencies**
  - [ ] Add `psycopg2-binary>=2.9.9` to `requirements.txt`
  - [ ] Install: `pip install -r requirements.txt`
  - [ ] Verify: `python -c "import psycopg2; print(psycopg2.__version__)"`

- [ ] **Configuration**
  - [ ] Create `database_config.json` (local and production configs)
  - [ ] Add database config to `core/config.py` (or separate config loader)

---

## Task 1: Update Position Model

**File:** `core/models.py`

- [ ] **Add `is_base_position` field**
  ```python
  is_base_position: bool = False  # TRUE for base entry, FALSE for pyramids
  ```
  - [ ] Add to `Position` dataclass (after `limiter` field, line ~205)
  - [ ] Update `__post_init__` if needed (no validation required)
  - [ ] Verify: Run existing tests to ensure no breakage

**Verification:**
```bash
python -m pytest tests/unit/test_position_sizer.py -v
```

---

## Task 2: Create Database Schema

**File:** `migrations/001_initial_schema.sql` (NEW)

- [ ] **Create migrations directory**
  ```bash
  mkdir -p portfolio_manager/migrations
  touch portfolio_manager/migrations/__init__.py
  ```

- [ ] **Create schema file with 5 tables:**
  - [ ] **Table 1: `portfolio_positions`**
    - [ ] All fields from plan (lines 184-251)
    - [ ] Primary key: `position_id`
    - [ ] All 5 indexes (lines 246-250)
    - [ ] Constraints: `CHECK (status IN ('open', 'closed', 'partial'))`
    - [ ] Constraints: `CHECK (rollover_status IN ('none', 'pending', 'in_progress', 'rolled', 'failed'))`
  
  - [ ] **Table 2: `portfolio_state`**
    - [ ] Single-row table (lines 258-276)
    - [ ] Constraint: `CHECK (id = 1)`
    - [ ] Initial row insert (id=1, initial_capital=5000000.0, closed_equity=5000000.0)
  
  - [ ] **Table 3: `pyramiding_state`**
    - [ ] Primary key: `instrument` (lines 284-292)
    - [ ] Nullable `base_position_id` with `ON DELETE SET NULL`
  
  - [ ] **Table 4: `signal_log`**
    - [ ] All fields (lines 300-325)
    - [ ] Unique constraint on `fingerprint`
    - [ ] All 3 indexes (lines 322-324)
    - [ ] Cleanup function (lines 328-332)
  
  - [ ] **Table 5: `instance_metadata`**
    - [ ] All fields (lines 340-364)
    - [ ] Index on `last_heartbeat`

**Verification:**
```bash
# Run migration
psql -U pm_user -d portfolio_manager -f migrations/001_initial_schema.sql

# Verify tables exist
psql -U pm_user -d portfolio_manager -c "\dt"

# Verify indexes
psql -U pm_user -d portfolio_manager -c "\di"
```

---

## Task 3: Implement DatabaseStateManager

**File:** `core/db_state_manager.py` (NEW)

- [ ] **Create file structure**
  ```bash
  touch portfolio_manager/core/db_state_manager.py
  ```

- [ ] **Implement core class:**
  - [ ] **`__init__` method**
    - [ ] Connection pool initialization (lines 402-425)
    - [ ] L1 cache initialization (lines 428-429)
    - [ ] Connection retry logic (from Section 11, lines 1576-1606)
    - [ ] Error handling for connection failures
  
  - [ ] **Connection management:**
    - [ ] `get_connection()` context manager (lines 433-440)
    - [ ] `transaction()` context manager (lines 442-452)
    - [ ] Transaction retry logic (lines 1616-1640)
  
  - [ ] **Position operations:**
    - [ ] `save_position(position: Position) -> bool` (lines 456-505)
      - [ ] Upsert with `ON CONFLICT`
      - [ ] Optimistic locking (version increment)
      - [ ] Cache update
    - [ ] `get_position(position_id: str) -> Optional[Position]` (lines 507-527)
      - [ ] Cache-first lookup
      - [ ] Database fallback
      - [ ] Cache update on fetch
    - [ ] `get_all_open_positions() -> Dict[str, Position]` (lines 529-545)
      - [ ] Query with `status = 'open'`
      - [ ] Cache all loaded positions
  
  - [ ] **Portfolio state operations:**
    - [ ] `save_portfolio_state(state: PortfolioState) -> bool` (lines 549-573)
      - [ ] Single-row upsert
      - [ ] Version increment
    - [ ] `get_portfolio_state() -> Optional[dict]` (lines 575-591)
      - [ ] Cache-first lookup
  
  - [ ] **Pyramiding state operations:**
    - [ ] `save_pyramiding_state(...)` (lines 595-607)
    - [ ] `get_pyramiding_state() -> Dict[str, dict]` (lines 609-620)
  
  - [ ] **Signal deduplication:**
    - [ ] `check_duplicate_signal(fingerprint: str) -> bool` (lines 624-635)
    - [ ] `log_signal(...)` (lines 637-659)
  
  - [ ] **Helper methods:**
    - [ ] `_position_to_dict(position: Position) -> dict` (lines 663-700)
      - [ ] Include `is_base_position` field
      - [ ] Handle all optional fields (None → NULL)
    - [ ] `_dict_to_position(row: dict) -> Position` (lines 702-740)
      - [ ] Include `is_base_position` field
      - [ ] Handle NULL values (None for optional fields)
      - [ ] Type conversions (DECIMAL → float, TIMESTAMP → datetime)

**Verification:**
```bash
# Syntax check
python -m py_compile core/db_state_manager.py

# Import check
python -c "from core.db_state_manager import DatabaseStateManager; print('OK')"
```

---

## Task 4: Create Unit Tests for DatabaseStateManager

**File:** `tests/unit/test_db_state_manager.py` (NEW)

- [ ] **Test setup:**
  - [ ] Test database creation (separate test DB)
  - [ ] Fixtures for connection config
  - [ ] Fixtures for sample positions
  - [ ] Cleanup after each test (DROP/CREATE tables)

- [ ] **Connection tests:**
  - [ ] `test_connection_pool_initialization`
  - [ ] `test_connection_retry_on_failure`
  - [ ] `test_transaction_rollback_on_error`

- [ ] **Position CRUD tests:**
  - [ ] `test_save_position_insert`
  - [ ] `test_save_position_update`
  - [ ] `test_save_position_optimistic_locking`
  - [ ] `test_get_position_cache_hit`
  - [ ] `test_get_position_cache_miss`
  - [ ] `test_get_all_open_positions`
  - [ ] `test_position_serialization_is_base_position`

- [ ] **Portfolio state tests:**
  - [ ] `test_save_portfolio_state`
  - [ ] `test_get_portfolio_state`
  - [ ] `test_portfolio_state_version_increment`

- [ ] **Pyramiding state tests:**
  - [ ] `test_save_pyramiding_state`
  - [ ] `test_get_pyramiding_state`
  - [ ] `test_base_position_id_nullable`

- [ ] **Signal deduplication tests:**
  - [ ] `test_check_duplicate_signal_exists`
  - [ ] `test_check_duplicate_signal_not_exists`
  - [ ] `test_log_signal_insert`
  - [ ] `test_log_signal_duplicate_detection`

**Verification:**
```bash
python -m pytest tests/unit/test_db_state_manager.py -v --cov=core.db_state_manager
```

**Target Coverage:** >90%

---

## Task 5: Integrate with PortfolioStateManager

**File:** `core/portfolio_state.py`

- [ ] **Add database integration:**
  - [ ] Import `DatabaseStateManager`
  - [ ] Add `db_manager: Optional[DatabaseStateManager] = None` parameter to `__init__`
  - [ ] Load `closed_equity` from database on initialization (if `db_manager` provided)
  - [ ] Save `closed_equity` to database when positions close
  - [ ] Optional: Save portfolio state snapshots periodically

- [ ] **Update `close_position` method:**
  ```python
  def close_position(self, position_id: str, exit_price: float, 
                     exit_timestamp: datetime, reason: str) -> float:
      # ... existing logic ...
      
      # Save closed_equity to database
      if self.db_manager:
          portfolio_state = PortfolioState(
              initial_capital=self.initial_capital,
              closed_equity=self.closed_equity,
              # ... other fields ...
          )
          self.db_manager.save_portfolio_state(portfolio_state)
  ```

- [ ] **Update `update_unrealized_pnl` method:**
  - [ ] Optionally save portfolio state after P&L updates (if needed)

**Verification:**
```bash
# Run existing portfolio state tests
python -m pytest tests/unit/test_portfolio_state.py -v

# Ensure no regressions
python -m pytest tests/ -v
```

---

## Task 6: Integrate with LiveTradingEngine

**File:** `live/engine.py`

- [ ] **Add database manager initialization:**
  - [ ] Import `DatabaseStateManager`
  - [ ] Add `db_manager: Optional[DatabaseStateManager] = None` to `__init__`
  - [ ] Load state from database on startup (if `db_manager` provided):
    - [ ] Load all open positions: `self.positions = db_manager.get_all_open_positions()`
    - [ ] Load pyramiding state: `self.last_pyramid_price`, `self.base_positions`
    - [ ] Load portfolio state: `closed_equity`

- [ ] **Add persistence calls:**
  - [ ] **In `_handle_base_entry_live`:**
    - [ ] After position created: `db_manager.save_position(position)`
    - [ ] Update pyramiding state: `db_manager.save_pyramiding_state(...)`
  
  - [ ] **In `_handle_pyramid_live`:**
    - [ ] After position created: `db_manager.save_position(position)`
    - [ ] Update pyramiding state: `db_manager.save_pyramiding_state(...)`
  
  - [ ] **In `_handle_exit_live`:**
    - [ ] After position closed: `db_manager.save_position(position)` (status='closed')
    - [ ] Update portfolio state: `db_manager.save_portfolio_state(...)`
  
  - [ ] **In `update_stops` (if exists) or stop update methods:**
    - [ ] After stop updated: `db_manager.save_position(position)`

- [ ] **Update `base_positions` tracking:**
  - [ ] Set `position.is_base_position = True` for base entries
  - [ ] Set `position.is_base_position = False` for pyramids

**Verification:**
```bash
# Run existing live engine tests
python -m pytest tests/integration/ -v

# Manual test: Start engine, process signal, verify database
```

---

## Task 7: Update Main Application

**File:** `portfolio_manager.py`

- [ ] **Add database initialization:**
  - [ ] Import `DatabaseStateManager`
  - [ ] Load database config from `database_config.json` or environment
  - [ ] Initialize `DatabaseStateManager` in `main()` function
  - [ ] Pass `db_manager` to `LiveTradingEngine` and `PortfolioStateManager`

- [ ] **Add command-line flag:**
  ```python
  parser.add_argument('--db-config', type=str, 
                      help='Path to database config JSON file')
  ```

- [ ] **Optional: Add database status endpoint:**
  ```python
  @app.route('/db/status', methods=['GET'])
  def db_status():
      # Check database connection
      # Return status
  ```

**Verification:**
```bash
# Start application
python portfolio_manager.py live --db-config database_config.json

# Verify database connection in logs
# Check /db/status endpoint (if added)
```

---

## Task 8: Integration Tests

**File:** `tests/integration/test_persistence.py` (NEW)

- [ ] **Test: Signal → Database → Recovery**
  - [ ] Process BASE_ENTRY signal
  - [ ] Verify position in database
  - [ ] Restart engine
  - [ ] Verify position loaded from database
  - [ ] Verify state matches (entry_price, lots, etc.)

- [ ] **Test: Full Signal Sequence**
  - [ ] BASE_ENTRY → PYRAMID → EXIT
  - [ ] Verify all positions persisted
  - [ ] Verify portfolio state updated
  - [ ] Verify pyramiding state updated

- [ ] **Test: Crash Recovery**
  - [ ] Create position
  - [ ] Simulate crash (kill process)
  - [ ] Restart engine
  - [ ] Verify position recovered
  - [ ] Verify can continue trading

- [ ] **Test: Concurrent Updates**
  - [ ] Update position stop from two threads
  - [ ] Verify optimistic locking prevents conflicts
  - [ ] Verify version increments

**Verification:**
```bash
python -m pytest tests/integration/test_persistence.py -v
```

---

## Task 9: Documentation

- [ ] **Update README.md:**
  - [ ] Add database setup instructions
  - [ ] Add database configuration section
  - [ ] Add migration instructions

- [ ] **Create `DATABASE_SETUP.md`:**
  - [ ] PostgreSQL installation (local/Docker)
  - [ ] Database creation steps
  - [ ] Migration execution
  - [ ] Connection troubleshooting

- [ ] **Update `ARCHITECTURE.md`:**
  - [ ] Add database persistence layer diagram
  - [ ] Document database schema
  - [ ] Document recovery flow

---

## Task 10: Final Verification

### Functional Tests

- [ ] **Manual Test 1: Fresh Start**
  ```bash
  # 1. Create fresh database
  psql -U pm_user -d portfolio_manager -f migrations/001_initial_schema.sql
  
  # 2. Start portfolio manager
  python portfolio_manager.py live --db-config database_config.json
  
  # 3. Send test webhook (BASE_ENTRY)
  # 4. Verify position in database
  psql -U pm_user -d portfolio_manager -c "SELECT * FROM portfolio_positions;"
  ```

- [ ] **Manual Test 2: Recovery**
  ```bash
  # 1. Create position (from Test 1)
  # 2. Stop portfolio manager (Ctrl+C)
  # 3. Restart portfolio manager
  # 4. Verify position loaded from database
  # 5. Verify can process new signals
  ```

- [ ] **Manual Test 3: Full Sequence**
  ```bash
  # 1. BASE_ENTRY → verify in DB
  # 2. PYRAMID → verify in DB
  # 3. EXIT → verify status='closed' in DB
  # 4. Verify portfolio_state.closed_equity updated
  ```

### Performance Tests

- [ ] **Test: Position Save Latency**
  - [ ] Measure `save_position()` time (target: <50ms)
  - [ ] Measure `get_position()` time (target: <10ms with cache)

- [ ] **Test: Concurrent Writes**
  - [ ] 10 concurrent position saves
  - [ ] Verify no deadlocks
  - [ ] Verify all positions saved

### Code Quality

- [ ] **Linting:**
  ```bash
  flake8 core/db_state_manager.py --max-line-length=120
  ```

- [ ] **Type Checking:**
  ```bash
  mypy core/db_state_manager.py --ignore-missing-imports
  ```

- [ ] **Test Coverage:**
  ```bash
  python -m pytest tests/ --cov=core.db_state_manager --cov-report=html
  # Target: >90% coverage
  ```

---

## Deliverables Checklist

### Code Files

- [ ] `core/db_state_manager.py` (NEW)
- [ ] `migrations/001_initial_schema.sql` (NEW)
- [ ] `tests/unit/test_db_state_manager.py` (NEW)
- [ ] `tests/integration/test_persistence.py` (NEW)
- [ ] `core/models.py` (MODIFIED - added `is_base_position`)
- [ ] `core/portfolio_state.py` (MODIFIED - database hooks)
- [ ] `live/engine.py` (MODIFIED - persistence calls)
- [ ] `portfolio_manager.py` (MODIFIED - database initialization)

### Configuration Files

- [ ] `database_config.json` (NEW)
- [ ] `requirements.txt` (MODIFIED - added psycopg2-binary)

### Documentation

- [ ] `DATABASE_SETUP.md` (NEW)
- [ ] `README.md` (MODIFIED - database setup section)
- [ ] `ARCHITECTURE.md` (MODIFIED - persistence layer)

---

## Success Criteria

### Must Have (Phase 1 Complete)

- [ ] ✅ All 5 database tables created
- [ ] ✅ DatabaseStateManager fully implemented
- [ ] ✅ Position CRUD operations working
- [ ] ✅ Portfolio state persistence working
- [ ] ✅ Pyramiding state persistence working
- [ ] ✅ Integration with LiveTradingEngine complete
- [ ] ✅ Recovery on startup working
- [ ] ✅ Unit tests passing (>90% coverage)
- [ ] ✅ Integration tests passing
- [ ] ✅ Manual verification successful

### Nice to Have (Can Defer)

- [ ] ⚪ Statistics persistence (Phase 2)
- [ ] ⚪ Signal log cleanup job (Phase 2)
- [ ] ⚪ Database connection monitoring (Phase 2)
- [ ] ⚪ Read replica support (Phase 3+)

---

## Risk Mitigation

### Potential Issues

1. **Database Connection Failures**
   - ✅ Mitigation: Retry logic with exponential backoff (implemented)

2. **Schema Migration Conflicts**
   - ✅ Mitigation: Use versioned migrations, test on clean DB first

3. **Performance Issues**
   - ✅ Mitigation: L1 cache, connection pooling, indexes

4. **Data Type Mismatches**
   - ✅ Mitigation: Comprehensive serialization/deserialization tests

5. **Concurrent Update Conflicts**
   - ✅ Mitigation: Optimistic locking with version field

---

## Timeline Estimate

| Task | Estimated Time | Dependencies |
|------|---------------|--------------|
| 1. Update Position Model | 30 min | None |
| 2. Create Database Schema | 2 hours | PostgreSQL setup |
| 3. Implement DatabaseStateManager | 8 hours | Task 2 |
| 4. Unit Tests | 4 hours | Task 3 |
| 5. Integrate PortfolioStateManager | 2 hours | Task 3 |
| 6. Integrate LiveTradingEngine | 3 hours | Task 3, 5 |
| 7. Update Main Application | 1 hour | Task 3 |
| 8. Integration Tests | 3 hours | Task 3-7 |
| 9. Documentation | 2 hours | All tasks |
| 10. Final Verification | 2 hours | All tasks |

**Total Estimated Time:** ~27 hours (3-4 days)

---

## Next Steps After Phase 1

Once Phase 1 is complete and verified:

1. ✅ **Code Review** - Review all changes
2. ✅ **Merge to Main** - Merge Phase 1 branch
3. → **Phase 2** - Redis Coordination (Week 2)

---

## Notes

- **Database Choice:** Using PostgreSQL for all environments (local + production)
- **Migration Strategy:** Manual SQL migrations (can add Alembic later)
- **Testing Strategy:** Test database separate from production
- **Backward Compatibility:** Existing in-memory code remains (dual-write during transition)

---

**Status:** Ready for Implementation  
**Last Updated:** November 28, 2025

