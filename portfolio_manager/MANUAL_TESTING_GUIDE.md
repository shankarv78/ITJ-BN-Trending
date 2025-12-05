# Manual Testing Guide - CrashRecoveryManager

**Date:** November 30, 2025
**Purpose:** Manual verification of crash recovery functionality
**Status:** Ready for execution

---

## Prerequisites

✅ **Verified:**
- PostgreSQL database running and accessible
- Database tables created (portfolio_positions, portfolio_state, etc.)
- `database_config.json` configured
- Python 3.13.3 installed
- Application runs without errors

---

## Test Scenario 1: Normal Recovery Flow

**Objective:** Verify crash recovery works with normal signal processing
**Time:** 15 minutes
**Priority:** HIGH

### Step 1: Start Application

```bash
# Terminal 1
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager

python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
📊 Loading state from database...
✅ Crash recovery completed successfully - state restored
🚀 Webhook server starting on port 5000...
```

### Step 2: Send BASE_ENTRY Signal

```bash
# Terminal 2
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 50000,
    "stop": 49500,
    "lots": 5,
    "atr": 300,
    "er": 0.85,
    "supertrend": 49500,
    "timestamp": "2025-11-30T10:00:00Z"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "position_id": "BANKNIFTY_123...",
  "lots": 12,
  "risk_amount": 100000.0
}
```

### Step 3: Verify Position in Database

```bash
# Terminal 3
psql -U pm_user -d portfolio_manager -c \
  "SELECT position_id, instrument, entry_price, lots, status FROM portfolio_positions;"
```

**Expected Output:**
```
 position_id     | instrument  | entry_price | lots | status
-----------------+-------------+-------------+------+--------
 BANKNIFTY_123   | BANKNIFTY   |   50000.00  |  12  | open
```

### Step 4: Crash Simulation (Kill Application)

```bash
# Terminal 1: Press Ctrl+C to kill the application
^C
```

**Expected Output:**
```
Received SIGINT, shutting down...
Server stopped.
```

### Step 5: Restart Application

```bash
# Terminal 1: Restart the application
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
📊 Loading state from database...
🔄 Fetched 1 open positions from database
✅ Crash recovery completed successfully - state restored
📈 Recovered state: 1 positions, ₹50,00,000 equity
🚀 Webhook server starting on port 5000...
```

### Step 6: Send PYRAMID Signal

```bash
# Terminal 2
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "PYRAMID",
    "instrument": "BANK_NIFTY",
    "position": "Long_2",
    "price": 50300,
    "stop": 49800,
    "lots": 3,
    "atr": 300,
    "er": 0.90,
    "supertrend": 49800,
    "timestamp": "2025-11-30T10:30:00Z"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "position_id": "BANKNIFTY_123_PYR_1",
  "lots": 6,
  "message": "Pyramid added to existing position"
}
```

### Step 7: Verification Checklist

- [ ] Application started successfully after crash
- [ ] Recovery logs show "Fetched 1 open positions from database"
- [ ] Recovery logs show "✅ Crash recovery completed successfully"
- [ ] Pyramid signal processed successfully
- [ ] Database shows 2 positions (1 base + 1 pyramid)

**✅ PASS / ❌ FAIL:** __________

**Notes:**
```


```

---

## Test Scenario 2: Database Unavailable

**Objective:** Verify graceful handling when PostgreSQL is unavailable
**Time:** 10 minutes
**Priority:** HIGH

### Step 1: Stop PostgreSQL

```bash
# macOS
brew services stop postgresql@14

# OR Linux
sudo systemctl stop postgresql
```

**Verification:**
```bash
psql -U pm_user -d portfolio_manager -c "SELECT 1;"
# Should fail with: connection refused
```

### Step 2: Start Application (DB Down)

```bash
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
❌ Database connection failed: could not connect to server
🔄 Retrying database connection (attempt 1/3)...
🔄 Retrying database connection (attempt 2/3)...
🔄 Retrying database connection (attempt 3/3)...
⚠️  WARNING: Database unavailable - starting with empty state
⚠️  WARNING: If positions exist in database, they will not be tracked
🚀 Webhook server starting on port 5000...
```

### Step 3: Verify Application Continues Running

