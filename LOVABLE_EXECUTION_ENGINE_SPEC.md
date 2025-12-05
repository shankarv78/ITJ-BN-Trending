# Lovable Execution Engine - Complete Implementation Specification

## Instructions for Lovable AI

**IMPORTANT - READ FIRST:**

1. **Use TaskMaster internally** to break down each feature into subtasks before implementing
2. **Ask clarifying questions** if any requirement is ambiguous - do NOT assume
3. **Implement incrementally** with testable checkpoints after each task
4. **Pause for verification** after completing each major feature (Tasks 1-10)
5. **Follow the implementation order** specified in the Phases section
6. **Reuse code from the Portfolio Manager** where applicable (see GitHub Reference section)

---

## Software Development Guidelines

### Code Modification Principles

When editing code:
1. **Always test changes** before committing
2. **Preserve existing functionality** - don't break working features
3. **Update version comments** when making significant changes
4. **Add changelog entries** for tracking changes
5. **Check division-by-zero protection** for any new calculations
6. **Verify edge cases** - null values, empty arrays, network failures

### When Adding New Parameters

1. Use descriptive names with clear purpose
2. Provide conservative defaults (safety over convenience)
3. Add validation for all user inputs
4. Document expected ranges and types

### Quality Standards

- **No lookahead bias** in calculations
- **Repainting prevention** in time-sensitive operations  
- **Division by zero checks** for all calculations
- **Null safety** for all optional values
- **Error boundaries** around external API calls

---

## GitHub Repository Reference

**IMPORTANT: Reuse existing code from the Portfolio Manager repository where applicable.**

### Repository Details

```
Repository: https://github.com/shankarv78/ITJ-BN-Trending
Branch: main
```

**Key Reusable Components:**

| Component | Path | Description |
|-----------|------|-------------|
| Position Sizer | `portfolio_manager/core/position_sizer.py` | Tom Basso triple constraint logic |
| Webhook Parser | `portfolio_manager/core/webhook_parser.py` | TradingView JSON signal parsing |
| Config | `portfolio_manager/core/config.py` | Instrument configs, margin values |
| Models | `portfolio_manager/core/models.py` | Position, Trade, Signal data models |
| OpenAlgo Client | `openalgo_client.py` | Python OpenAlgo integration |

**To access this code from Lovable:**
1. Clone the repository
2. Reference the Python files for logic/algorithms
3. Port to TypeScript where needed
4. Maintain the same calculation formulas

---

## Project Context

This is an enhancement to an existing position sizing calculator web app. The app currently has:

**Already Implemented (DO NOT recreate):**
- Position sizing calculator using Tom Basso triple constraint (Risk, Volatility, Margin)
- User settings persistence via localStorage
- CSV import/export for daily state persistence

**What We're Adding:**
- OpenAlgo broker integration for live trading
- Automated trade execution via webhook (TradingView → Web App → OpenAlgo)
- Real-time position dashboard
- Risk management pre-checks
- Analytics and equity curve

**NOTE:** The manual JSON parser was removed from the web app. Signals will come via webhook only.

---

## OpenAlgo Setup & Configuration

### What is OpenAlgo?

OpenAlgo is an open-source broker abstraction layer that provides a unified API for 15+ Indian brokers.

**GitHub Repository:** https://github.com/marketcalls/openalgo

**Documentation:** https://docs.openalgo.in

### Step 1: Install OpenAlgo

```bash
# Clone OpenAlgo
cd ~
git clone https://github.com/marketcalls/openalgo.git
cd openalgo

# Install UV package manager
pip install uv

# Configure environment
cp .sample.env .env
```

### Step 2: Configure OpenAlgo (.env file)

```env
# Broker Credentials (works for all brokers)
BROKER_API_KEY=your_broker_api_key
BROKER_API_SECRET=your_broker_api_secret

# Generate security keys
# Run: python -c "import secrets; print(secrets.token_hex(32))"
APP_KEY=<generated_key>
API_KEY_PEPPER=<generated_pepper>

# Database (SQLite default)
DATABASE_URL=sqlite:///db/openalgo.db
```

### Step 3: Start OpenAlgo Server

```bash
cd ~/openalgo
uv run app.py

# Server starts at http://localhost:5000
```

### Step 4: First-Time Broker Login

