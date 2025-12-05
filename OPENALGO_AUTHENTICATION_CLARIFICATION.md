# OpenAlgo Authentication - Important Clarification

## Understanding OpenAlgo Authentication

Based on OpenAlgo documentation and codebase analysis:

### Two Separate Authentication Systems

1. **Dashboard Login (Username/Password)**
   - Used to access the OpenAlgo web dashboard
   - Required to view settings, connect brokers, manage API keys
   - **NOT required for API calls** - this is only for web UI access

2. **API Key Authentication**
   - Used for programmatic API access (Portfolio Manager, scripts, etc.)
   - **Only the API key is needed** - no username/password required
   - Sent as `Authorization: Bearer YOUR_API_KEY` header

---

## The 403 Error - Possible Causes

Since you're getting 403 with your API key, here are the most likely causes:

### 1. API Key Not Activated/Enabled

**Check in Dashboard:**
1. Login to OpenAlgo dashboard (username/password)
2. Go to **Settings → API Keys**
3. Check if your API key shows as **"Active"** or **"Enabled"**
4. If it shows as inactive, you may need to activate it

### 2. API Key Format Issue

Your API key starts with `c116680631...` (64 characters). This might be:
- A registration token (not an API key)
- An API key that needs to be activated
- A different type of key

**What to check:**
- In the dashboard, look for "Show/Hide API Key" button
- Click it to reveal the full key
- Verify it matches what you copied
- Check if there's a "Regenerate" or "Activate" button

### 3. User Account Status

The API key might be tied to your user account status:
- Account might need email verification
- Account might be in "pending" status
- First-time setup might require additional steps

**Check:**
- Look for any account status indicators in dashboard
- Check for verification emails
- See if there are any setup completion steps

---

## Correct Authentication Flow

### For API Calls (Portfolio Manager):

```python
# Only API key is needed - NO username/password
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}
response = requests.get(url, headers=headers)
```

### For Dashboard Access:

```
1. Open http://localhost:5000
2. Enter username and password
3. Access dashboard features
```

**These are separate!** Dashboard login is NOT required for API calls.

---

## Troubleshooting Steps

### Step 1: Verify API Key in Dashboard

1. **Login to dashboard** (username/password)
2. Go to **Settings → API Keys**
3. **Click "Show/Hide API Key"** to reveal the key
4. **Copy it again** - make sure you get the complete key
5. Check if there's an **"Activate"** or **"Enable"** button

### Step 2: Check API Key Status

Look for indicators like:
- ✅ Active / ❌ Inactive
- Enabled / Disabled
- Status: Active / Pending / Expired

### Step 3: Try Regenerating API Key

If the key seems inactive:
1. Click **"Regenerate API Key"** button
2. Copy the new key immediately
3. Update `openalgo_config.json` with new key
4. Test again

### Step 4: Check Account Status

In the dashboard, look for:
- Account verification status
- Setup completion steps
- Any warnings or notices

---

## Testing with Correct Authentication

Once you have the correct, active API key:

```bash
cd portfolio_manager
python3 -c "
import json
import requests

config = json.load(open('openalgo_config.json'))
api_key = config.get('openalgo_api_key')
base_url = config.get('openalgo_url', 'http://localhost:5000')

# Test with API key only (no username/password)
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

# Try funds endpoint
response = requests.get(f'{base_url}/api/v1/funds', headers=headers)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API key works!')
    print(response.json())
else:
    print(f'Error: {response.status_code}')
    print(response.text[:200])
"
```

---

## Key Points

✅ **API key alone should work** - no username/password needed for API calls  
✅ **Dashboard login is separate** - only for web UI access  
✅ **403 error suggests** - API key might be inactive or invalid  
✅ **Check dashboard** - verify key status and regenerate if needed  

---

## Next Steps

1. **Login to dashboard** (username/password)
2. **Go to Settings → API Keys**
3. **Click "Show/Hide"** to see full key
4. **Check if key is Active/Enabled**
5. **If inactive, try "Regenerate API Key"**
6. **Copy new key and update config**
7. **Test again**

---

**Last Updated:** December 2, 2025

