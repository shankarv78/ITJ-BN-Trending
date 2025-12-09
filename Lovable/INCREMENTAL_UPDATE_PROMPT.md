# Incremental Update Prompt for Lovable

Copy this prompt to Lovable to clarify the architecture and correct any issues.

---

## PROMPT START

## CRITICAL CORRECTIONS

### 1. DO NOT Use Lovable Cloud or Edge Functions

**WRONG approach:**
- Lovable Cloud database
- Edge functions as proxy to Python backend
- Supabase integration

**CORRECT approach:**
- Direct HTTPS calls to my external Python backend
- No database in Lovable - my backend has PostgreSQL
- No proxy - frontend calls backend directly

```typescript
// CORRECT - Direct call to backend
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:5002';
const response = await fetch(`${BACKEND_URL}/status`);

// WRONG - Don't use edge functions or proxy
// const response = await supabase.functions.invoke('proxy', {...});
```

### 2. Keep EOD_MONITOR Signal Type

EOD_MONITOR **exists** in my backend. Do NOT remove it:

```typescript
// CORRECT - Keep all 4 signal types
enum SignalType {
  BASE_ENTRY = "BASE_ENTRY",
  PYRAMID = "PYRAMID",
  EXIT = "EXIT",
  EOD_MONITOR = "EOD_MONITOR"  // KEEP THIS!
}
```

This matches my backend at `core/models.py`:
```python
class SignalType(Enum):
    BASE_ENTRY = "BASE_ENTRY"
    PYRAMID = "PYRAMID"
    EXIT = "EXIT"
    EOD_MONITOR = "EOD_MONITOR"  # It exists!
```

### 3. Position.currentPrice is Optional (Calculated at Runtime)

`currentPrice` is NOT stored in the database - it's fetched from broker at runtime.

```typescript
interface Position {
  positionId: string;
  instrument: string;
  entryPrice: number;
  currentPrice?: number;  // Optional - calculated at runtime from broker quote
  lots: number;
  // ... other fields
}
```

The `/positions` endpoint will include `currentPrice` when the broker is connected.

### 4. Signal.suggestedLots (Not lots)

The Signal model uses `suggestedLots` (from `suggested_lots` in Python):

```typescript
interface Signal {
  timestamp: string;
  instrument: string;
  signalType: SignalType;
  position: string;
  price: number;
  stop: number;
  suggestedLots: number;  // NOT "lots"
  atr: number;
  er: number;
  supertrend: number;
  roc?: number;
  reason?: string;
}
```

---

## Architecture Clarification

This is a **frontend-only** project for Lovable. The Python backend already exists and will run separately.

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LOVABLE (This Project)                    │
│                                                              │
│   React/Next.js Frontend Dashboard                          │
│   - Portfolio visualization                                  │
│   - Position management UI                                   │
│   - Signal monitoring                                        │
│   - Configuration pages                                      │
│                                                              │
│   Hosted on: Lovable                                        │
│   Database: NONE (backend handles it)                       │
│   Edge Functions: NONE (direct API calls)                   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ Direct REST API Calls (HTTPS)
                              │ NO PROXY / NO EDGE FUNCTIONS
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  EXTERNAL PYTHON BACKEND                     │
│                  (Already exists - NOT in Lovable)           │
│                                                              │
│   Flask server: portfolio_manager.py                        │
│   Database: PostgreSQL (managed by backend)                 │
│   Running on: Mac (dev) → AWS/GCP (production)              │
│   Exposed via: Cloudflare Tunnel or public URL              │
│                                                              │
│   Backend URL (configurable):                                │
│   - Dev: https://your-tunnel.trycloudflare.com              │
│   - Prod: https://api.yourdomain.com                        │
└─────────────────────────────────────────────────────────────┘
```

### What Lovable Should Generate

**DO generate:**
- React/Next.js frontend with all dashboard pages
- TypeScript interfaces matching the Python data models exactly
- API client/hooks to call the external backend DIRECTLY
- Environment variable for `NEXT_PUBLIC_BACKEND_URL`
- Beautiful UI with Tailwind + shadcn/ui
- Loading states when backend is unreachable
- Connection status indicator

**DO NOT generate:**
- Lovable Cloud database setup
- Supabase integration
- Edge functions
- Proxy functions
- Any backend/server code
- Database schemas in Lovable

### API Client Configuration

Create an API client that calls the backend DIRECTLY:

```typescript
// lib/api-client.ts

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:5002';

