# Lovable AI Prompt - Tom Basso Portfolio Manager Frontend

Copy this entire prompt into Lovable AI to generate the frontend portal.

---

## PROMPT START

Build a modern React/Next.js frontend portal for a Tom Basso Portfolio Manager trading system that connects to Zerodha Kite API for live trading of Bank Nifty options and Gold Mini futures.

## SYSTEM OVERVIEW

This is a portfolio management system that:
1. Receives TradingView webhook signals for trade entries/exits/pyramids
2. Applies Tom Basso 3-constraint position sizing (Risk, Volatility, Margin)
3. Executes trades via Zerodha Kite API
4. Manages portfolio with 15% max risk cap across instruments
5. Handles automatic contract rollover near expiry
6. Stores all state in PostgreSQL database

## FRONTEND REQUIREMENTS

### 1. Dashboard (Home)
- Real-time portfolio equity curve chart
- Current portfolio metrics:
  - Total equity, closed equity, unrealized P&L
  - Portfolio risk % (with 15% hard limit indicator - show red when approaching limit)
  - Portfolio volatility %
  - Margin utilization %
- Active positions summary cards (Bank Nifty & Gold Mini)
- Recent signals feed (last 10 signals)
- System health indicators (webhook status, broker connection, database status)

### 2. Positions Page
- Table of all open positions with columns:
  - Position ID, Instrument, Entry Price, Current Price
  - Lots, Quantity, Stop Level
  - Unrealized P&L (color coded: green for profit, red for loss)
  - Risk Contribution %
  - Rollover status, Days to Expiry
- Closed positions history with date range filters
- Position detail modal showing full trade history
- Actions: Close position, Adjust stop level

### 3. Signals Page
- Real-time signal log table with columns:
  - Timestamp, Instrument, Signal Type (BASE_ENTRY/PYRAMID/EXIT/EOD_MONITOR)
  - Position (Long_1 through Long_6), Price, Stop, Lots
  - Validation status (accepted/rejected/blocked) with color badges
  - Request ID for tracking
- Signal detail modal showing full JSON payload
- Duplicate detection statistics panel
- Filter by instrument, signal type, date range

### 4. Risk Management Page
- Tom Basso 3-constraint visualization with gauges:
  - Risk-based lots calculator (Lot-R)
  - Volatility-based lots calculator (Lot-V)
  - Margin-based lots calculator (Lot-M)
  - Final lots = MIN(Lot-R, Lot-V, Lot-M)
- Pyramid gate status cards per instrument:
  - Instrument gate (1R profit requirement)
  - Portfolio gate (12% risk block threshold)
  - Profit gate status
- ATR trailing stop visualization per position showing:
  - Entry price, Initial stop, Current stop, Highest close

### 5. Configuration Page
- Portfolio settings form (editable with save):
  - Initial capital (INR)
  - Max portfolio risk % (default: 15%)
  - Max volatility % (default: 5%)
  - Max margin utilization % (default: 60%)
- Instrument settings per instrument (Bank Nifty, Gold Mini):
  - Lot size, Point value, Margin per lot
  - Initial/Ongoing risk percentages
  - Initial/Ongoing volatility percentages
  - Initial/Trailing ATR multipliers
- Zerodha API settings:
  - API Key input (masked)
  - API Secret input (masked)
  - Access token status indicator (valid/expired)
  - Session expiry countdown
  - Login/Re-authenticate button
- Signal validation settings toggle

### 6. Analytics Page
- Performance metrics cards:
  - Total P&L, Win rate, Average win/loss ratio
  - Sharpe ratio, Max drawdown, Recovery factor
  - P&L by instrument breakdown (pie chart)
- Charts section:
  - Equity curve with drawdown overlay (line + area chart)
  - P&L distribution histogram
  - Position sizing distribution (bar chart)
  - Risk utilization over time (line chart)
- Date range selector for all analytics

### 7. Operations Page
- Rollover Management section:
  - Candidates list showing positions approaching expiry
  - Days to expiry countdown for each
  - Manual rollover trigger button with dry-run option
  - Rollover history log table
- EOD (End-of-Day) Execution Status:
  - Current status indicator
  - Next execution time
  - Recent EOD execution log
- System Logs Viewer:
  - Filterable log viewer (INFO, WARNING, ERROR levels)
  - Search functionality
