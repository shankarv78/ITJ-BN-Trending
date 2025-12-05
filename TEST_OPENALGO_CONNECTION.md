# Quick Test: Verify OpenAlgo Connection

## Portfolio Manager is Running! ✅

The health endpoint responded, which means Portfolio Manager started successfully.

---

## Quick Verification Steps

### 1. Check if OpenAlgo Client Initialized

Look at the Portfolio Manager logs (where you started it) for:

```
✓ Broker client initialized successfully
OpenAlgo client initialized: http://localhost:5000
```

**If you see these messages:** ✅ OpenAlgo connection is working!

**If you see errors:** Check the error message for details.

---

### 2. Send a Test Signal

In a **new terminal**, send a test webhook:

```bash
curl -X POST http://localhost:5002/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000,
    "stop": 51650,
    "suggested_lots": 5,
    "timestamp": "2025-12-03T20:35:00Z"
  }'
```

**Expected Response:**
```json
{"status": "processed", "result": {...}}
```

**Then check Portfolio Manager logs for:**
- ✅ Signal received
- ✅ Signal validated
- ✅ Position size calculated
- ✅ (In analyzer mode, order won't execute, but will be logged)

---

### 3. Test OpenAlgo API Directly

While Portfolio Manager is running, test if the API key works:

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

headers = {'Authorization': f'Bearer {api_key}'}
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)

print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API key works! Portfolio Manager can connect to OpenAlgo.')
    data = response.json().get('data', {})
    print(f'Available cash: ₹{data.get(\"availablecash\", 0):,.2f}')
else:
    print(f'Response: {response.text[:200]}')
"
```

---

## What Success Looks Like

### In Portfolio Manager Logs:

```
============================================================
TOM BASSO PORTFOLIO - LIVE TRADING
============================================================
Broker: dhan
Loading OpenAlgo config from ...
Creating broker client: type=openalgo, broker=dhan
✓ Broker client initialized successfully
OpenAlgo client initialized: http://localhost:5000
Webhook endpoint: http://localhost:5002/webhook
```

### When You Send a Test Signal:

```
🔔 Webhook received: BASE_ENTRY Long_1
📊 Processing BASE_ENTRY: Long_1
✓ Signal validated
✓ Position size calculated: 5 lots
[In analyzer mode: Order prepared but not executed]
```

---

## If You See Errors

### "Failed to initialize broker client"
- Check API key in `openalgo_config.json`
- Verify OpenAlgo server is running
- Check API key is active in dashboard

### "401 Unauthorized" or "403 Forbidden"
- API key might be invalid
- Check API key permissions in dashboard
- Try regenerating API key

### "Connection refused"
- OpenAlgo server not running
- Start it: `cd ~/openalgo && uv run app.py`

---

## Next Steps

Once verified:

1. **Monitor logs** for a few test signals
2. **Verify position sizing** calculations
3. **Test different signal types** (BASE_ENTRY, PYRAMID, EXIT)
4. **When ready**, change `execution_mode` from `analyzer` to `semi_auto` or `auto`

---

**Last Updated:** December 2, 2025

