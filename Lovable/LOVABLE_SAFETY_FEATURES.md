# Lovable: Safety Features Integration

**Send THIS to Lovable** - Adds safety controls and emergency features to the frontend.

---

## PROMPT START

## New Backend Endpoints - Safety & Emergency Controls

The backend now has safety features that need frontend integration:

### 1. Emergency / Kill Switch Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/emergency/stop` | POST | **KILL SWITCH** - Pause all trading |
| `/emergency/resume` | POST | Resume trading after pause |
| `/emergency/close-all` | POST | Close ALL positions at market (dangerous!) |
| `/safety/status` | GET | Get safety manager status |
| `/sync/broker` | POST | Manually sync with broker positions |
| `/sync/status` | GET | Get broker sync status |

### 2. Updated `/health` Endpoint

The `/health` endpoint now includes safety status:

```typescript
interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  rollover_scheduler: 'running' | 'disabled';
  eod_scheduler: 'running' | 'disabled';
  voice_announcer: 'enabled' | 'disabled';
  telegram_notifier: 'enabled' | 'disabled';
  safety_manager: 'enabled' | 'disabled';
  broker_sync: 'running' | 'disabled';
  trading_paused: boolean;      // NEW: Is trading paused?
  pause_reason: string | null;  // NEW: Why trading is paused
}
```

---

## Frontend Implementation Requirements

### 1. Trading Status Banner (All Pages)

Add a **prominent banner** that shows when trading is paused:

```tsx
// Component: TradingStatusBanner
// Show at TOP of every page when trading is paused

{tradingPaused && (
  <Alert variant="destructive" className="mb-4">
    <AlertTriangle className="h-4 w-4" />
    <AlertTitle>⚠️ TRADING PAUSED</AlertTitle>
    <AlertDescription>
      {pauseReason || 'Trading has been paused'}
      <Button onClick={handleResume} className="ml-4">
        Resume Trading
      </Button>
    </AlertDescription>
  </Alert>
)}
```

### 2. Operations Page - Emergency Controls Tab

Add a new tab called **"Emergency Controls"** with:

#### A. Kill Switch Section
```tsx
<Card className="border-red-500">
  <CardHeader>
    <CardTitle className="text-red-500">🚨 Kill Switch</CardTitle>
    <CardDescription>
      Immediately pause all trading. New signals will be rejected.
    </CardDescription>
  </CardHeader>
  <CardContent>
    <div className="flex gap-4">
      <Button
        variant="destructive"
        onClick={handlePauseTrading}
        disabled={tradingPaused}
      >
        ⏸️ PAUSE TRADING
      </Button>
      <Button
        variant="outline"
        onClick={handleResumeTrading}
        disabled={!tradingPaused}
      >
        ▶️ Resume Trading
      </Button>
    </div>
    {tradingPaused && (
      <p className="text-red-500 mt-2">
        Trading paused: {pauseReason}
      </p>
    )}
  </CardContent>
</Card>
```

