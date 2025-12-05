# OpenAlgo Connection Verification Guide

## How to Verify Portfolio Manager is Connected to OpenAlgo

After starting Portfolio Manager, here's how to verify it's successfully talking to OpenAlgo:

---

## Step 1: Check Startup Logs

When Portfolio Manager starts, look for these success indicators in the logs:

### ✅ Success Indicators:

```
============================================================
TOM BASSO PORTFOLIO - LIVE TRADING
============================================================
Broker: dhan
Mode: LIVE
Creating broker client: type=openalgo, broker=dhan
✓ Broker client initialized successfully
OpenAlgo client initialized: http://localhost:5000
Webhook endpoint: http://localhost:5002/webhook
```

**Key messages to look for:**
- ✅ `"Creating broker client: type=openalgo"` - Broker factory working
- ✅ `"✓ Broker client initialized successfully"` - OpenAlgo client created
- ✅ `"OpenAlgo client initialized: http://localhost:5000"` - Connection established
- ✅ `"Webhook endpoint: http://localhost:5002/webhook"` - Server started

### ❌ Error Indicators:

```
✗ Failed to initialize broker client: ...
✗ OpenAlgo client initialization failed
✗ Connection refused
✗ 401 Unauthorized
✗ 403 Forbidden
```

---

## Step 2: Test OpenAlgo Connection Directly

While Portfolio Manager is running, test the connection in another terminal:

### Test 1: Check Webhook Server

```bash
# Test if webhook server is running
curl http://localhost:5002/health

# Expected response:
# {"status": "healthy", ...}
```

### Test 2: Test OpenAlgo API (via Portfolio Manager's client)

The Portfolio Manager should be able to call OpenAlgo. Check the logs when it tries to get funds or place orders.

---

## Step 3: Send a Test Signal

Send a test webhook signal to verify end-to-end flow:

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
    "timestamp": "2025-12-02T10:30:00Z"
  }'
```

### What to Look For in Logs:

**✅ Success:**
```
🔔 Webhook received: BASE_ENTRY Long_1
📊 Processing BASE_ENTRY: Long_1
✓ Signal validated
✓ Position size calculated: 5 lots
✓ Order sent to OpenAlgo
```

**❌ Errors:**
```
✗ Invalid signal
✗ Failed to connect to OpenAlgo
✗ API key authentication failed
✗ Order placement failed
```

---

## Step 4: Check OpenAlgo Server Logs

In the OpenAlgo server terminal, you should see:

**✅ Success:**
```
[INFO] API request received: GET /api/v1/funds
[INFO] API key validated
[INFO] Request processed successfully
```

**❌ Errors:**
```
[ERROR] Invalid API key
[ERROR] 403 Forbidden
[ERROR] Authentication failed
```

---

## Step 5: Verify API Key is Working

Test the API key directly (while Portfolio Manager is running):

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

# Test funds endpoint (what Portfolio Manager uses)
headers = {'Authorization': f'Bearer {api_key}'}
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)

print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API key works! Portfolio Manager can connect.')
    data = response.json().get('data', {})
    print(f'Available cash: ₹{data.get(\"availablecash\", 0):,.2f}')
elif response.status_code == 403:
    print('✗ 403 - API key permission issue')
    print('Check dashboard: Settings → API Keys → Order Mode')
elif response.status_code == 401:
    print('✗ 401 - API key is invalid')
else:
    print(f'Response: {response.text[:200]}')
"
```

---

## Step 6: Monitor Portfolio Manager Logs

Watch the Portfolio Manager logs in real-time:

```bash
# If running in foreground, logs appear in terminal
# If running in background, check log file:
tail -f portfolio_manager.log
```

**Look for:**
- Webhook requests received
- Signal processing
- OpenAlgo API calls
- Order placement attempts
- Any error messages

---

## Quick Verification Checklist

- [ ] Portfolio Manager started without errors
- [ ] Logs show "OpenAlgo client initialized"
- [ ] Webhook server responding on port 5002
- [ ] Test signal processed successfully
- [ ] No authentication errors in logs
- [ ] OpenAlgo server shows API requests

---

## Troubleshooting

### If Portfolio Manager starts but can't connect:

1. **Check OpenAlgo is running:**
   ```bash
   curl http://localhost:5000/api/v1/ping
   # Should return "Pong" (if using POST with API key in body)
   ```

2. **Check API key in config:**
   ```bash
   cat portfolio_manager/openalgo_config.json | grep api_key
   ```

3. **Check logs for specific errors:**
   ```bash
   tail -50 portfolio_manager.log | grep -i "error\|failed\|403\|401"
   ```

### If test signal fails:

1. Check webhook server is running
2. Verify signal format is correct
3. Check Portfolio Manager logs for validation errors
4. Verify OpenAlgo connection in logs

---

## Expected Behavior in Analyzer Mode

Since `execution_mode` is set to `analyzer`:

- ✅ Signals will be **processed and validated**
- ✅ Position sizes will be **calculated**
- ✅ Orders will be **prepared**
- ❌ Orders will **NOT be executed** (analyzer mode)
- ✅ Everything will be **logged** for review

This is perfect for testing! You can verify the entire flow without placing real trades.

---

## Next Steps After Verification

Once you confirm everything works:

1. **Monitor for a few days** in analyzer mode
2. **Review logs** to ensure signals are processed correctly
3. **Verify position sizing** calculations
4. **Test with different signal types** (BASE_ENTRY, PYRAMID, EXIT)
5. **When ready**, change `execution_mode` to `semi_auto` or `auto`

---

**Last Updated:** December 2, 2025