- Manual Intervention Tools:
  - Force close position button
  - Adjust stop level form
  - Sync from broker button (reconcile positions)

## BACKEND REQUIREMENTS

### 1. Zerodha Kite API Integration

Create a Python backend with `zerodha_client.py` that implements:

```python
from kiteconnect import KiteConnect

class ZerodhaClient:
    def __init__(self, api_key: str, api_secret: str):
        self.kite = KiteConnect(api_key=api_key)
        self.api_secret = api_secret
        
    def get_login_url(self) -> str:
        """Generate Kite login URL for OAuth"""
        return self.kite.login_url()
        
    def generate_session(self, request_token: str) -> dict:
        """Exchange request_token for access_token"""
        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        self.kite.set_access_token(data["access_token"])
        return data
        
    def set_access_token(self, access_token: str):
        """Set access token directly"""
        self.kite.set_access_token(access_token)
        
    def place_order(self, tradingsymbol: str, transaction_type: str, quantity: int,
                    order_type: str = "MARKET", product: str = "NRML",
                    price: float = None, exchange: str = "NFO") -> str:
        """Place order via Kite API"""
        return self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,  # BUY or SELL
            quantity=quantity,
            product=product,  # NRML, MIS, CNC
            order_type=order_type,  # MARKET, LIMIT, SL, SL-M
            price=price
        )
        
    def modify_order(self, order_id: str, price: float = None, 
                     quantity: int = None) -> str:
        """Modify existing order"""
        params = {"order_id": order_id, "variety": self.kite.VARIETY_REGULAR}
        if price: params["price"] = price
        if quantity: params["quantity"] = quantity
        return self.kite.modify_order(**params)
        
    def cancel_order(self, order_id: str) -> str:
        """Cancel order"""
        return self.kite.cancel_order(
            variety=self.kite.VARIETY_REGULAR,
            order_id=order_id
        )
        
    def get_orders(self) -> list:
        """Get all orders for the day"""
        return self.kite.orders()
        
    def get_order_history(self, order_id: str) -> list:
        """Get order history/status"""
        return self.kite.order_history(order_id)
        
    def get_positions(self) -> dict:
        """Get net and day positions"""
        return self.kite.positions()
        
    def get_holdings(self) -> list:
        """Get holdings"""
        return self.kite.holdings()
        
    def get_quote(self, instruments: list) -> dict:
        """Get LTP/quotes for instruments"""
        return self.kite.quote(instruments)
        
    def get_ltp(self, instruments: list) -> dict:
        """Get only LTP for instruments"""
        return self.kite.ltp(instruments)
        
    def get_margins(self) -> dict:
        """Get available margin/funds"""
        return self.kite.margins()
        
    def get_instruments(self, exchange: str = None) -> list:
        """Get instrument list for symbol mapping"""
        return self.kite.instruments(exchange)
```

Key Zerodha-specific requirements:
- OAuth2 login flow (redirect to Kite login page, handle callback)
- Access token management (expires daily at 3:30 AM IST - need daily re-login)
- Instrument token mapping for websocket streaming
- Exchange codes: NFO (Bank Nifty options), MCX (Gold Mini futures)
- Product types: NRML (overnight/positional), MIS (intraday)
- Order types: MARKET, LIMIT, SL (stop-loss), SL-M (stop-loss market)
- Rate limits: 3 requests/second for most APIs

### 2. API Endpoints (FastAPI Backend)

```python
# Authentication
POST /api/auth/zerodha/login     # Returns Kite login URL
GET  /api/auth/zerodha/callback  # OAuth callback - exchanges request_token
GET  /api/auth/status            # Check if session is valid
POST /api/auth/logout            # Clear session

# Portfolio
GET  /api/portfolio/status       # Current portfolio state (equity, risk, etc.)
GET  /api/portfolio/equity-curve # Historical equity data for charting
GET  /api/portfolio/metrics      # Detailed risk/volatility metrics

# Positions
GET  /api/positions              # All positions (query: status=open|closed)
GET  /api/positions/{id}         # Single position detail
POST /api/positions/{id}/close   # Force close a position
PATCH /api/positions/{id}/stop   # Adjust stop level

# Signals
GET  /api/signals                # Signal log (query: page, limit, instrument, type)
GET  /api/signals/{id}           # Single signal detail with full payload
GET  /api/signals/stats          # Validation statistics (accepted, rejected, blocked counts)

# Webhook (from TradingView - keep existing)
POST /api/webhook                # Receive trading signals

# Risk
GET  /api/risk/constraints       # Current Tom Basso constraint values
GET  /api/risk/pyramid-gates     # Pyramid gate status per instrument

# Configuration
GET  /api/config                 # Get all configuration
PATCH /api/config                # Update configuration

# Operations
GET  /api/rollover/candidates    # Positions approaching expiry
POST /api/rollover/execute       # Execute rollover (query: dry_run=true|false)
GET  /api/rollover/history       # Rollover execution history
GET  /api/eod/status             # EOD execution status
POST /api/sync/broker            # Sync positions from Zerodha

# Health
GET  /api/health                 # System health check (DB, broker, webhook)
```

