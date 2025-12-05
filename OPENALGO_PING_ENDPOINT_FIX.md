# OpenAlgo Ping Endpoint - Correct Usage

## Important Discovery

You found that:
- ❌ `/api/v1/health` is **NOT a valid endpoint**
- ✅ `/api/v1/ping` **IS a valid endpoint** and works in API Playground

---

## Why Ping Works in Playground But Not With API Key

The API Playground likely uses **session-based authentication** (from your dashboard login), not API key authentication.

**This means:**
- When you're logged into the dashboard, the Playground uses your session cookie
- API key authentication might work differently or require different setup

---

## Correct Ping Endpoint Usage

According to [OpenAlgo API Documentation](https://docs.openalgo.in/api-documentation/v1/accounts-api/ping):

**Method:** POST  
**Body:** JSON with API key
```json
{
  "apikey": "your_api_key_here"
}
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "pong"
}
```

---

## Testing Your API Key

Since ping works in Playground but not with API key, there are two possibilities:

### Possibility 1: API Key Needs Activation

The API key from registration might need to be activated in the dashboard.

**Check:**
1. Login to dashboard
2. Go to **Settings → API Keys**
3. Look for "Activate" or "Enable" button
4. Or try "Regenerate API Key" to get a new active key

### Possibility 2: API Key Format Issue

The registration API key might be in a different format than what's needed for API calls.

**Solution:**
- Regenerate API key from dashboard
- Copy the new key
- Update `openalgo_config.json`

---

## Alternative: Test With Funds Endpoint

Instead of ping, test with an endpoint that Portfolio Manager will actually use:

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

# Test funds endpoint (what Portfolio Manager will use)
headers = {'Authorization': f'Bearer {api_key}'}
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)

print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API key works! Portfolio Manager will work.')
    print(response.json())
elif response.status_code == 403:
    print('✗ 403 - Check API key permissions in dashboard')
elif response.status_code == 401:
    print('✗ 401 - API key is invalid')
"
```

---

## Key Insight

**If ping works in Playground:**
- Your OpenAlgo server is running correctly ✅
- The endpoint exists and is accessible ✅
- The issue is with API key authentication, not the server

**Next Steps:**
1. Check API key status in dashboard
2. Try regenerating API key
3. Test with `/api/v1/funds` endpoint (what Portfolio Manager uses)
4. If funds works, your integration is fine!

---

## Summary

- ✅ `/api/v1/ping` is the correct endpoint (not `/api/v1/health`)
- ✅ Ping works in Playground (session auth)
- ⚠️  Ping returns 403 with API key (key might need activation)
- ✅ Test with `/api/v1/funds` instead (what Portfolio Manager uses)

**The real test:** Can Portfolio Manager connect and use the API? That's what matters!

---

**Last Updated:** December 2, 2025