1. Open browser: http://localhost:5000
2. Select your broker (Zerodha, Dhan, Finvasia, etc.)
3. Login with your broker credentials
4. Complete 2FA if required
5. Navigate to Settings → API Keys
6. Generate a new API key
7. **Save this API key** - you'll need it for the Lovable app

### Daily Startup Sequence (Simple)

**Every trading day, just 2 steps:**

```bash
# Step 1: Start OpenAlgo
cd ~/openalgo && uv run app.py

# Step 2: Login to broker via browser
# Open http://localhost:5000 and complete broker login
```

That's it! After broker login, OpenAlgo handles all authentication automatically.

**Broker Session Duration:**
- **Zerodha:** Valid until 3:30 AM next day
- **Dhan:** Valid for 24 hours
- **Finvasia:** Valid until midnight

---

## Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TradingView                                    │
│  ┌──────────────────────┐         ┌──────────────────────┐             │
│  │ BankNifty V8.0       │         │ GoldMini V8.0        │             │
│  │ (Pine Script)        │         │ (Pine Script)        │             │
│  └──────────┬───────────┘         └──────────┬───────────┘             │
│             │ JSON Webhook                    │ JSON Webhook            │
└─────────────┼────────────────────────────────┼──────────────────────────┘
              │                                 │
              └─────────────┬───────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Lovable Web App (This System)                         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Supabase Edge Function - Webhook Receiver                         │ │
│  │  • Receives TradingView webhooks                                  │ │
│  │  • Validates signal freshness (<90 seconds)                       │ │
│  │  • Checks for duplicates                                          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                            │                                             │
│                            ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Position Sizing Engine (Tom Basso Triple Constraint)              │ │
│  │  • Lot-R: Risk-based (Equity × Risk% / Stop Distance)            │ │
│  │  • Lot-V: Volatility-based (Equity × Vol% / ATR)                 │ │
│  │  • Lot-M: Margin-based (Available Margin / Margin per Lot)       │ │
│  │  • Final Lots = MIN(Lot-R, Lot-V, Lot-M)                         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                            │                                             │
│                            ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ OpenAlgo Proxy (Supabase Edge Function)                           │ │
│  │  • Securely stores API credentials                                │ │
│  │  • Proxies requests to OpenAlgo server                           │ │
│  │  • Logs all API calls for audit                                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    OpenAlgo Server (localhost:5000)                      │
│  • Unified API for all brokers                                          │
│  • Handles broker authentication                                        │
│  • Executes orders, fetches positions                                   │
└─────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Broker (Zerodha/Dhan/Finvasia)                        │
│  • Order execution                                                       │
│  • Position management                                                   │
│  • Margin tracking                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why OpenAlgo (Not Direct Broker Integration)?

| Aspect | OpenAlgo | Direct Broker API |
|--------|----------|-------------------|
| **Broker Switch** | ~5 minutes (config change) | 2-5 days (code rewrite) |
| **Brokers Supported** | 15+ (Zerodha, Dhan, Finvasia, Angel, etc.) | 1 per integration |
| **Authentication** | OpenAlgo handles OAuth, token refresh | Must implement per broker |
| **API Format** | Unified REST API | Different per broker |
| **Maintenance** | OpenAlgo team maintains | You maintain all brokers |

**Conclusion:** OpenAlgo is the clear choice for broker portability.

---

## Feature Tasks

### TASK 1: OpenAlgo Backend Proxy Setup (P0)

Create Supabase Edge Functions to proxy requests to OpenAlgo server.

**Endpoints to implement:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/openalgo/connect` | POST | Test connection & health check |
| `/openalgo/order` | POST | Place order (market/limit) |
| `/openalgo/cancel` | POST | Cancel pending order |
| `/openalgo/positions` | GET | Get open positions |
| `/openalgo/orders` | GET | Get order book |
| `/openalgo/funds` | GET | Get available margin |
| `/openalgo/ltp` | POST | Get last traded price |

**Reference Implementation:** See `openalgo_client.py` in GitHub repo for Python version.

**Security Requirements:**
- Store OpenAlgo API key in Supabase Vault (never expose to frontend)
- Validate all request payloads
- Log all API calls with timestamps
- Rate limit to prevent abuse (10 requests/second)

---

### TASK 2: OpenAlgo Configuration UI (P0)

Settings page for OpenAlgo connection.

**Fields:**
- Server URL (default: `http://localhost:5000`)
- API Key (masked password input)
- Broker dropdown (Zerodha, Dhan, Finvasia, Angel, Fyers, etc.)
- Test Connection button with status indicator

