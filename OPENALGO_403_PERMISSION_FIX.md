# OpenAlgo 403 Permission Error - Solutions

## Understanding 403 vs 401

According to [OpenAlgo HTTP Status Codes documentation](https://docs.openalgo.in/api-documentation/v1/http-status-codes):
- **401** = Authorization error (authentication failed - wrong API key)
- **403** = Permission error (authenticated but lacks permissions)

Since you're getting **403**, your API key is being **recognized** (authentication works), but there's a **permission issue**.

---

## Possible Causes for 403 (Even as Admin)

### 1. Health Endpoint Doesn't Exist

**Important:** `/api/v1/health` is **not a valid endpoint** in OpenAlgo!

**Valid endpoints to test:**
- `/api/v1/ping` - Returns "Pong" (works with API key)
- `/api/v1/funds` - Get available margin (requires API key)

**Solution:** Use `/api/v1/ping` to test server connectivity:

```bash
# Test with ping endpoint (valid endpoint)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:5000/api/v1/ping

# Should return "Pong" if API key is valid

# Test with funds endpoint (requires full permissions)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:5000/api/v1/funds
```

If ping works (200 with "Pong"), your API key is valid!

---

### 2. API Key Order Mode Restrictions

OpenAlgo API keys have an `order_mode` setting:
- `auto` - Full trading permissions
- `semi_auto` - Requires manual approval
- `analyzer` - Read-only, no trading

**Check in Dashboard:**
1. Go to **Settings → API Keys**
2. Check your API key's **Order Mode** setting
3. Some endpoints might require specific order modes

---

### 3. IP Banning

According to [OpenAlgo Security documentation](https://docs.openalgo.in/security/ban-ip), repeated invalid attempts can ban your IP.

**Check:**
1. Go to http://localhost:5000/security
2. Check if your IP is banned
3. Unban if necessary

---

### 4. Rate Limiting

[OpenAlgo rate limits](https://docs.openalgo.in/api-documentation/v1/rate-limiting) are 50 API calls/second. Exceeding can cause 403.

**Check:**
- Are you making too many requests?
- Wait a few seconds and try again

---

## Recommended Testing Approach

### Step 1: Test a Different Endpoint

Instead of health endpoint, test with an endpoint that definitely requires API key:

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

headers = {'Authorization': f'Bearer {api_key}'}

# Test funds endpoint (requires valid API key)
print('Testing /api/v1/funds endpoint...')
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)
print(f'Status: {response.status_code}')

if response.status_code == 200:
    print('✓ API key works! Health endpoint might just be restricted.')
    print(f'Available cash: {response.json().get(\"data\", {}).get(\"availablecash\", \"N/A\")}')
elif response.status_code == 403:
    print('✗ 403 on funds too - check API key permissions in dashboard')
elif response.status_code == 401:
    print('✗ 401 - API key is invalid')
else:
    print(f'Status: {response.status_code}')
    print(response.text[:200])
"
```

### Step 2: Check API Key Settings in Dashboard

1. **Login to dashboard** (username/password)
2. **Go to Settings → API Keys**
3. **Check:**
   - Is API key **Active/Enabled**?
   - What is the **Order Mode**? (auto/semi_auto/analyzer)
   - Are there any **permission restrictions**?

### Step 3: Try Regenerating API Key

If settings look correct but still 403:
1. **Regenerate API key** in dashboard
2. **Copy new key**
3. **Update** `openalgo_config.json`
4. **Test again**

---

## Important: Health Endpoint Doesn't Exist

**The `/api/v1/health` endpoint is NOT a valid OpenAlgo endpoint!**

Use these endpoints instead:
- `/api/v1/ping` - Returns "Pong" (tests API key validity)
- `/api/v1/funds` - Get available margin (requires full permissions)

**If `/api/v1/ping` works (returns "Pong"), your API key is valid and integration will work!**

The Portfolio Manager will use endpoints like:
- `/api/v1/funds` - Get available margin
- `/api/v1/placeorder` - Place orders
- `/api/v1/positionbook` - Get positions

These should work with your API key even if health endpoint doesn't.

---

## Quick Test: Start Portfolio Manager

Even if health endpoint gives 403, try starting Portfolio Manager:

```bash
cd portfolio_manager
./start_portfolio_manager.sh
```

**Check the logs:**
- If you see "OpenAlgo client initialized" - connection works!
- If you see authentication errors - then there's an issue
- If Portfolio Manager starts successfully - integration is working!

---

## Summary

**403 = Permission Error** (not authentication error)

**Most likely causes:**
1. Health endpoint is restricted (try other endpoints)
2. API key order mode restrictions
3. IP ban (check /security)
4. Rate limiting

**Next steps:**
1. Test `/api/v1/funds` endpoint instead of health
2. Check API key settings in dashboard
3. Try starting Portfolio Manager - if it works, integration is fine!

---

**References:**
- [OpenAlgo HTTP Status Codes](https://docs.openalgo.in/api-documentation/v1/http-status-codes)
- [OpenAlgo Rate Limiting](https://docs.openalgo.in/api-documentation/v1/rate-limiting)
- [OpenAlgo Security - Ban IP](https://docs.openalgo.in/security/ban-ip)

---

**Last Updated:** December 2, 2025

