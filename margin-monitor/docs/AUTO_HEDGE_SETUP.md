# Auto-Hedge System Setup Guide

## Prerequisites

1. **PostgreSQL** database running with the `auto_hedge` schema
2. **OpenAlgo** running and configured with API key
3. **Telegram Bot** (optional) for alerts

## 1. Database Setup

### Run Migrations

```bash
cd margin-monitor
source venv/bin/activate
alembic upgrade head
```

### Seed Strategy Schedule

```bash
# Connect to PostgreSQL and run the seed script
psql -d margin_monitor -f scripts/seed_strategy_schedule.sql
```

Or via Python:

```python
from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    with open('scripts/seed_strategy_schedule.sql', 'r') as f:
        conn.execute(text(f.read()))
    conn.commit()
```

## 2. Environment Configuration

Create or update `.env` file:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/margin_monitor

# OpenAlgo (REQUIRED for real orders)
OPENALGO_BASE_URL=http://localhost:5000
OPENALGO_API_KEY=your_api_key_here

# Telegram Alerts (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Auto-Hedge Control
AUTO_HEDGE_ENABLED=false          # Set to 'true' to enable
AUTO_HEDGE_DRY_RUN=true           # Set to 'false' for real orders

# API Security
HEDGE_API_KEY=your_secure_api_key # Required for manual actions
HEDGE_DEV_MODE=false              # Only set 'true' in development

# Hedge Parameters (optional, defaults shown)
HEDGE_UTILIZATION_TRIGGER=95     # % at which to buy hedges
HEDGE_MIN_PREMIUM=2.0            # Min LTP for hedge strike
HEDGE_MAX_PREMIUM=6.0            # Max LTP for hedge strike
HEDGE_MAX_COST_PER_DAY=50000     # Max daily hedge spend in ₹
HEDGE_COOLDOWN_SECONDS=120       # Min time between hedge actions
```

## 3. Start Backend

```bash
cd margin-monitor
source venv/bin/activate
python3 run.py
```

Expected output:
```
INFO: Starting Margin Monitor...
INFO: Database initialized
INFO: Scheduler started
INFO: Auto-Hedge Orchestrator started (dry_run=True)
INFO: Uvicorn running on http://0.0.0.0:5010
```

## 4. Start Frontend

```bash
cd frontend
npm run dev
```

## 5. Usage Workflow

### Step 1: Create a Session

Navigate to **Margin Monitor → Auto-Hedge → Session** tab.

Fill in:
- **Session Date**: Today's date
- **Index**: NIFTY or SENSEX
- **Expiry Type**: 0DTE, 1DTE, 2DTE
- **Expiry Date**: The actual expiry date
- **Number of Baskets**: How many strategy baskets you're running
- **Budget per Basket**: ₹10L default

Click **Create Session**.

### Step 2: Verify Schedule

Navigate to the **Schedule** tab to see the pre-configured entry times for each day.

### Step 3: Monitor Status

The **Status** tab shows:
- Current margin utilization
- Active hedges
- Next scheduled entry
- Circuit breaker state
- Daily cost spent

### Step 4: Auto-Hedge Behavior

When enabled (`AUTO_HEDGE_ENABLED=true`), the system:

1. Checks margin every 30 seconds during market hours (9:15-15:30)
2. Before each strategy entry time (from schedule):
   - Calculates projected utilization after entry
   - If projected > 95%, buys optimal hedge
3. After strategy exits:
   - If utilization drops significantly, sells hedges to recover cost
4. Sends Telegram alerts for all buy/sell actions

### Step 5: Manual Override

Use the **Manual** tab for:
- Emergency hedge buying
- Testing in dry-run mode
- Exiting hedges manually

## 6. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hedge/status` | GET | Current system status |
| `/api/hedge/session` | GET/POST | Get or create session |
| `/api/hedge/schedule` | GET | Get strategy schedule |
| `/api/hedge/toggle` | POST | Enable/disable auto-hedge |
| `/api/hedge/manual/buy` | POST | Manual hedge buy (requires API key) |
| `/api/hedge/manual/exit` | POST | Manual hedge exit (requires API key) |
| `/api/hedge/transactions` | GET | Transaction history |
| `/api/hedge/analytics` | GET | Cost analytics |

## 7. Troubleshooting

### "No session found"
Create a session first via UI or API.

### "Orchestrator not initialized"
Check that `AUTO_HEDGE_ENABLED=true` in environment.

### "Circuit breaker OPEN"
Too many API failures. Wait 60 seconds or check OpenAlgo connection.

### No hedges being placed
1. Check dry_run mode is off
2. Verify utilization is above trigger threshold
3. Check if daily cost cap is reached
4. Check cooldown hasn't blocked action

### Telegram not working
Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set correctly.