```bash
# Application should NOT halt
# Webhook server should be accessible
curl http://localhost:5002/health
```

**Expected Response:**
```json
{
  "status": "degraded",
  "database": false,
  "recovery": false
}
```

### Step 4: Restart PostgreSQL

```bash
# macOS
brew services start postgresql@14

# OR Linux
sudo systemctl start postgresql
```

### Step 5: Restart Application (DB Up)

```bash
# Ctrl+C to stop app, then restart
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
📊 Loading state from database...
✅ Crash recovery completed successfully - state restored
🚀 Webhook server starting on port 5000...
```

### Step 6: Verification Checklist

- [ ] Application starts despite database unavailable
- [ ] Warning logs show "Database unavailable - starting with empty state"
- [ ] Application does NOT crash or exit
- [ ] Health endpoint returns degraded status
- [ ] After DB restart, normal recovery works

**✅ PASS / ❌ FAIL:** __________

**Notes:**
```


```

---

## Test Scenario 3: State Corruption Detection

**Objective:** Verify application halts on corrupted database state
**Time:** 15 minutes
**Priority:** CRITICAL (Financial Safety)

### Step 1: Create Valid Position

```bash
# Start application
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY

# Send signal
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 50000,
    "stop": 49500,
    "lots": 5,
    "atr": 300,
    "er": 0.85,
    "supertrend": 49500,
    "timestamp": "2025-11-30T11:00:00Z"
  }'

# Verify position created
psql -U pm_user -d portfolio_manager -c \
  "SELECT position_id, entry_price, lots FROM portfolio_positions;"
```

### Step 2: Corrupt Database State

```bash
# Manually corrupt the total_risk_amount
psql -U pm_user -d portfolio_manager -c \
  "UPDATE portfolio_state SET total_risk_amount = 999999.99 WHERE id = 1;"
```

**Verification:**
```bash
psql -U pm_user -d portfolio_manager -c \
  "SELECT total_risk_amount FROM portfolio_state WHERE id = 1;"
```

**Expected Output:**
```
 total_risk_amount
-------------------
         999999.99
```

### Step 3: Restart Application

```bash
# Kill current instance
# Ctrl+C

# Restart
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
📊 Loading state from database...
🔄 Validating recovered state...
❌ Risk amount mismatch: DB=999999.99, Calculated=100000.00
🚨 CRITICAL: State corruption detected - HALTING STARTUP
ERROR: Recovery failed with code: VALIDATION_FAILED
Exiting...
```

**Exit Code:** 1 (application should exit)

### Step 4: Fix Corruption

```bash
# Restore correct value
psql -U pm_user -d portfolio_manager -c \
  "UPDATE portfolio_state SET total_risk_amount = 100000.00 WHERE id = 1;"
```

### Step 5: Verify Normal Recovery

```bash
# Restart application
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --broker zerodha \
  --api-key TEST_API_KEY
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
📊 Loading state from database...
🔄 Validating recovered state...
✅ State validation passed
✅ Crash recovery completed successfully - state restored
🚀 Webhook server starting on port 5000...
```

### Step 6: Verification Checklist

- [ ] Application EXITS when corruption detected (does not continue)
- [ ] Error log shows "🚨 CRITICAL: State corruption detected"
- [ ] Error log shows exact values (DB vs Calculated)
- [ ] Exit code is 1
- [ ] After fix, normal recovery works
- [ ] **FINANCIAL SAFETY:** Application halts instead of trading with corrupted state

**✅ PASS / ❌ FAIL:** __________

**Notes:**
```


```

---

## Test Scenario 4: HA Recovery (Multi-Instance)

**Objective:** Verify multi-instance recovery with Redis coordination
**Time:** 20 minutes
**Priority:** MEDIUM (Optional - requires Redis)

### Prerequisites

- Redis server running (`brew services start redis`)
- `redis_config.json` configured

### Step 1: Start Redis

```bash
# macOS
brew services start redis

# Verify
redis-cli ping
# Expected: PONG
```

### Step 2: Start Instance A (Terminal 1)

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager

