# Lovable: Emergency Controls & Holiday Calendar Update

**Send THIS to Lovable** - Adds authenticated emergency controls and holiday calendar management.

---

## PROMPT START

## Critical Update: API Key Authentication for Emergency Endpoints

The emergency endpoints now require authentication via `X-API-KEY` header. This prevents unauthorized access to critical trading controls.

### Environment Variable Setup

Add this to your Lovable project's environment variables:

```
VITE_EMERGENCY_API_KEY=<YOUR_KEY_HERE>
```

**Replace `<YOUR_KEY_HERE>` with the actual key I'll provide.**
EMERGENCY_API_KEY="964a99e357f681e8f3111c0c94933007840b52c1d4e2c0970bce6cd750e46480"
---

## 1. Update API Client with Authentication

Update your API client to include the API key for emergency endpoints:

```typescript
// lib/api-client.ts

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;
const EMERGENCY_API_KEY = import.meta.env.VITE_EMERGENCY_API_KEY;

// Helper for authenticated emergency requests
const fetchEmergencyApi = async (endpoint: string, options: RequestInit = {}) => {
  const response = await fetch(`${BACKEND_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-KEY': EMERGENCY_API_KEY || '',
      ...options.headers,
    },
  });

  if (response.status === 401) {
    throw new Error('Unauthorized: Invalid API key for emergency endpoint');
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
};

export const apiClient = {
  // ... existing methods ...

  // Emergency Controls (AUTHENTICATED)
  pauseTrading: (reason?: string) =>
    fetchEmergencyApi('/emergency/stop', {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Manual stop via frontend' })
    }),

  resumeTrading: () =>
    fetchEmergencyApi('/emergency/resume', { method: 'POST' }),

  closeAllPositions: (dryRun: boolean = true) =>
    fetchEmergencyApi('/emergency/close-all', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun })
    }),

  // Safety Status (no auth required)
  getSafetyStatus: () =>
    fetchApi('/safety/status'),

  // Broker Sync (no auth required)
  syncBroker: () =>
    fetchApi('/sync/broker', { method: 'POST' }),

  getSyncStatus: () =>
    fetchApi('/sync/status'),

  // Holiday Calendar (no auth required)
  getHolidayStatus: () =>
    fetchApi('/holidays/status'),

  getHolidays: (exchange: 'NSE' | 'MCX', year?: number) =>
    fetchApi(`/holidays/${exchange}${year ? `?year=${year}` : ''}`),

  addHoliday: (exchange: 'NSE' | 'MCX', date: string, description: string) =>
    fetchApi(`/holidays/${exchange}`, {
      method: 'POST',
      body: JSON.stringify({ date, description })
    }),

  removeHoliday: (exchange: 'NSE' | 'MCX', date: string) =>
    fetchApi(`/holidays/${exchange}/${date}`, { method: 'DELETE' }),
};
```

---

## 2. Emergency Controls Component Update

Update your Emergency Controls to handle authentication errors:

```tsx
// components/EmergencyControls.tsx

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ui/use-toast';

