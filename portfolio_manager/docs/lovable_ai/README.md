# Lovable AI Integration Documentation

This folder contains all the documentation needed to generate a frontend portal for the Portfolio Manager using Lovable AI.

## Quick Start

### Step 1: Copy the Prompt

Open `LOVABLE_AI_PROMPT.md` and copy the entire content between "PROMPT START" and "PROMPT END" into Lovable AI.

### Step 2: Share Essential Files

Share these files from the `portfolio_manager` directory:

```
portfolio_manager/
├── core/models.py              # Data models (MUST SHARE)
├── core/config.py              # Configuration (MUST SHARE)
├── migrations/001_initial_schema.sql  # Database schema (MUST SHARE)
├── brokers/openalgo_client.py  # Reference for Zerodha client
├── portfolio_manager.py        # Main app, endpoints
├── requirements.txt            # Dependencies
└── README.md                   # Overview
```

### Step 3: Share Zerodha API Info

Point Lovable AI to:
- https://kite.trade/docs/connect/v3/
- https://github.com/zerodha/pykiteconnect

Or share the contents of `ZERODHA_KITE_API_GUIDE.md`.

## Files in This Folder

| File | Description |
|------|-------------|
| `LOVABLE_AI_PROMPT.md` | Complete prompt to paste into Lovable AI |
| `FILES_TO_SHARE.md` | Detailed list of all files to share with priorities |
| `ZERODHA_KITE_API_GUIDE.md` | Comprehensive Zerodha Kite API integration guide |
| `README.md` | This file |

## What Lovable AI Will Generate

Based on the prompt, Lovable AI will generate:

### Frontend (React/Next.js)

1. **Dashboard** - Portfolio overview, equity curve, metrics, health status
2. **Positions Page** - Open/closed positions table, detail modals
3. **Signals Page** - Signal log, validation stats, filtering
4. **Risk Management** - Tom Basso constraints, pyramid gates visualization
5. **Configuration** - Settings forms for portfolio, instruments, Zerodha API
6. **Analytics** - Performance charts, P&L breakdown, metrics
7. **Operations** - Rollover management, EOD status, manual interventions

### Backend (FastAPI)

1. **Zerodha Client** - Direct Kite API integration (replaces OpenAlgo)
2. **REST API** - All endpoints for frontend
3. **WebSocket** - Real-time updates using KiteTicker
4. **Database** - PostgreSQL with SQLAlchemy

## After Generation

1. **Configure Zerodha Credentials**
   - Get API Key and Secret from https://developers.kite.trade/
   - Set redirect URL in Kite Connect app settings
   - Update backend configuration

2. **Set Up Database**
   - Create PostgreSQL database
   - Run migrations from `migrations/001_initial_schema.sql`
   - Add new `zerodha_sessions` table

3. **Configure TradingView Webhook**
   - Deploy backend to accessible URL
   - Update TradingView alert webhook URL to `https://your-domain/api/webhook`

4. **Test OAuth Flow**
   - Click "Login with Zerodha" in frontend
   - Complete Kite login flow
   - Verify access token is saved

## Important Notes

### Zerodha Token Expiry

- Access tokens expire at **3:30 AM IST** every day
- Frontend should show session status and "Re-authenticate" button
- Backend should handle `TokenException` and prompt re-login

### Symbol Mapping

Bank Nifty and Gold Mini symbols need to be mapped from TradingView format to Zerodha format:

| TradingView | Zerodha |
|-------------|---------|
| BANK_NIFTY | BANKNIFTY24DEC52000CE |
| GOLD_MINI | GOLDM25JANFUT |

### Rate Limits

- Zerodha API: 3 requests/second (most APIs)
- Orders: 10 requests/second
- WebSocket: 3000 instruments per connection

## Support Files to Share (Optional)

For more complete context, also share:

```
portfolio_manager/
├── core/
│   ├── portfolio_state.py      # Portfolio management
│   ├── position_sizer.py       # Tom Basso sizing
│   ├── pyramid_gate.py         # Pyramid logic
│   ├── stop_manager.py         # ATR stops
│   └── db_state_manager.py     # Database operations
├── live/
│   ├── engine.py               # Live trading engine
│   └── rollover_*.py           # Rollover logic
└── tests/fixtures/
    └── webhook_payloads.py     # Example payloads
```

## Contact

For questions about the Portfolio Manager system, refer to:
- `portfolio_manager/README.md` - System overview
- `portfolio_manager/RUNBOOK.md` - Operations guide
- `portfolio_manager/DATABASE_SETUP.md` - Database setup