**Daily Startup Reminder:**
Display message: "Remember to login to your broker at http://localhost:5000 each morning"

---

### TASK 3: Webhook Receiver (P0)

Supabase Edge Function to receive webhooks from TradingView.

**Endpoint:** `/functions/v1/webhook-receiver`

**Request Format (from TradingView):**
```json
{
  "type": "BASE_ENTRY",
  "instrument": "BANKNIFTY",
  "position": "Long_1",
  "price": 52450.50,
  "stop": 52100.00,
  "atr": 350.25,
  "er": 0.72,
  "supertrend": 52100.00,
  "timestamp": "2025-01-15 14:30:00"
}
```

**Validation Rules:**
1. Signal age < 90 seconds (reject stale signals)
2. No duplicate signals (same instrument + type + timestamp)
3. Valid signal type (BASE_ENTRY, PYRAMID, EXIT, STOP_UPDATE)
4. Valid instrument (BANKNIFTY, GOLDMINI)

**Reference:** See `portfolio_manager/core/webhook_parser.py` for parsing logic.

---

### TASK 4: Live Position Dashboard (P0)

Real-time display of open positions from broker.

**Features:**
- Auto-refresh every 30 seconds (or manual refresh button)
- Columns: Symbol, Qty, Avg Price, LTP, P&L, P&L%
- Color-coded P&L (green for profit, red for loss)
- "Close Position" button per row with confirmation dialog
- Total portfolio P&L summary at top
- Mobile responsive

**Reference:** See `portfolio_manager/core/portfolio_state.py` for position tracking logic.

---

### TASK 5: Automated Trade Tracker (P0)

Automatically log all executed trades (replaces manual journal).

**Auto-record on:**
- Order execution: Create entry trade record
- Position close: Update with exit price, calculate P&L

**Trade Fields:**
- signal_id (links to webhook signal)
- instrument
- direction (LONG/SHORT)
- entry_time, entry_price
- quantity, lots
- exit_time, exit_price
- pnl, pnl_percent
- status (OPEN/CLOSED)
- order_ids (broker order IDs)

**Reference:** See `portfolio_manager/core/models.py` for data structures.

---

### TASK 6: Order Placement UI (P0)

Manual order placement interface.

**Fields:**
- Instrument selector (Bank Nifty, Gold Mini)
- Action (BUY / SELL) - radio buttons
- Lots (number input, shows quantity based on lot size)
- Order type (MARKET / LIMIT)
- Price (for LIMIT orders only)
- Product (NRML for overnight, MIS for intraday)

**Lot Sizes:**
- Bank Nifty: 15 per lot
- Gold Mini: 100 per lot

---

### TASK 7: Order Book & History (P1)

View all orders from broker.

**Features:**
- Fetch orders from OpenAlgo `/api/v1/orderbook`
- Display: Order ID, Symbol, Type, Qty, Price, Status, Time
- Cancel button for pending orders
- Filter by status (All / Pending / Filled / Rejected)

---

### TASK 8: Risk Management Checks (P0)

Pre-execution validation before placing orders.

**Checks:**
1. **Portfolio Risk Check:** Total risk < 2% of equity
2. **Margin Check:** Required margin < Available margin
3. **Daily Loss Limit:** Halt if daily loss > threshold (configurable)

**Position Sizing Formula (Tom Basso Triple Constraint):**