// Helper for fetch with error handling
async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BACKEND_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export const apiClient = {
  // Portfolio
  getPortfolioStatus: () => fetchApi('/status'),
  getPositions: () => fetchApi('/positions'),

  // Signals
  getSignalStats: () => fetchApi('/webhook/stats'),

  // Health
  getHealth: () => fetchApi('/health'),

  // Database
  getDBStatus: () => fetchApi('/db/status'),

  // Rollover
  getRolloverStatus: () => fetchApi('/rollover/status'),
  scanRolloverCandidates: () => fetchApi('/rollover/scan'),
  executeRollover: (dryRun: boolean) =>
    fetchApi('/rollover/execute', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun })
    }),

  // EOD
  getEODStatus: () => fetchApi('/eod/status'),

  // Analyzer (for testing mode)
  getAnalyzerOrders: () => fetchApi('/analyzer/orders'),

  // History (NEW)
  getSignals: (limit = 50, instrument?: string, status?: string) => {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (instrument) params.append('instrument', instrument);
    if (status) params.append('status', status);
    return fetchApi(`/signals?${params}`);
  },
  getTrades: (limit = 50, instrument?: string, status = 'closed') => {
    const params = new URLSearchParams({ limit: limit.toString(), status });
    if (instrument) params.append('instrument', instrument);
    return fetchApi(`/trades?${params}`);
  },
};
```

### Environment Variables

Only ONE environment variable needed:

```env
# Backend API URL - the ONLY config needed
NEXT_PUBLIC_BACKEND_URL=http://localhost:5002