python3 portfolio_manager.py live \
  --db-config database_config.json \
  --redis-config redis_config.json \
  --broker mock \
  --api-key TEST
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
✅ Redis connected successfully
🎯 [instance-A-12345] Became LEADER
📊 Loading state from database...
✅ Crash recovery completed successfully
🚀 Webhook server starting on port 5000...
```

### Step 3: Start Instance B (Terminal 2)

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager

python3 portfolio_manager.py live \
  --db-config database_config.json \
  --redis-config redis_config.json \
  --broker mock \
  --api-key TEST \
  --port 5001  # Different port
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
✅ Redis connected successfully
⏸️  [instance-B-67890] Running as FOLLOWER
📊 Loading state from database...
✅ Crash recovery completed successfully
🚀 Webhook server starting on port 5001...
```

### Step 4: Send Signal to Leader (Instance A)

```bash
# Terminal 3
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 50000,
    "stop": 49500,
    "lots": 5,
    "atr": 300,
    "er": 0.85,
    "supertrend": 49500,
    "timestamp": "2025-11-30T12:00:00Z"
  }'
```

**Expected:** Success (leader processes signal)

### Step 5: Send Signal to Follower (Instance B)

```bash
curl -X POST http://localhost:5001/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 50000,
    "stop": 49500,
    "lots": 5,
    "atr": 300,
    "er": 0.85,
    "supertrend": 49500,
    "timestamp": "2025-11-30T12:01:00Z"
  }'
```

**Expected Response:**
```json
{
  "status": "rejected",
  "reason": "not_leader",
  "message": "This instance is not the leader"
}
```

### Step 6: Kill Leader (Instance A)

```bash
# Terminal 1: Ctrl+C to kill Instance A
^C
```

**Watch Terminal 2 (Instance B):**
```
🎯 [instance-B-67890] Became LEADER
📊 Instance status set to 'active' in HA system
```

### Step 7: Restart Instance A

```bash
# Terminal 1
python3 portfolio_manager.py live \
  --db-config database_config.json \
  --redis-config redis_config.json \
  --broker mock \
  --api-key TEST
```

**Expected Output:**
```
Starting Portfolio Manager in LIVE mode...
✅ Database connected successfully
✅ Redis connected successfully
⏸️  [instance-A-12345] Running as FOLLOWER
📊 Instance status set to 'recovering' in HA system
📊 Loading state from database...
🔄 Fetched 1 open positions from database
✅ Crash recovery completed successfully
📈 Recovered state: 1 positions
📊 Instance status set to 'active' in HA system
🚀 Webhook server starting on port 5000...
```

### Step 8: Verify State Consistency

```bash
# Check both instances have same state
curl http://localhost:5002/status
curl http://localhost:5001/status

# Both should show same position count
```

### Step 9: Verification Checklist

- [ ] Instance A starts as leader
- [ ] Instance B starts as follower
- [ ] Leader processes signals successfully
- [ ] Follower rejects signals with "not_leader"
- [ ] After leader crash, follower becomes leader
- [ ] Restarted instance A becomes follower
- [ ] Recovery logs show "Instance status set to 'recovering'"
- [ ] Both instances have consistent state
- [ ] No split-brain scenario

**✅ PASS / ❌ FAIL:** __________

**Notes:**
```


```

---

## Cleanup After Testing

```bash
# Stop all running instances
# Ctrl+C in all terminals

# Clear test data from database
psql -U pm_user -d portfolio_manager <<EOF
DELETE FROM portfolio_positions WHERE position_id LIKE 'BANKNIFTY%';
DELETE FROM portfolio_state WHERE id = 1;
DELETE FROM pyramiding_state;
DELETE FROM signal_log;
DELETE FROM instance_metadata;
DELETE FROM leadership_history;
EOF

# Stop Redis (if used)
brew services stop redis
```

---

## Test Results Summary

| Scenario | Status | Time | Notes |
|----------|--------|------|-------|
| 1. Normal Recovery | ⬜ | ___ min | |
| 2. DB Unavailable | ⬜ | ___ min | |
| 3. State Corruption | ⬜ | ___ min | |
| 4. HA Recovery | ⬜ | ___ min | |

**Overall Status:** ⬜ PASS / ⬜ FAIL

**Issues Found:**
```


```

**Next Steps:**
```


```

---

**Tester:** __________________
**Date Completed:** __________________
**Approved By:** __________________