#### B. Emergency Close All Section
```tsx
<Card className="border-orange-500">
  <CardHeader>
    <CardTitle className="text-orange-500">⚠️ Emergency Close All</CardTitle>
    <CardDescription>
      Close ALL open positions at market price. Use with extreme caution!
    </CardDescription>
  </CardHeader>
  <CardContent>
    <div className="flex gap-4">
      <Button
        variant="outline"
        onClick={() => handleCloseAll(true)}
      >
        🔍 Preview (Dry Run)
      </Button>
      <Button
        variant="destructive"
        onClick={() => setShowCloseAllConfirm(true)}
      >
        🚨 CLOSE ALL POSITIONS
      </Button>
    </div>
  </CardContent>
</Card>

{/* Confirmation Dialog */}
<AlertDialog open={showCloseAllConfirm}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>⚠️ Are you absolutely sure?</AlertDialogTitle>
      <AlertDialogDescription>
        This will immediately close ALL {positionCount} open positions at market price.
        This action cannot be undone!
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction
        onClick={() => handleCloseAll(false)}
        className="bg-red-600 hover:bg-red-700"
      >
        Yes, Close All Positions
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

#### C. Broker Sync Section
```tsx
<Card>
  <CardHeader>
    <CardTitle>🔄 Broker Position Sync</CardTitle>
    <CardDescription>
      Compare Portfolio Manager positions with actual broker positions.
      Auto-sync runs every 5 minutes.
    </CardDescription>
  </CardHeader>
  <CardContent>
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button onClick={handleManualSync} disabled={syncing}>
          {syncing ? <Spinner /> : '🔄'} Sync Now
        </Button>
        <span className="text-sm text-muted-foreground">
          Last sync: {lastSyncTime || 'Never'}
        </span>
      </div>

      {syncResult && (
        <div className="border rounded p-4">
          <div className="flex justify-between">
            <span>PM Positions: {syncResult.pm_positions}</span>
            <span>Broker Positions: {syncResult.broker_positions}</span>
          </div>

          {syncResult.discrepancy_count > 0 ? (
            <Alert variant="destructive" className="mt-2">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Discrepancies Found!</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4 mt-2">
                  {syncResult.discrepancies.map((d, i) => (
                    <li key={i}>
                      {d.instrument}: {d.details}
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : (
            <Alert className="mt-2">
              <CheckCircle className="h-4 w-4" />
              <AlertTitle>All positions match!</AlertTitle>
            </Alert>
          )}
        </div>
      )}
    </div>
  </CardContent>
</Card>
```

### 3. API Client Updates

Add these methods to your API client:

```typescript
// lib/api-client.ts

export const apiClient = {
  // ... existing methods ...

  // Emergency Controls
  pauseTrading: (reason?: string) =>
    fetchApi('/emergency/stop', {
      method: 'POST',
      body: JSON.stringify({ reason })
    }),

  resumeTrading: () =>
    fetchApi('/emergency/resume', { method: 'POST' }),

  closeAllPositions: (dryRun: boolean = true) =>
    fetchApi('/emergency/close-all', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun })
    }),

  getSafetyStatus: () =>
    fetchApi('/safety/status'),

  // Broker Sync
  syncBroker: () =>
    fetchApi('/sync/broker', { method: 'POST' }),

  getSyncStatus: () =>
    fetchApi('/sync/status'),
};
```

### 4. TypeScript Interfaces

```typescript
// types/safety.ts

interface SafetyStatus {
  trading_paused: boolean;
  pause_reason: string | null;
  margin_warning_threshold: number;  // 50
  margin_critical_threshold: number; // 80
  price_deviation_threshold: number; // 5
  current_margin_utilization: number;
  last_prices: Record<string, number>;
}

interface SyncDiscrepancy {
  type: 'missing_in_pm' | 'missing_in_broker' | 'quantity_mismatch';
  instrument: string;
  pm_lots: number | null;
  broker_lots: number | null;
  details: string;
}

interface SyncResult {
  success: boolean;
  timestamp: string;
  pm_positions: number;
  broker_positions: number;
  discrepancy_count: number;
  discrepancies: SyncDiscrepancy[];
  error: string | null;
}

interface SyncStatus {
  sync_interval_seconds: number;
  background_sync_running: boolean;
  last_sync: {
    timestamp: string | null;
    success: boolean | null;
    pm_positions: number | null;
    broker_positions: number | null;
    discrepancy_count: number;
    error: string | null;
  } | null;
}

interface CloseAllResult {
  success: boolean;
  message: string;
  dry_run: boolean;
  positions_count: number;
  results: Array<{
    position_id: string;
    instrument: string;
    lots: number;
    status: string;
  }>;
}
```

### 5. Dashboard - Safety Status Card

Add a safety status card to the Dashboard:

```tsx
<Card>
  <CardHeader>
    <CardTitle>🛡️ Safety Status</CardTitle>
  </CardHeader>
  <CardContent>
    <div className="space-y-2">
      <div className="flex justify-between">
        <span>Trading Status</span>
        <Badge variant={tradingPaused ? 'destructive' : 'success'}>
          {tradingPaused ? '⏸️ Paused' : '✅ Active'}
        </Badge>
      </div>
      <div className="flex justify-between">
        <span>Margin Utilization</span>
        <span className={marginUtilization > 50 ? 'text-yellow-500' : ''}>
          {marginUtilization.toFixed(1)}%
        </span>
      </div>
      <div className="flex justify-between">
        <span>Broker Sync</span>
        <Badge variant={brokerSyncRunning ? 'success' : 'secondary'}>
          {brokerSyncRunning ? '🔄 Active' : 'Disabled'}
        </Badge>
      </div>
      <div className="flex justify-between">
        <span>Last Sync</span>
        <span className="text-sm text-muted-foreground">
          {lastSyncTime || 'Never'}
        </span>
      </div>
    </div>
  </CardContent>
</Card>
```

---

## Summary of Changes

1. **Trading Status Banner**: Show prominent alert when trading is paused (all pages)
2. **Operations Page**: Add "Emergency Controls" tab with:
   - Kill Switch (Pause/Resume)
   - Emergency Close All (with confirmation)
   - Broker Sync controls
3. **Dashboard**: Add Safety Status card
4. **API Client**: Add 6 new endpoint methods
5. **TypeScript Types**: Add safety-related interfaces

## PROMPT END