# For production:
# NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com
```

NO Supabase URL, NO Supabase key, NO database connection strings.

### Existing Backend Endpoints (Already Implemented)

The Python backend at `portfolio_manager.py` provides these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Portfolio status (equity, risk %, positions count) |
| `/positions` | GET | All open positions with details |
| `/webhook` | POST | Receives TradingView signals (not called by frontend) |
| `/webhook/stats` | GET | Signal processing statistics |
| `/health` | GET | System health check |
| `/db/status` | GET | Database connection status |
| `/rollover/status` | GET | Rollover scheduler status |
| `/rollover/scan` | GET | Scan for rollover candidates |
| `/rollover/execute` | POST | Execute rollover (body: `{dry_run: bool}`) |
| `/eod/status` | GET | EOD pre-close execution status |
| `/analyzer/orders` | GET | Simulated orders (analyzer mode only) |
| `/config` | GET | Configuration settings (read-only) |
| `/signals` | GET | Signal history (query: `?limit=50&instrument=GOLD_MINI&status=executed`) |
| `/trades` | GET | Trade/position history (query: `?limit=50&instrument=GOLD_MINI&status=closed`) |
| `/voice/status` | GET | Voice announcer status & pending errors |
| `/voice/acknowledge` | POST | Acknowledge errors (body: `{errorId?: string}`) |
| `/voice/test` | POST | Test voice announcement (body: `{type: "pre_trade" | "post_trade" | "error"}`) |

### Response Formats (from existing backend)

**GET /status**
```json
{
  "equity": 5250000.0,
  "positions": 3,
  "risk_pct": 8.5,
  "stats": {
    "signals_received": 45,
    "entries_executed": 12,
    "pyramids_executed": 8,
    "exits_executed": 5
  }
}
```

**GET /positions**
```json
{
  "positions": {
    "GOLD_MINI_Long_1": {
      "instrument": "GOLD_MINI",
      "lots": 2,
      "entry_price": 78500.0,
      "current_stop": 77800.0,
      "expiry": "2025-01-05",
      "strike": null,
      "rollover_status": "none",
      "rollover_count": 0
    },
    "BANK_NIFTY_Long_1": {
      "instrument": "BANK_NIFTY",
      "lots": 1,
      "entry_price": 52000.0,
      "current_stop": 51200.0,
      "expiry": "2024-12-25",
      "strike": 52000,
      "rollover_status": "none",
      "rollover_count": 0
    }
  }
}
```

**GET /health**
```json
{
  "status": "healthy",
  "timestamp": "2024-12-07T15:30:00",
  "rollover_scheduler": "running",
  "eod_scheduler": "running"
}
```

**GET /webhook/stats**
```json
{
  "webhook": {
    "duplicate_detector": {
      "signals_checked": 100,
      "duplicates_found": 5
    },
    "total_received": 100,
    "duplicates_ignored": 5
  },
  "execution": {
    "entries_executed": 12,
    "pyramids_executed": 8,
    "exits_executed": 5,
    "entries_blocked": 3,
    "pyramids_blocked": 2
  }
}
```

**GET /signals** (NEW - Signal History)
```json
{
  "signals": [
    {
      "id": 123,
      "instrument": "GOLD_MINI",
      "signalType": "BASE_ENTRY",
      "position": "Long_1",
      "signalTimestamp": "2025-12-05T15:40:00Z",
      "status": "executed",
      "processedAt": "2025-12-05T15:40:01Z",
      "price": 130051.67,
      "stop": 128511.24,
      "suggestedLots": 3
    }
  ],
  "count": 1,
  "limit": 50
}
```

**GET /trades** (NEW - Trade/Position History)
```json
{
  "trades": [
    {
      "id": "manual_gold_20251205_1540",
      "instrument": "GOLD_MINI",
      "status": "closed",
      "entryTimestamp": "2025-12-05T15:40:00Z",
      "entryPrice": 130051.67,
      "lots": 3,
      "quantity": 300,
      "initialStop": 128511.24,
      "currentStop": 128511.24,
      "highestClose": 130051.67,
      "unrealizedPnl": 0,
      "realizedPnl": -27200.10,
      "atr": 1540.43,
      "isBasePosition": true,
      "rolloverStatus": "none",
      "rolloverCount": 0,
      "expiry": null,
      "strike": null,
      "futuresSymbol": "GOLDM25FEBFUT",
      "contractMonth": "2025-02",
      "createdAt": "2025-12-05T15:40:00Z",
      "updatedAt": "2025-12-05T16:30:00Z",
      "exitTimestamp": "2025-12-05T16:30:00Z",
      "exitPrice": 129145.00,
      "exitReason": "STOP_LOSS"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Correct TypeScript Types

```typescript
// Signal types - KEEP ALL 4
export enum SignalType {
  BASE_ENTRY = "BASE_ENTRY",
  PYRAMID = "PYRAMID",
  EXIT = "EXIT",
  EOD_MONITOR = "EOD_MONITOR"  // KEEP THIS
}

// Instrument types
export enum InstrumentType {
  GOLD_MINI = "GOLD_MINI",
  BANK_NIFTY = "BANK_NIFTY"
}

// Position status
export enum PositionStatus {
  OPEN = "open",
  CLOSED = "closed",
  PARTIAL = "partial"
}

// Rollover status
export enum RolloverStatus {
  NONE = "none",
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  ROLLED = "rolled",
  FAILED = "failed"
}

// Signal interface
export interface Signal {
  timestamp: string;
  instrument: InstrumentType;
  signalType: SignalType;
  position: string;  // Long_1 through Long_6
  price: number;
  stop: number;
  suggestedLots: number;  // NOT "lots"
  atr: number;
  er: number;
  supertrend: number;
  roc?: number;
  reason?: string;  // Required for EXIT signals
}

// Position interface
export interface Position {
  positionId: string;
  instrument: InstrumentType;
  status: PositionStatus;
  entryTimestamp: string;
  entryPrice: number;
  currentPrice?: number;  // Optional - calculated at runtime
  lots: number;
  quantity: number;
  initialStop: number;
  currentStop: number;
  highestClose: number;
  unrealizedPnl?: number;
  realizedPnl: number;
  riskContribution?: number;
  volContribution?: number;
  atr: number;
  limiter?: string;
  isBasePosition: boolean;
  // Rollover
  rolloverStatus: RolloverStatus;
  expiry?: string;
  strike?: number;
  rolloverCount: number;
  // Bank Nifty synthetic
  peSymbol?: string;
  ceSymbol?: string;
  // Gold Mini futures
  futuresSymbol?: string;
  contractMonth?: string;
}

// Portfolio state
export interface PortfolioState {
  timestamp: string;
  equity: number;
  closedEquity: number;
  openEquity: number;
  blendedEquity: number;
  totalRiskAmount: number;
  totalRiskPercent: number;
  goldRiskPercent: number;
  bankniftyRiskPercent: number;
  totalVolAmount: number;
  totalVolPercent: number;
  marginUsed: number;
  marginAvailable: number;
  marginUtilizationPercent: number;
}
```

### Newly Implemented Endpoints

These endpoints are NOW AVAILABLE:

```
GET  /config                   - Get all configuration (READ-ONLY)
```

**Configuration Endpoint Response Structure:**

```typescript
interface ConfigResponse {
  instruments: {
    [key: string]: {
      name: string;
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
  };
  portfolio: {
    maxPortfolioRiskPercent: number;
    maxPortfolioVolPercent: number;
    maxMarginUtilizationPercent: number;
  };
  pyramidGates: {
    riskWarning: number;
    riskBlock: number;
    volBlock: number;
    use1RGate: boolean;
    atrPyramidSpacing: number;
  };
  equity: {
    mode: string;  // 'closed' | 'open' | 'blended'
    blendedUnrealizedWeight: number;
  };
  rollover: {
    enabled: boolean;
    bankNiftyDays: number;
    goldMiniDays: number;
    initialBufferPct: number;
    incrementPct: number;
    maxRetries: number;
    retryIntervalSec: number;
    strikeInterval: number;
    prefer1000s: boolean;
  };
  marketHours: {
    nseStart: string;
    nseEnd: string;
    mcxStart: string;
    mcxEnd: string;
    mcxSummerClose: string;
    mcxWinterClose: string;
  };
  eod: {
    enabled: boolean;
    monitoringStartMinutes: number;
    conditionCheckSeconds: number;
    executionSeconds: number;
    trackingSeconds: number;
    orderTimeout: number;
    trackingPollInterval: number;
    limitBufferPct: number;
    fallbackToMarket: boolean;
    fallbackSeconds: number;
    maxSignalAgeSeconds: number;
    marketCloseTimes: { [key: string]: string };
    instrumentsEnabled: { [key: string]: boolean };
  };
  execution: {
    strategy: string;
    signalValidationEnabled: boolean;
    partialFillStrategy: string;
    partialFillWaitTimeout: number;
  };
  peelOff: {
    enabled: boolean;
    checkInterval: number;
  };
  _meta: {
    readOnly: boolean;  // Always true
    note: string;
    timestamp: string;
  };
}
```

### IMPORTANT: Configuration Page is READ-ONLY

The Configuration page should:
1. **Fetch config** from `GET /config` endpoint
2. **Display all settings** in a clean, organized UI (grouped by category)
3. **Remove all "Save" buttons** - no editing allowed
4. **Show read-only notice**: "Configuration is read-only. Changes require backend restart."
5. **No input fields** - only display values

### Broker Status Correction

The frontend shows "Zerodha Status" but the backend uses **OpenAlgo** middleware. Update the UI:
- Change "Zerodha Status" → "Broker Status" or "OpenAlgo Status"
- The `/status` endpoint returns broker connection through OpenAlgo

### New Endpoints (To Be Added to Backend Later)

These endpoints don't exist yet. Show "Coming Soon" placeholder for features that need them:

```
GET  /api/signals              - Signal log with pagination
GET  /api/signals/:id          - Single signal detail
GET  /api/risk/constraints     - Tom Basso constraint values
GET  /api/risk/pyramid-gates   - Pyramid gate status per instrument
GET  /api/portfolio/equity-curve - Historical equity data
POST /api/positions/:id/close  - Force close position
PATCH /api/positions/:id/stop  - Adjust stop level
```

### Summary of Corrections

1. **Remove Lovable Cloud / Supabase** - Not needed, backend has database
2. **Remove Edge Functions** - Direct API calls only
3. **Keep EOD_MONITOR** - It exists in backend
4. **Use suggestedLots** - Not "lots" in Signal interface
5. **currentPrice is optional** - Calculated at runtime from broker
6. **Single env var** - Only `NEXT_PUBLIC_BACKEND_URL` needed
7. **Config page is READ-ONLY** - No save functionality, just display
8. **Broker Status** - Show "Broker Status" not "Zerodha Status" (uses OpenAlgo)

## PROMPT END
