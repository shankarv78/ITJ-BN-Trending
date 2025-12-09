# Lovable Fix: Signals + Performance Optimizations

**Send THIS to Lovable** - fixes for current frontend issues.

---

## PROMPT START

## 1. Performance: Reduce Polling & Smart Refresh

### Problem
Frequent polling (every 5 seconds) puts unnecessary load on the backend. We need to:
1. **Only poll when the page is active/visible**
2. **Reduce polling frequency** (15-30 seconds instead of 5)
3. **Make Refresh buttons work** for immediate updates

### Implementation Requirements

#### A. Page-Specific Polling (Only when page is visible)
```typescript
// Only fetch data when this specific page is active
const { data, refetch, isLoading } = useQuery({
  queryKey: ['status'],
  queryFn: () => apiClient.getPortfolioStatus(),
  refetchInterval: 30000,  // 30 seconds, not 5
  refetchIntervalInBackground: false,  // STOP polling when tab is hidden
  enabled: true,  // Can be tied to page visibility
});
```

#### B. Polling Intervals by Page (Recommended)
| Page | Endpoint | Polling Interval | Notes |
|------|----------|------------------|-------|
| Dashboard | `/status`, `/positions`, `/health` | 30 seconds | Main overview |
| Positions | `/positions` | 30 seconds | Or manual refresh only |
| Signals | `/signals`, `/webhook/stats` | 60 seconds | Historical data |
| Analytics | `/trades`, `/status` | 60 seconds | Historical data |
| Risk | `/status` | 30 seconds | Risk metrics |
| Configuration | `/config` | **No polling** | Static data, fetch once |
| Operations | `/health`, `/positions` | 30 seconds | System status |

#### C. Working Refresh Buttons
Every page with a "Refresh" button should call `refetch()`:

```typescript
// In your page component
const { data, refetch, isLoading, isFetching } = useQuery({...});

// Refresh button handler
<Button
  onClick={() => refetch()}
  disabled={isFetching}
>
  {isFetching ? <Spinner /> : <RefreshIcon />}
  Refresh
</Button>
```

#### D. Stop Polling When Page Not Visible
Use React Query's built-in support or add visibility detection:

```typescript
import { useQuery } from '@tanstack/react-query';

// This automatically stops polling when tab is hidden
const { data } = useQuery({
  queryKey: ['status'],
  queryFn: fetchStatus,
  refetchInterval: 30000,
  refetchIntervalInBackground: false,  // KEY: stops when tab hidden
});
```

#### E. Page-Level Data Fetching
Only fetch data relevant to the current page:

```typescript
// Dashboard.tsx - fetches dashboard-specific data
useQuery({ queryKey: ['status'], ... });
useQuery({ queryKey: ['positions'], ... });
useQuery({ queryKey: ['health'], ... });

// Analytics.tsx - fetches analytics-specific data (different!)
useQuery({ queryKey: ['trades'], ... });
useQuery({ queryKey: ['status'], ... });  // For equity display

// Configuration.tsx - fetch ONCE, no polling
useQuery({
  queryKey: ['config'],
  queryFn: () => apiClient.getConfig(),
  staleTime: Infinity,  // Never refetch automatically
  refetchInterval: false,  // No polling
});
```

---

## 2. Bug Fix: Dashboard "Recent Signals" Not Using /signals Endpoint

The `/signals` endpoint **ALREADY EXISTS** in the backend, but the Dashboard shows "Signal history will be available when the /signals endpoint is implemented."

### The endpoint IS available:

```
GET /signals?limit=10
```

**Example Response:**
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
  "limit": 10
}
```

### Fix Required:

1. **Dashboard page**: Remove the placeholder "Signal history will be available..." message
2. **Call the API**: Use `apiClient.getSignals(10)` to fetch recent signals
3. **Display in Recent Signals section**: Show the last 5-10 signals with timestamp, instrument, type, and status

### API Client (already exists, just use it):

```typescript
// In your API client
getSignals: (limit = 50, instrument?: string, status?: string) => {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (instrument) params.append('instrument', instrument);
  if (status) params.append('status', status);
  return fetchApi(`/signals?${params}`);
}

// Usage in Dashboard component
const { data: signalsData } = useQuery({
  queryKey: ['signals', 10],
  queryFn: () => apiClient.getSignals(10),
  refetchInterval: 5000
});
```

---

## Endpoints Status Summary

### ✅ IMPLEMENTED (use these now):
| Endpoint | Use In |
|----------|--------|
| `GET /signals` | Dashboard Recent Signals, Signals page Signal Log |
| `GET /trades` | Analytics Trade History (already working!) |
| `GET /status` | Dashboard metrics (already working!) |
| `GET /positions` | Positions page (already working!) |
| `GET /health` | System Health (already working!) |
| `GET /config` | Configuration page (already working!) |
| `GET /webhook/stats` | Signals page stats (already working!) |

### ❌ NOT YET IMPLEMENTED (keep placeholders):
| Endpoint | Page | Keep showing "waiting for..." |
|----------|------|------------------------------|
| `GET /equity` | Dashboard Equity Curve | Yes |
| `GET /risk/constraints` | Risk page - Tom Basso 3-Constraint | Yes |
| `GET /risk/pyramid-gates` | Risk page - Pyramid Gate Status | Yes |
| `GET /rollover/history` | Operations - Rollover History | Yes |
| `GET /logs` | Operations - System Logs | Yes |
| `GET /eod/status` | Operations - EOD Status | Yes |

---

## Summary of Changes Needed

### Performance (Priority 1)
1. **Reduce polling intervals**: 30 seconds for most pages, 60 seconds for historical data
2. **Stop polling when tab hidden**: Set `refetchIntervalInBackground: false`
3. **Fix Refresh buttons**: Wire them to call `refetch()` and show loading state
4. **Configuration page**: No polling - fetch once on mount

### Bug Fixes (Priority 2)
5. **Dashboard Recent Signals**: Connect to `GET /signals?limit=10` - endpoint EXISTS
6. **Keep all other placeholders** - those endpoints don't exist yet

### Expected Result
- Backend load reduced by ~80% (30s vs 5s polling)
- No polling when user switches to another browser tab
- Refresh buttons provide immediate updates when clicked
- Better user experience with loading indicators

## PROMPT END