### 3. Database Schema

PostgreSQL database with existing tables plus Zerodha session table:

```sql
-- Existing tables (from portfolio_manager):
-- portfolio_positions, portfolio_state, pyramiding_state, signal_log, instance_metadata

-- New table for Zerodha sessions
CREATE TABLE zerodha_sessions (
    id SERIAL PRIMARY KEY,
    api_key VARCHAR(50) NOT NULL,
    api_secret_hash VARCHAR(256),  -- Store hashed, not plaintext
    access_token TEXT,
    public_token TEXT,
    user_id VARCHAR(50),
    login_time TIMESTAMP,
    token_expiry TIMESTAMP,  -- Always 3:30 AM IST next day
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Equity curve history for analytics
CREATE TABLE equity_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    closed_equity DECIMAL(15,2) NOT NULL,
    open_equity DECIMAL(15,2),
    unrealized_pnl DECIMAL(15,2),
    total_risk_percent DECIMAL(8,4),
    total_vol_percent DECIMAL(8,4),
    margin_used DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_equity_timestamp ON equity_history(timestamp);
```

### 4. WebSocket for Real-time Updates

Implement WebSocket connections for:
- Position price updates (from Zerodha KiteTicker)
- P&L recalculation in real-time
- Signal notifications (new signal received)
- Portfolio metrics refresh
- Broker connection status changes

Use Zerodha's KiteTicker for market data streaming:
```python
from kiteconnect import KiteTicker

def on_ticks(ws, ticks):
    # Broadcast to frontend WebSocket clients
    for tick in ticks:
        # Update position prices, calculate P&L
        pass

ticker = KiteTicker(api_key, access_token)
ticker.on_ticks = on_ticks
ticker.subscribe([instrument_tokens])
ticker.set_mode(ticker.MODE_LTP, [instrument_tokens])
```

## TECH STACK

Frontend:
- Next.js 14 with App Router
- TypeScript
- Tailwind CSS + shadcn/ui components
- TanStack Query (React Query) for data fetching and caching
- Recharts or Tremor for charts
- Socket.io-client for WebSocket

Backend:
- FastAPI (Python)
- SQLAlchemy ORM
- kiteconnect Python SDK (pip install kiteconnect)
- psycopg2-binary for PostgreSQL
- python-socketio for WebSocket server
- Redis for caching (optional but recommended)

## DATA MODELS

### Enums
```typescript
enum InstrumentType {
  GOLD_MINI = "GOLD_MINI",
  BANK_NIFTY = "BANK_NIFTY"
}

enum SignalType {
  BASE_ENTRY = "BASE_ENTRY",
  PYRAMID = "PYRAMID", 
  EXIT = "EXIT",
  EOD_MONITOR = "EOD_MONITOR"
}

enum PositionStatus {
  OPEN = "open",
  CLOSED = "closed",
  PARTIAL = "partial"
}

enum RolloverStatus {
  NONE = "none",
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  ROLLED = "rolled",
  FAILED = "failed"
}
```

