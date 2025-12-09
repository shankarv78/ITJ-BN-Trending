# Lovable Fix: Performance Optimizations

**Send THIS to Lovable** - reduces backend load and improves UX.

---

## PROMPT START

## Performance: Reduce Polling & Smart Refresh

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
  enabled: true,
});
```

#### B. Updated Polling Intervals (Changes from Current)
| Hook | Endpoint | Current | Change To | Reason |
|------|----------|---------|-----------|--------|
| usePortfolioStatus | `/status` | 10s | **30s** | Reduce load |
| usePositions | `/positions` | 10s | **30s** | Reduce load |
| useSystemHealth | `/health` | 30s | 30s ✓ | Keep |
| useWebhookStats | `/webhook/stats` | 15s | **30s** | Historical data |
| useBackendConnection | `/health` | 30s | 30s ✓ | Keep |
| useConfig | `/config` | No polling ✓ | Keep | Already correct |
| useSignals | `/signals` | 15s | **30s** | Historical data |
| useTrades | `/trades` | 30s | 30s ✓ | Keep |

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
Use React Query's built-in support:

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

// Analytics.tsx - fetches analytics-specific data
useQuery({ queryKey: ['trades'], ... });
useQuery({ queryKey: ['status'], ... });

// Configuration.tsx - fetch ONCE, no polling
useQuery({
  queryKey: ['config'],
  queryFn: () => apiClient.getConfig(),
  staleTime: Infinity,  // Never refetch automatically
  refetchInterval: false,  // No polling
});
```

---

## Summary of Changes Needed

1. **Reduce polling intervals**: 30 seconds for most pages, 60 seconds for historical data
2. **Stop polling when tab hidden**: Set `refetchIntervalInBackground: false`
3. **Fix Refresh buttons**: Wire them to call `refetch()` and show loading state
4. **Configuration page**: No polling - fetch once on mount

### Expected Result
- Backend load reduced by ~80% (30s vs 5s polling)
- No polling when user switches to another browser tab
- Refresh buttons provide immediate updates when clicked
- Better user experience with loading indicators

## PROMPT END
