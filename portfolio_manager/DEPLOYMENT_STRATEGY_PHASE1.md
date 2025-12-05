# Phase 1 Deployment Strategy - Database Persistence & Crash Recovery

**Target:** Production deployment of PostgreSQL state persistence and crash recovery
**Risk Level:** Medium (database dependency introduced)
**Rollback Time:** <5 minutes

---

## Pre-Deployment Checklist

### 1. Database Setup

```bash
# Install PostgreSQL 13+
sudo apt-get install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE portfolio_manager;
CREATE USER portfolio_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE portfolio_manager TO portfolio_user;
\q

# Run migrations
psql -U portfolio_user -d portfolio_manager -f migrations/001_initial_schema.sql
psql -U portfolio_user -d portfolio_manager -f migrations/002_add_heartbeat_index.sql
psql -U portfolio_user -d portfolio_manager -f migrations/003_add_leadership_history.sql

# Verify schema
psql -U portfolio_user -d portfolio_manager -c "\dt"
# Expected tables: portfolio_state, portfolio_positions, instance_heartbeat, leadership_history
```

### 2. Configuration Files

```bash
# Create database_config.json from example
cp database_config.json.example database_config.json

# Edit with production credentials
{
  "host": "localhost",
  "port": 5432,
  "database": "portfolio_manager",
  "user": "portfolio_user",
  "password": "your_secure_password"
}

# Set restrictive permissions
chmod 600 database_config.json
```

### 3. Test Database Connectivity

```bash
# Test connection
python -c "
from core.db_state_manager import DatabaseStateManager
db = DatabaseStateManager('database_config.json')
print('Connection successful!')
"
```

### 4. Run Integration Tests

```bash
# Full test suite
pytest tests/integration/test_persistence.py -v
pytest tests/integration/test_crash_recovery_integration.py -v
pytest tests/performance/test_recovery_performance.py -v

# Expected: All tests pass
# Performance: Recovery <100ms for 1-10 positions
```

---

## Deployment Steps

### Step 1: Deploy to Staging (Non-Production)

**Objective:** Validate deployment process and catch issues

```bash
# Stop staging instance
sudo systemctl stop portfolio_manager_staging

# Backup current version
cp -r /opt/portfolio_manager /opt/portfolio_manager_backup_$(date +%Y%m%d)

# Deploy new code
git pull origin feature/ha-phase1-database-persistence
pip install -r requirements.txt

# Verify configuration
ls -l database_config.json  # Should exist with correct permissions

# Start with logging enabled
python portfolio_manager.py live --log-level DEBUG

# Monitor logs for recovery
tail -f logs/portfolio_manager.log
# Expected: "Recovery successful: loaded X positions in Yms"
```

**Validation:**
- [ ] Instance starts without errors
- [ ] Recovery completes successfully
- [ ] No positions = clean start
- [ ] Database writes on position open/close
- [ ] Log entries show DB operations

**Duration:** 15 minutes

---

### Step 2: Deploy to Production (Single Instance)

**Objective:** Deploy to production with zero downtime using graceful shutdown

**Pre-Deployment:**
```bash
# Check current state
curl http://localhost:5000/health
# Note: Current positions, risk%, equity

# Backup database
pg_dump -U portfolio_user portfolio_manager > backup_pre_phase1_$(date +%Y%m%d_%H%M%S).sql

# Backup configuration
cp database_config.json database_config.json.backup
```

**Deployment:**
```bash
# 1. Stop accepting new signals (optional: enable maintenance mode)
# If using webhook, temporarily return 503

# 2. Wait for open positions to close OR manually close (if acceptable)
# Check: curl http://localhost:5000/health
# Verify: "positions": 0

# 3. Graceful shutdown
sudo systemctl stop portfolio_manager
# OR: pkill -SIGTERM -f portfolio_manager.py

# 4. Deploy new version
cd /opt/portfolio_manager
git pull origin feature/ha-phase1-database-persistence
pip install -r requirements.txt

# 5. Verify configuration exists
ls -l database_config.json

# 6. Start with enhanced logging
sudo systemctl start portfolio_manager
# OR: python portfolio_manager.py live --log-level INFO &

# 7. Monitor startup
tail -f logs/portfolio_manager.log
# Expected: "Recovery successful: loaded 0 positions in Xms" (clean start)

# 8. Verify health
curl http://localhost:5000/health
# Expected: {"status": "healthy", "positions": 0, "risk_pct": 0.0}

# 9. Re-enable signal acceptance
# If maintenance mode was enabled, disable it
```

**Validation:**
- [ ] Instance starts cleanly
- [ ] Health endpoint responds
- [ ] Database connectivity confirmed
- [ ] No errors in logs
- [ ] Ready to accept signals

**Duration:** 10 minutes
**Risk:** Low (no open positions)

---

### Step 3: Monitor First Signal Processing

**Objective:** Verify database persistence on first real signal