### Interfaces
```typescript
interface Signal {
  id: string;
  timestamp: string;
  instrument: InstrumentType;
  signalType: SignalType;
  position: string;  // Long_1 through Long_6
  price: number;
  stop: number;
  lots: number;
  atr: number;
  er: number;  // Efficiency ratio
  supertrend: number;
  roc?: number;
  reason?: string;  // For EXIT signals
  validationStatus: "accepted" | "rejected" | "blocked" | "duplicate";
  requestId: string;
}

interface Position {
  positionId: string;
  instrument: InstrumentType;
  status: PositionStatus;
  entryTimestamp: string;
  entryPrice: number;
  currentPrice: number;
  lots: number;
  quantity: number;
  initialStop: number;
  currentStop: number;
  highestClose: number;
  unrealizedPnl: number;
  realizedPnl: number;
  riskContribution: number;
  volContribution: number;
  atr: number;
  limiter?: string;
  isBasePosition: boolean;
  // Rollover fields
  rolloverStatus: RolloverStatus;
  expiry?: string;
  strike?: number;
  daysToExpiry?: number;
  // Bank Nifty synthetic futures
  peSymbol?: string;
  ceSymbol?: string;
  // Gold Mini futures
  futuresSymbol?: string;
  contractMonth?: string;
}

interface PortfolioState {
  timestamp: string;
  equity: number;
  closedEquity: number;
  openEquity: number;
  blendedEquity: number;
  unrealizedPnl: number;
  // Risk metrics
  totalRiskAmount: number;
  totalRiskPercent: number;
  goldRiskPercent: number;
  bankniftyRiskPercent: number;
  // Volatility metrics
  totalVolAmount: number;
  totalVolPercent: number;
  // Margin
  marginUsed: number;
  marginAvailable: number;
  marginUtilizationPercent: number;
  // Position counts
  openPositionCount: number;
  goldPositionCount: number;
  bankniftyPositionCount: number;
}

interface TomBassoConstraints {
  lotR: number;  // Risk-based lots
  lotV: number;  // Volatility-based lots
  lotM: number;  // Margin-based lots
  finalLots: number;  // MIN(lotR, lotV, lotM) floored
  limiter: "risk" | "volatility" | "margin";
}

interface PyramidGateStatus {
  instrument: InstrumentType;
  allowed: boolean;
  instrumentGate: boolean;  // 1R profit gate
  portfolioGate: boolean;   // 12% risk block
  profitGate: boolean;
  reason: string;
  priceMoveR: number;
  atrSpacing: number;
  portfolioRiskPct: number;
}

interface InstrumentConfig {
  name: string;
  instrumentType: InstrumentType;
  lotSize: number;
  pointValue: number;
  marginPerLot: number;
  initialRiskPercent: number;
  ongoingRiskPercent: number;
  initialVolPercent: number;
  ongoingVolPercent: number;
  initialAtrMult: number;
  trailingAtrMult: number;
  maxPyramids: number;
}
```

## IMPORTANT BUSINESS RULES

1. **Portfolio Risk Cap**: 15% hard limit - block ALL new entries when exceeded
2. **Pyramid Blocking**: Block new pyramids at 12% portfolio risk
3. **1R Profit Gate**: Require price to move 1R (initial risk) in profit before first pyramid
4. **ATR Trailing Stops**: Stops only move UP for long positions, NEVER down
5. **Bank Nifty Synthetic Futures**: Uses options combo (sell PE + buy CE at same strike)
6. **Gold Mini Futures**: Direct MCX futures contracts
7. **Auto-Rollover**: 
   - Bank Nifty: 7 days before expiry
   - Gold Mini: 8 days before expiry (tender period)
8. **Duplicate Detection**: 60-second window for same signal deduplication
9. **Position Layers**: Maximum 6 layers (Long_1 base + Long_2 to Long_6 pyramids)
10. **Zerodha Session**: Access token expires at 3:30 AM IST daily - must re-authenticate

## UI/UX GUIDELINES

1. Use a dark theme optimized for trading (dark background, high contrast)
2. Color scheme: 
   - Profit: Green (#22c55e)
   - Loss: Red (#ef4444)
   - Warning: Amber (#f59e0b)
   - Info: Blue (#3b82f6)
3. Real-time data should pulse/highlight on update
4. Critical alerts (risk limit, session expiry) should use toast notifications
5. Mobile responsive design for monitoring on-the-go
6. Keyboard shortcuts for common actions
7. Loading states and error boundaries for all async operations

## PROMPT END

---

## Next Steps After Generation

1. Share the Python files listed in `FILES_TO_SHARE.md` with Lovable AI
2. Share the Zerodha API documentation links
3. Set up PostgreSQL database using the provided schema
4. Configure Zerodha Kite Connect API credentials
5. Set up TradingView webhook URL pointing to the deployed backend
