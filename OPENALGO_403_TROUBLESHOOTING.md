# OpenAlgo 403 Forbidden Error - Troubleshooting

## Issue: Getting 403 Forbidden on API Calls

If you're getting 403 errors when testing OpenAlgo connection, here's how to troubleshoot:

---

## Quick Checks

### 1. Verify API Key Format

OpenAlgo API keys typically start with `oa_` and are 64+ characters long.

Check your API key:
```bash
cd portfolio_manager
python3 -c "import json; config = json.load(open('openalgo_config.json')); key = config.get('openalgo_api_key', ''); print(f'Starts with oa_: {key.startswith(\"oa_\")}'); print(f'Length: {len(key)}')"
```

**Expected:**
- Starts with `oa_`
- Length: 64+ characters

---

### 2. Verify API Key in Dashboard

1. Open OpenAlgo dashboard: http://localhost:5000
2. Go to **Settings → API Keys**
3. Check if your API key is listed and **active**
4. Verify the key matches what's in `openalgo_config.json`

---

### 3. Test API Key Directly

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

# Test funds endpoint (requires auth)
headers = {'Authorization': f'Bearer {api_key}'}
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)

print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API key is valid!')
    print(f'Response: {response.json()}')
elif response.status_code == 403:
    print('✗ 403 Forbidden - API key might be invalid')
    print('Check:')
    print('  1. API key is correct in dashboard')
    print('  2. API key is copied correctly (no extra spaces)')
    print('  3. API key hasn\'t been revoked')
else:
    print(f'Unexpected status: {response.status_code}')
"
```

---

## Common Causes

### Cause 1: API Key Not Generated Yet

**Solution:**
1. Go to OpenAlgo dashboard → Settings → API Keys
2. Generate a new API key
3. Copy it immediately (shown only once)
4. Update `openalgo_config.json`

### Cause 2: API Key Copied Incorrectly

**Solution:**
- Check for extra spaces before/after the key
- Ensure entire key is copied (64+ characters)
- Re-copy from dashboard if needed

### Cause 3: API Key Revoked or Expired

**Solution:**
- Check dashboard if key is still active
- Generate a new API key if needed
- Update config file with new key

### Cause 4: Health Endpoint Requires Special Permissions

**Note:** Some OpenAlgo endpoints might require specific permissions. The health endpoint might not be publicly accessible.

**Solution:**
- Try other endpoints like `/api/v1/funds` (requires auth)
- If funds endpoint works, your API key is valid
- Health endpoint 403 might be expected behavior

---

## Testing Without Health Endpoint

If health endpoint gives 403, test with an endpoint that definitely requires auth:

```bash
# Test funds endpoint (this requires valid API key)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:5000/api/v1/funds
```

**If this returns 200:** Your API key is valid, health endpoint might just require different permissions.

**If this also returns 403:** API key is likely invalid - regenerate it.

---

## Verify Integration is Working

Even if health endpoint gives 403, your integration might still work. Test by:

1. **Start Portfolio Manager:**
   ```bash
   cd portfolio_manager
   ./start_portfolio_manager.sh
   ```

2. **Check logs for connection:**
   - Look for "OpenAlgo client initialized" message
   - No authentication errors

3. **Send test signal:**
   - If Portfolio Manager starts without errors, integration is working
   - The 403 on health endpoint might not be critical

---

## Next Steps

1. ✅ Verify API key format and length
2. ✅ Check API key is active in dashboard
3. ✅ Test with `/api/v1/funds` endpoint (requires auth)
4. ✅ If funds works, health endpoint 403 might be OK
5. ✅ Try starting Portfolio Manager - if it works, integration is fine

---

## Summary

**403 on health endpoint might not be a blocker** if:
- API key format is correct
- Other endpoints work (like `/api/v1/funds`)
- Portfolio Manager starts without errors

The health endpoint might require special permissions or might not be publicly accessible. Focus on testing endpoints that your Portfolio Manager will actually use.

---

**Last Updated:** December 2, 2025