```bash
# Monitor logs for first signal
tail -f logs/portfolio_manager.log

# When signal arrives, verify:
# 1. Position opened successfully
# 2. "Portfolio state saved to database" log entry
# 3. Database write confirmed

# Check database directly
psql -U portfolio_user -d portfolio_manager -c "
SELECT position_id, instrument, lots, entry_price, status
FROM portfolio_positions;
"
# Expected: 1 row with open position

# Check portfolio state
psql -U portfolio_user -d portfolio_manager -c "
SELECT closed_equity, total_risk_amount, margin_used, updated_at
FROM portfolio_state;
"
# Expected: 1 row with current state
```

**Validation:**
- [ ] Signal processed successfully
- [ ] Position saved to database
- [ ] Portfolio state saved to database
- [ ] No errors or warnings

**Duration:** Wait for next signal (could be hours/days)

---

### Step 4: Test Crash Recovery (Controlled)

**Objective:** Validate recovery works in production

**Procedure:**
```bash
# 1. Note current state
curl http://localhost:5000/health
# Record: positions, risk%, equity

# 2. Simulate crash (controlled restart)
sudo systemctl restart portfolio_manager

# 3. Monitor recovery
tail -f logs/portfolio_manager.log
# Expected: "Recovery successful: loaded X positions in Yms"

# 4. Verify recovered state matches
curl http://localhost:5000/health
# Compare: positions, risk%, equity should match pre-restart values

# 5. Check database alignment
psql -U portfolio_user -d portfolio_manager -c "
SELECT COUNT(*) FROM portfolio_positions WHERE status='open';
"
# Should match position count from health endpoint
```

**Validation:**
- [ ] Recovery completes in <100ms
- [ ] All positions restored correctly
- [ ] Risk/margin calculations match
- [ ] No VALIDATION_FAILED errors

**Duration:** 5 minutes

---

## Rollback Plan

### If Deployment Fails

```bash
# Stop new version
sudo systemctl stop portfolio_manager

# Restore previous version
rm -rf /opt/portfolio_manager
mv /opt/portfolio_manager_backup_$(date +%Y%m%d) /opt/portfolio_manager

# Start old version
sudo systemctl start portfolio_manager

# Verify
curl http://localhost:5000/health
```

**Duration:** <5 minutes

### If Database Issues Occur

**Option 1: Restore Database**
```bash
# Stop instance
sudo systemctl stop portfolio_manager

# Restore from backup
psql -U portfolio_user -d portfolio_manager < backup_pre_phase1_*.sql

# Restart
sudo systemctl start portfolio_manager
```

**Option 2: Clean State**
```bash
# Only if no open positions and acceptable to start fresh
psql -U portfolio_user -d portfolio_manager -c "
DELETE FROM portfolio_positions;
DELETE FROM portfolio_state;
"

# Restart instance
sudo systemctl restart portfolio_manager
```

---

## Post-Deployment Monitoring

### First 24 Hours

**Monitor:**
1. **Recovery Time:** Should be <100ms for normal position counts
2. **Database Writes:** Should occur on every position open/close
3. **Error Logs:** Check for any DB-related errors
4. **Performance:** No noticeable latency increase

**Metrics to Track:**
```bash
# Check recovery metrics
grep "Recovery successful" logs/portfolio_manager.log | tail -20

# Check database write frequency
psql -U portfolio_user -d portfolio_manager -c "
SELECT COUNT(*), DATE_TRUNC('hour', updated_at) as hour
FROM portfolio_state
GROUP BY hour
ORDER BY hour DESC
LIMIT 24;
"

# Check for errors
grep -i "error\|failed" logs/portfolio_manager.log | tail -50
```

### First Week

**Validate:**
- [ ] Recovery tested after at least 2 restarts
- [ ] Database size reasonable (<10MB for typical usage)
- [ ] No performance degradation
- [ ] Backup strategy working (daily pg_dump)

---

## Success Criteria

**Phase 1 deployment is successful when:**

1. ✅ Database persistence working (verified by direct SQL queries)
2. ✅ Crash recovery working (tested with controlled restarts)
3. ✅ Recovery time <100ms for normal position counts
4. ✅ No VALIDATION_FAILED errors
5. ✅ Zero data loss after crashes
6. ✅ Performance unchanged (no latency increase)
7. ✅ Database backup strategy in place

---

## Known Limitations (Phase 1)

1. **Single Instance Only:** High availability requires Phase 2 (Redis coordination)
2. **Manual Intervention:** DB_UNAVAILABLE requires manual restart
3. **No Failover:** Crash = downtime until restart (minutes)

**Next Phase:** Phase 2 will address these with Redis-based HA and automatic failover.

---

## Emergency Contacts

- **Database Issues:** Check PostgreSQL logs: `/var/log/postgresql/`
- **Application Issues:** Check application logs: `logs/portfolio_manager.log`
- **Runbook:** See `RUNBOOK.md` for detailed troubleshooting

---

**Deployment Owner:** System Administrator
**Last Updated:** December 1, 2025
**Status:** Ready for Production Deployment