```javascript
// From portfolio_manager/core/position_sizer.py

const INSTRUMENT_CONFIG = {
  BANKNIFTY: { lotSize: 15, pointValue: 15, marginPerLot: 270000 },
  GOLDMINI: { lotSize: 100, pointValue: 10, marginPerLot: 105000 }
};

function calculatePositionSize({ equity, riskPercent, volPercent, maxMarginPercent, 
                                  availableMargin, entryPrice, stopPrice, atr, instrument }) {
  const config = INSTRUMENT_CONFIG[instrument];
  const stopDistance = Math.abs(entryPrice - stopPrice);
  
  // Risk-based lots
  const riskPerLot = stopDistance * config.pointValue;
  const riskBudget = equity * (riskPercent / 100);
  const lotR = Math.floor(riskBudget / riskPerLot);
  
  // Volatility-based lots
  const volPerLot = atr * config.pointValue;
  const volBudget = equity * (volPercent / 100);
  const lotV = Math.floor(volBudget / volPerLot);
  
  // Margin-based lots
  const marginBudget = availableMargin * (maxMarginPercent / 100);
  const lotM = Math.floor(marginBudget / config.marginPerLot);
  
  // Take minimum (most conservative)
  const lots = Math.max(0, Math.min(lotR, lotV, lotM));
  const limiter = lots === lotR ? "RISK" : lots === lotV ? "VOLATILITY" : "MARGIN";
  
  return { lots, lotR, lotV, lotM, limiter };
}
```

---

### TASK 9: Equity Curve & Analytics (P2)

Portfolio performance visualization.

**Features:**
- Daily equity tracking (record at EOD)
- Equity curve line chart (using Recharts)
- Key metrics:
  - Total P&L
  - Win Rate
  - Average Win / Average Loss
  - Profit Factor
  - Max Drawdown
- Monthly breakdown table
- CSV export

---

### TASK 10: Instrument Symbol Mapping (P1)

Map generic instrument names to broker-specific symbols.

**Bank Nifty (Synthetic Futures via Options):**
- Need ATM strike options: CE + PE
- Symbol format: `BANKNIFTY{DDMMMYY}{STRIKE}{CE/PE}`
- Example: `BANKNIFTY15JAN2553000CE`

**Gold Mini (MCX Futures):**
- Symbol format: `GOLDM{DDMMMYY}FUT`
- Example: `GOLDM05FEB25FUT`

**Features:**
- Expiry calendar calculation (weekly for BN, monthly for Gold)
- ATM strike calculation from current price
- Handle expiry rollover logic

**Reference:** See `portfolio_manager/live/expiry_utils.py` for expiry calculations.

---

## Database Schema (Supabase)

```sql
-- Portfolio Settings
CREATE TABLE portfolio_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL UNIQUE,
  initial_capital DECIMAL(15,2) DEFAULT 5000000,
  risk_percent DECIMAL(5,2) DEFAULT 0.5,
  volatility_percent DECIMAL(5,2) DEFAULT 0.2,
  max_margin_percent DECIMAL(5,2) DEFAULT 80,
  openalgo_url TEXT DEFAULT 'http://localhost:5000',
  openalgo_api_key TEXT,
  broker TEXT DEFAULT 'zerodha',
  auto_execute BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Signals (from TradingView webhooks)
CREATE TABLE signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  raw_json JSONB NOT NULL,
  signal_type TEXT NOT NULL,
  instrument TEXT NOT NULL,
  price DECIMAL(12,2),
  stop_price DECIMAL(12,2),
  atr DECIMAL(12,2),
  received_at TIMESTAMPTZ DEFAULT NOW(),
  executed BOOLEAN DEFAULT FALSE,
  execution_status TEXT DEFAULT 'pending',
  calculated_lots INTEGER,
  error_message TEXT
);

-- Trades (automated tracking)
CREATE TABLE trades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  signal_id UUID REFERENCES signals,
  instrument TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
  entry_time TIMESTAMPTZ NOT NULL,
  entry_price DECIMAL(12,2) NOT NULL,
  quantity INTEGER NOT NULL,
  lots INTEGER NOT NULL,
  initial_stop DECIMAL(12,2),
  exit_time TIMESTAMPTZ,
  exit_price DECIMAL(12,2),
  pnl DECIMAL(15,2),
  pnl_percent DECIMAL(8,4),
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
  order_ids TEXT[],
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily Equity
CREATE TABLE daily_equity (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  date DATE NOT NULL,
  starting_equity DECIMAL(15,2),
  ending_equity DECIMAL(15,2),
  realized_pnl DECIMAL(15,2),
  UNIQUE(user_id, date)
);

-- API Logs (audit trail)
CREATE TABLE api_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  action TEXT NOT NULL,
  payload JSONB,
  response_status INTEGER,
  response_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security on all tables
ALTER TABLE portfolio_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_equity ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_logs ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users can only access their own data)
CREATE POLICY "Users manage own data" ON portfolio_settings FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own data" ON signals FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own data" ON trades FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own data" ON daily_equity FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own data" ON api_logs FOR ALL USING (auth.uid() = user_id);
```

