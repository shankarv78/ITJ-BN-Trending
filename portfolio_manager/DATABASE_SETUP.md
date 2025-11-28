# Database Setup Guide

This guide covers PostgreSQL setup for the Portfolio Manager HA system.

## Prerequisites

- PostgreSQL 14+ installed
- Python 3.8+ with `psycopg2-binary` package

## Installation

### Option 1: Local PostgreSQL Installation

**macOS (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql-14 postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Download and install from [PostgreSQL Downloads](https://www.postgresql.org/download/windows/)

### Option 2: Docker (Recommended for Development)

```bash
docker run --name portfolio-postgres \
  -e POSTGRES_USER=pm_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=portfolio_manager \
  -p 5432:5432 \
  -d postgres:14
```

## Database Setup

### 1. Create Database and User

Connect to PostgreSQL:
```bash
psql -U postgres
```

Create database and user:
```sql
-- Create database
CREATE DATABASE portfolio_manager;

-- Create user
CREATE USER pm_user WITH PASSWORD 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE portfolio_manager TO pm_user;

-- Connect to portfolio_manager database
\c portfolio_manager

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO pm_user;
```

### 2. Run Migrations

Run the initial schema migration:
```bash
psql -U pm_user -d portfolio_manager -f portfolio_manager/migrations/001_initial_schema.sql
```

Verify tables were created:
```bash
psql -U pm_user -d portfolio_manager -c "\dt"
```

You should see 5 tables:
- `portfolio_positions`
- `portfolio_state`
- `pyramiding_state`
- `signal_log`
- `instance_metadata`

### 3. Verify Indexes

Check that indexes were created:
```bash
psql -U pm_user -d portfolio_manager -c "\di"
```

## Configuration

### 1. Create Database Config File

Copy the example config:
```bash
cp portfolio_manager/database_config.json.example portfolio_manager/database_config.json
```

Edit `database_config.json`:
```json
{
  "local": {
    "host": "localhost",
    "port": 5432,
    "database": "portfolio_manager",
    "user": "pm_user",
    "password": "your_secure_password",
    "minconn": 2,
    "maxconn": 10
  },
  "production": {
    "host": "your-production-db-host",
    "port": 5432,
    "database": "portfolio_manager_prod",
    "user": "pm_prod_user",
    "password": "${DB_PASSWORD}",
    "minconn": 5,
    "maxconn": 20
  }
}
```

**Security Note:** Add `database_config.json` to `.gitignore` to prevent committing passwords.

### 2. Test Connection

Test database connection:
```bash
psql -U pm_user -d portfolio_manager -c "SELECT version();"
```

Or test from Python:
```python
from core.db_state_manager import DatabaseStateManager
import json

with open('database_config.json', 'r') as f:
    config = json.load(f)

db_manager = DatabaseStateManager(config['local'])
print("Database connection successful!")
```

## Running Portfolio Manager with Database

Start portfolio manager with database persistence:
```bash
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_API_KEY \
  --db-config database_config.json \
  --db-env local
```

## Database Status Endpoint

Check database status:
```bash
curl http://localhost:5000/db/status
```

Response:
```json
{
  "status": "connected",
  "connection": "healthy",
  "open_positions": 2,
  "closed_equity": 5000000.0
}
```

## Troubleshooting

### Connection Refused

**Error:** `psycopg2.OperationalError: could not connect to server`

**Solutions:**
1. Verify PostgreSQL is running:
   ```bash
   # macOS
   brew services list
   
   # Linux
   sudo systemctl status postgresql
   ```

2. Check PostgreSQL is listening on port 5432:
   ```bash
   # macOS/Linux
   lsof -i :5432
   ```

3. Verify `pg_hba.conf` allows connections:
   ```bash
   # Location: /usr/local/var/postgres/pg_hba.conf (macOS Homebrew)
   # Or: /etc/postgresql/14/main/pg_hba.conf (Linux)
   ```

### Authentication Failed

**Error:** `psycopg2.OperationalError: password authentication failed`

**Solutions:**
1. Reset password:
   ```sql
   ALTER USER pm_user WITH PASSWORD 'new_password';
   ```

2. Update `database_config.json` with new password

### Database Does Not Exist

**Error:** `psycopg2.OperationalError: database "portfolio_manager" does not exist`

**Solution:**
```sql
CREATE DATABASE portfolio_manager;
GRANT ALL PRIVILEGES ON DATABASE portfolio_manager TO pm_user;
```

### Migration Errors

**Error:** `relation "portfolio_positions" already exists`

**Solution:**
Drop and recreate database:
```sql
DROP DATABASE portfolio_manager;
CREATE DATABASE portfolio_manager;
GRANT ALL PRIVILEGES ON DATABASE portfolio_manager TO pm_user;
```

Then rerun migration:
```bash
psql -U pm_user -d portfolio_manager -f portfolio_manager/migrations/001_initial_schema.sql
```

## Production Setup

### AWS RDS

1. Create RDS PostgreSQL instance
2. Configure security groups (allow port 5432 from application servers)
3. Update `database_config.json` with RDS endpoint
4. Use environment variables for passwords:
   ```json
   {
     "production": {
       "host": "portfolio-db.abc123.us-east-1.rds.amazonaws.com",
       "password": "${DB_PASSWORD}"
     }
   }
   ```

### Connection Pooling

For production, consider using PgBouncer:
- Reduces connection overhead
- Better resource utilization
- Configure `database_config.json` to point to PgBouncer

### Backup Strategy

**Recommended:**
- Daily automated backups (AWS RDS automated backups)
- Point-in-time recovery enabled
- Test restore procedures monthly

## Maintenance

### Cleanup Old Signal Logs

Run cleanup function:
```sql
SELECT cleanup_old_signals();
```

Or schedule via cron:
```bash
# Daily at 2 AM
0 2 * * * psql -U pm_user -d portfolio_manager -c "SELECT cleanup_old_signals();"
```

### Monitor Database Size

Check database size:
```sql
SELECT pg_size_pretty(pg_database_size('portfolio_manager'));
```

Check table sizes:
```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Performance Tuning

### Connection Pool Settings

Adjust in `database_config.json`:
- `minconn`: Minimum connections (2-5 for small deployments)
- `maxconn`: Maximum connections (10-20 for small deployments)

### Index Maintenance

Rebuild indexes periodically:
```sql
REINDEX DATABASE portfolio_manager;
```

### Vacuum

Run VACUUM to reclaim space:
```sql
VACUUM ANALYZE;
```

Schedule via cron:
```bash
# Weekly at 3 AM
0 3 * * 0 psql -U pm_user -d portfolio_manager -c "VACUUM ANALYZE;"
```

## Security Best Practices

1. **Use Strong Passwords:** Minimum 16 characters, mix of letters, numbers, symbols
2. **Limit Network Access:** Only allow connections from application servers
3. **Use SSL:** Enable SSL connections in production
4. **Regular Updates:** Keep PostgreSQL updated with security patches
5. **Backup Encryption:** Encrypt database backups
6. **Audit Logging:** Enable PostgreSQL audit logging for compliance

## Next Steps

- [ ] Set up production database (AWS RDS or similar)
- [ ] Configure automated backups
- [ ] Set up monitoring (CloudWatch, Datadog, etc.)
- [ ] Test disaster recovery procedures
- [ ] Document backup/restore procedures

