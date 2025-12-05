# Portfolio Manager - Operations Runbook

## Crash Recovery Failures

### Symptom: DB_UNAVAILABLE

**Recognition:**
```
ERROR: Recovery failed: DB_UNAVAILABLE
Unable to connect to PostgreSQL
```

**Diagnostic Steps:**
1. Check database status: `pg_isready -h localhost -p 5432`
2. Verify credentials in `database_config.json`
3. Check network connectivity
4. Review PostgreSQL logs: `/var/log/postgresql/`

**Resolution:**
```bash
# Restart PostgreSQL
sudo systemctl restart postgresql

# Verify connection
psql -h localhost -U portfolio_user -d portfolio_manager -c "\dt"

# Restart portfolio manager
python portfolio_manager.py live
```

**Escalate if:** Database does not start after 3 restart attempts

---

### Symptom: VALIDATION_FAILED

**Recognition:**
```
ERROR: Recovery validation failed
Risk mismatch: DB=125000.0, Calculated=125420.0, Diff=420.0
```

**Diagnostic Steps:**
1. Check position data: `SELECT * FROM portfolio_positions WHERE status='open';`
2. Verify configuration consistency (margin values in config vs code)
3. Check for partial writes (transaction rollback)
4. Review recent changes to risk calculation logic

**Resolution:**

**Option A - Configuration Mismatch:**
```python
# Verify margin settings match
# core/config.py vs database_config.json
GOLD_MINI: margin_per_lot=105000.0  # Conservative
BANK_NIFTY: margin_per_lot=270000.0
```

**Option B - Corrupt State (Manual Intervention):**
```sql
-- Backup current state
CREATE TABLE portfolio_state_backup AS SELECT * FROM portfolio_state;
CREATE TABLE portfolio_positions_backup AS SELECT * FROM portfolio_positions;

-- Close all positions manually if safe
UPDATE portfolio_positions SET status='closed' WHERE status='open';

-- Restart with clean state
```

**Escalate if:** Validation fails after configuration fix AND no positions in database

---

### Symptom: DATA_CORRUPT

**Recognition:**
```
ERROR: Recovery failed: DATA_CORRUPT
Invalid position data: missing entry_price for BANK_NIFTY_Long_1
```

**Diagnostic Steps:**
1. Check data integrity: `SELECT * FROM portfolio_positions WHERE entry_price IS NULL;`
2. Review application logs for failed writes
3. Check PostgreSQL transaction logs

**Resolution:**
```sql
-- Identify corrupt positions
SELECT position_id, instrument, lots, entry_price, status
FROM portfolio_positions
WHERE entry_price IS NULL OR lots IS NULL OR lots <= 0;

-- Option 1: Delete corrupt test positions only
DELETE FROM portfolio_positions
WHERE position_id LIKE 'PERF_TEST_%' AND entry_price IS NULL;

-- Option 2: Manual data fix (if production positions)
-- Recover entry_price from application logs or broker statements
UPDATE portfolio_positions
SET entry_price = <recovered_value>
WHERE position_id = '<position_id>';
```

**Escalate if:** Production positions are corrupt and cannot be recovered from logs

---

## Pre-Deployment Checklist

Before deploying new version:

1. **Database Backup:**
   ```bash
   pg_dump -U portfolio_user portfolio_manager > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Test Recovery:**
   ```bash
   cd tests/integration
   pytest test_persistence.py -v
   pytest test_crash_recovery_integration.py -v
   ```

3. **Verify Configuration:**
   - `database_config.json` exists and valid
   - Margin values match code (105K Gold, 270K BN)
   - Redis config valid if HA enabled

4. **Check Database Migrations:**
   ```bash
   psql -U portfolio_user -d portfolio_manager -f migrations/001_initial_schema.sql
   psql -U portfolio_user -d portfolio_manager -f migrations/002_add_heartbeat_index.sql
   psql -U portfolio_user -d portfolio_manager -f migrations/003_add_leadership_history.sql
   ```

---

## Emergency Procedures

### Force Clean State (DANGER - Production Data Loss)

**Use only when:**
- Validation fails repeatedly
- No open positions OR all positions closed manually via broker
- Database state is irrecoverably corrupt

**Procedure:**
```sql
-- BACKUP FIRST!
pg_dump -U portfolio_user portfolio_manager > emergency_backup_$(date +%Y%m%d_%H%M%S).sql

-- Delete all positions
DELETE FROM portfolio_positions;

-- Reset portfolio state
DELETE FROM portfolio_state;

-- Verify clean
SELECT COUNT(*) FROM portfolio_positions;  -- Should be 0
SELECT COUNT(*) FROM portfolio_state;      -- Should be 0
```

**After cleanup:**
1. Verify no broker positions open
2. Restart portfolio manager
3. Monitor first 3 signals closely

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Recovery Time:** Should be <100ms for normal position counts (<10 positions)
2. **Validation Success Rate:** Should be 100%
3. **Database Connection Health:** Monitor connection pool

### Alert Thresholds

- **CRITICAL:** Recovery fails 2+ times in 1 hour
- **WARNING:** Recovery time >500ms
- **INFO:** Recovery time >100ms

### Health Check Endpoint

```bash
curl http://localhost:5000/health
# Should return: {"status": "healthy", "positions": N, "risk_pct": X.X}
```

---

## Contact & Escalation

**Level 1:** Restart services, check logs, verify configuration
**Level 2:** Database corruption, manual intervention required
**Level 3:** Code bugs, requires developer intervention

**Response Times:**
- DB_UNAVAILABLE: 5 minutes
- VALIDATION_FAILED: 15 minutes
- DATA_CORRUPT: 30 minutes