---

## Implementation Phases

**Phase 1 (MVP - 1 week):**
- Task 1: OpenAlgo Backend Proxy
- Task 2: OpenAlgo Configuration UI
- Task 4: Live Position Dashboard
- Task 6: Order Placement UI

**Phase 2 (Automation - 1 week):**
- Task 3: Webhook Receiver
- Task 5: Automated Trade Tracker
- Task 8: Risk Management Checks

**Phase 3 (Polish - 1 week):**
- Task 7: Order Book & History
- Task 9: Equity Curve & Analytics
- Task 10: Instrument Symbol Mapping

---

## Error Handling

| Error | User Message | Action |
|-------|--------------|--------|
| OpenAlgo unreachable | "Cannot connect to OpenAlgo. Ensure server is running at localhost:5000" | Disable execution, show connection status |
| Broker not logged in | "Broker session expired. Please login at localhost:5000" | Show login reminder, block orders |
| Order rejected | "Order rejected: {reason}" | Display reason, log, allow retry |
| Insufficient margin | "Insufficient margin. Available: ₹X, Required: ₹Y" | Block order, show alternative lot size |
| Stale signal (>90s) | "Signal expired ({age}s old). Ignoring." | Auto-reject, log for debugging |
| Duplicate signal | "Duplicate signal detected. Already processed." | Auto-ignore, log |

---

## Daily User Workflow

### Morning Setup (Before 9:15 AM)

1. **Start OpenAlgo:**
   ```bash
   cd ~/openalgo && uv run app.py
   ```

2. **Login to Broker:**
   - Open http://localhost:5000
   - Complete broker login (2FA if required)
   - Verify session is active

3. **Open Lovable App:**
   - Check connection status shows "Connected"
   - Review any overnight signals
   - Verify equity and positions

### During Trading Hours

- App automatically receives webhooks from TradingView
- Signals processed and executed (if auto-execute enabled)
- Monitor positions in real-time dashboard
- Manual order placement if needed

### End of Day (After 3:30 PM / 11:30 PM)

- Review day's trades
- Export CSV backup
- Record daily equity snapshot

---

## Questions to Confirm Before Implementing

1. Is Supabase Auth already configured in the existing app?
2. Which UI component library is being used (shadcn/ui assumed)?
3. Should the webhook URL be public (via ngrok) or local only?
4. Is there an existing design system or color scheme to follow?

---

## TaskMaster Integration

If TaskMaster is available in Lovable, use these commands to track progress:

```bash
task-master init
task-master parse-prd          # Parse this specification
task-master expand --id=1      # Break Task 1 into subtasks
task-master set-status --id=1 --status=in-progress
task-master set-status --id=1 --status=done
```

---

**END OF SPECIFICATION**

---

## Appendix: Quick Reference

### OpenAlgo API Endpoints

| Action | Method | Endpoint | Payload |
|--------|--------|----------|---------|
| Health Check | GET | `/api/v1/ping` | - |
| Place Order | POST | `/api/v1/placeorder` | `{symbol, exchange, action, quantity, price_type, product}` |
| Cancel Order | POST | `/api/v1/cancelorder` | `{order_id}` |
| Get Positions | GET | `/api/v1/positionbook` | - |
| Get Orders | GET | `/api/v1/orderbook` | - |
| Get Funds | GET | `/api/v1/funds` | - |
| Get Quotes | POST | `/api/v1/quotes` | `{symbol, exchange}` |

### TradingView Signal Types

| Type | Description |
|------|-------------|
| `BASE_ENTRY` | New position entry |
| `PYRAMID` | Adding to existing position |
| `EXIT` | Close all positions |
| `STOP_UPDATE` | Update stop loss level |

### Broker Codes

| Broker | Code |
|--------|------|
| Zerodha | `zerodha` |
| Dhan | `dhan` |
| Finvasia | `finvasia` |
| Angel One | `angel` |
| Fyers | `fyers` |
| IIFL | `iifl` |
| Kotak | `kotak` |
| Upstox | `upstox` |