export function EmergencyControls() {
  const [loading, setLoading] = useState(false);
  const [tradingPaused, setTradingPaused] = useState(false);
  const { toast } = useToast();

  const handlePauseTrading = async () => {
    setLoading(true);
    try {
      await apiClient.pauseTrading('Manual stop via frontend');
      setTradingPaused(true);
      toast({
        title: 'Trading Paused',
        description: 'All new signals will be rejected.',
        variant: 'destructive',
      });
    } catch (error) {
      if (error.message.includes('Unauthorized')) {
        toast({
          title: 'Authentication Failed',
          description: 'Invalid API key. Check VITE_EMERGENCY_API_KEY.',
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Error',
          description: error.message,
          variant: 'destructive',
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResumeTrading = async () => {
    setLoading(true);
    try {
      await apiClient.resumeTrading();
      setTradingPaused(false);
      toast({
        title: 'Trading Resumed',
        description: 'Signals will now be processed.',
      });
    } catch (error) {
      if (error.message.includes('Unauthorized')) {
        toast({
          title: 'Authentication Failed',
          description: 'Invalid API key for emergency endpoint.',
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Error',
          description: error.message,
          variant: 'destructive',
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCloseAll = async (dryRun: boolean) => {
    setLoading(true);
    try {
      const result = await apiClient.closeAllPositions(dryRun);
      if (dryRun) {
        toast({
          title: 'Preview Complete',
          description: `Would close ${result.positions_count} positions.`,
        });
      } else {
        toast({
          title: 'Positions Closed',
          description: `Closed ${result.positions_count} positions.`,
          variant: 'destructive',
        });
      }
    } catch (error) {
      if (error.message.includes('Unauthorized')) {
        toast({
          title: 'Authentication Failed',
          description: 'Invalid API key for close-all endpoint.',
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Error',
          description: error.message,
          variant: 'destructive',
        });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Kill Switch */}
      <Card className="border-red-500">
        <CardHeader>
          <CardTitle className="text-red-500 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Kill Switch
          </CardTitle>
          <CardDescription>
            Immediately pause all trading. New signals will be rejected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <Button
              variant="destructive"
              onClick={handlePauseTrading}
              disabled={loading || tradingPaused}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              PAUSE TRADING
            </Button>
            <Button
              variant="outline"
              onClick={handleResumeTrading}
              disabled={loading || !tradingPaused}
            >
              Resume Trading
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Emergency Close All */}
      <Card className="border-orange-500">
        <CardHeader>
          <CardTitle className="text-orange-500 flex items-center gap-2">
            <AlertOctagon className="h-5 w-5" />
            Emergency Close All
          </CardTitle>
          <CardDescription>
            Close ALL open positions at market price. Use with extreme caution!
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <Button
              variant="outline"
              onClick={() => handleCloseAll(true)}
              disabled={loading}
            >
              Preview (Dry Run)
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" disabled={loading}>
                  CLOSE ALL POSITIONS
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will immediately close ALL open positions at market price.
                    This action cannot be undone!
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => handleCloseAll(false)}
                    className="bg-red-600 hover:bg-red-700"
                  >
                    Yes, Close All
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

---

## 3. NEW: Holiday Calendar Management

Add a Holiday Calendar section to the Operations page:

### TypeScript Types

```typescript
// types/holidays.ts

interface Holiday {
  date: string;        // ISO format: "2025-12-25"
  exchange: 'NSE' | 'MCX';
  description: string;
}

interface HolidayStatus {
  today: string;
  nse: {
    is_holiday: boolean;
    reason: string;
  };
  mcx: {
    is_holiday: boolean;
    reason: string;
  };
  total_holidays: number;
}

interface HolidaysResponse {
  exchange: 'NSE' | 'MCX';
  year: number | null;
  count: number;
  holidays: Holiday[];
}
```

### Holiday Calendar Component

```tsx
// components/HolidayCalendar.tsx

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { format } from 'date-fns';

export function HolidayCalendar() {
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [selectedExchange, setSelectedExchange] = useState<'NSE' | 'MCX'>('NSE');
  const [newDate, setNewDate] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [holidayStatus, setHolidayStatus] = useState<HolidayStatus | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    loadHolidays();
    loadStatus();
  }, [selectedExchange]);

  const loadHolidays = async () => {
    try {
      const response = await apiClient.getHolidays(selectedExchange);
      setHolidays(response.holidays);
    } catch (error) {
      toast({ title: 'Error loading holidays', variant: 'destructive' });
    }
  };

  const loadStatus = async () => {
    try {
      const status = await apiClient.getHolidayStatus();
      setHolidayStatus(status);
    } catch (error) {
      console.error('Error loading holiday status:', error);
    }
  };

  const handleAddHoliday = async () => {
    if (!newDate || !newDescription) return;

    try {
      await apiClient.addHoliday(selectedExchange, newDate, newDescription);
      toast({ title: 'Holiday added successfully' });
      setNewDate('');
      setNewDescription('');
      loadHolidays();
    } catch (error) {
      toast({ title: 'Error adding holiday', variant: 'destructive' });
    }
  };

  const handleRemoveHoliday = async (date: string) => {
    try {
      await apiClient.removeHoliday(selectedExchange, date);
      toast({ title: 'Holiday removed' });
      loadHolidays();
    } catch (error) {
      toast({ title: 'Error removing holiday', variant: 'destructive' });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="h-5 w-5" />
          Holiday Calendar
        </CardTitle>
        <CardDescription>
          Manage market holidays for NSE and MCX. Trading is blocked on holidays.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Today's Status Banner */}
        {holidayStatus && (holidayStatus.nse.is_holiday || holidayStatus.mcx.is_holiday) && (
          <Alert variant="destructive" className="mb-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>TODAY IS A HOLIDAY</AlertTitle>
            <AlertDescription>
              {holidayStatus.nse.is_holiday && <div>NSE: {holidayStatus.nse.reason}</div>}
              {holidayStatus.mcx.is_holiday && <div>MCX: {holidayStatus.mcx.reason}</div>}
            </AlertDescription>
          </Alert>
        )}

        {/* Exchange Selector */}
        <Tabs value={selectedExchange} onValueChange={(v) => setSelectedExchange(v as 'NSE' | 'MCX')}>
          <TabsList>
            <TabsTrigger value="NSE">NSE (Bank Nifty)</TabsTrigger>
            <TabsTrigger value="MCX">MCX (Gold Mini)</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Add Holiday Form */}
        <div className="flex gap-2 mt-4">
          <Input
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.target.value)}
            className="w-40"
          />
          <Input
            placeholder="Description (e.g., Diwali)"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            className="flex-1"
          />
          <Button onClick={handleAddHoliday}>
            <Plus className="h-4 w-4 mr-1" />
            Add
          </Button>
        </div>

        {/* Holidays List */}
        <div className="mt-4 border rounded-lg">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="w-20">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {holidays.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    No holidays configured for {selectedExchange}
                  </TableCell>
                </TableRow>
              ) : (
                holidays.map((holiday) => (
                  <TableRow key={`${holiday.exchange}-${holiday.date}`}>
                    <TableCell>
                      {format(new Date(holiday.date), 'MMM dd, yyyy (EEE)')}
                    </TableCell>
                    <TableCell>{holiday.description}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveHoliday(holiday.date)}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <p className="text-sm text-muted-foreground mt-4">
          Note: Weekends (Saturday & Sunday) are automatically blocked - no need to add them.
        </p>
      </CardContent>
    </Card>
  );
}
```

---

## 4. Dashboard Holiday Banner

Add a holiday warning banner to the Dashboard if today is a holiday:

```tsx
// In Dashboard.tsx

const [holidayStatus, setHolidayStatus] = useState<HolidayStatus | null>(null);

useEffect(() => {
  apiClient.getHolidayStatus().then(setHolidayStatus);
}, []);

// In the render:
{holidayStatus && (holidayStatus.nse.is_holiday || holidayStatus.mcx.is_holiday) && (
  <Alert variant="warning" className="mb-4 bg-yellow-50 border-yellow-300">
    <CalendarX className="h-4 w-4" />
    <AlertTitle>Market Holiday</AlertTitle>
    <AlertDescription>
      {holidayStatus.nse.is_holiday && (
        <span className="block">NSE (Bank Nifty): {holidayStatus.nse.reason}</span>
      )}
      {holidayStatus.mcx.is_holiday && (
        <span className="block">MCX (Gold Mini): {holidayStatus.mcx.reason}</span>
      )}
      <span className="block text-sm mt-1">Signals will be rejected today.</span>
    </AlertDescription>
  </Alert>
)}
```

---

## 5. Operations Page Layout Update

Update the Operations page to include all new sections:

```tsx
// pages/Operations.tsx

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmergencyControls } from '@/components/EmergencyControls';
import { BrokerSync } from '@/components/BrokerSync';
import { HolidayCalendar } from '@/components/HolidayCalendar';

export default function Operations() {
  return (
    <div className="container mx-auto py-6">
      <h1 className="text-2xl font-bold mb-6">Operations</h1>

      <Tabs defaultValue="emergency" className="space-y-4">
        <TabsList>
          <TabsTrigger value="emergency">Emergency Controls</TabsTrigger>
          <TabsTrigger value="sync">Broker Sync</TabsTrigger>
          <TabsTrigger value="holidays">Holiday Calendar</TabsTrigger>
          <TabsTrigger value="rollover">Rollover</TabsTrigger>
        </TabsList>

        <TabsContent value="emergency">
          <EmergencyControls />
        </TabsContent>

        <TabsContent value="sync">
          <BrokerSync />
        </TabsContent>

        <TabsContent value="holidays">
          <HolidayCalendar />
        </TabsContent>

        <TabsContent value="rollover">
          {/* Existing rollover content */}
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

---

## Summary of Changes

| Feature | What to Implement |
|---------|-------------------|
| **API Key Auth** | Add `X-API-KEY` header to emergency endpoint calls |
| **Emergency Controls** | Update to handle 401 Unauthorized errors |
| **Holiday Calendar** | New component to manage NSE/MCX holidays |
| **Holiday Banner** | Show warning on Dashboard when today is holiday |
| **Operations Page** | Add "Holiday Calendar" tab |

## Environment Variables Required

```
VITE_BACKEND_URL=https://webhook.shankarvasudevan.com
VITE_EMERGENCY_API_KEY=<YOUR_KEY_HERE>
```

## PROMPT END
