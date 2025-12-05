# OpenAlgo API Key Setup Guide

## ✅ You've Connected Dhan Broker - Next Step: Generate API Key

After successfully connecting your Dhan broker to OpenAlgo, you need to generate an **OpenAlgo API key**. This is different from your Dhan credentials and is used by Portfolio Manager to authenticate with OpenAlgo.

---

## Step-by-Step: Generate OpenAlgo API Key

### Step 1: Navigate to API Keys Section

1. In the OpenAlgo dashboard (http://localhost:5000)
2. Go to **Settings** (usually in the top menu or sidebar)
3. Click on **API Keys** or **API Management**

### Step 2: Generate New API Key

1. Click **"Generate New API Key"** or **"Create API Key"** button
2. You may be asked to:
   - Give it a name/description (e.g., "Portfolio Manager")
   - Set expiration (optional - can leave blank for no expiration)
   - Set permissions (usually defaults are fine)

3. Click **"Generate"** or **"Create"**

### Step 3: Copy and Save the API Key

⚠️ **IMPORTANT:** The API key will be shown **only once**. Copy it immediately!

1. **Copy the API key** - it will look something like:
   ```
   oa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

2. **Save it securely:**
   - Save in a password manager
   - Or save in a secure note
   - **DO NOT** commit it to git or share it publicly

3. **Close the dialog** (the key won't be shown again)

---

## Step 4: Configure Portfolio Manager

Now add this API key to your Portfolio Manager configuration:

### Option 1: Edit Config File Directly

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager
nano openalgo_config.json
```

Update the `openalgo_api_key` field:

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "oa_your_actual_api_key_here",  ← PASTE YOUR KEY HERE
  "broker": "dhan",
  "execution_mode": "analyzer",
  ...
}
```

### Option 2: Use Command Line (Alternative)

When starting Portfolio Manager, you can also pass the API key via command line:

```bash
python portfolio_manager.py live \
  --broker dhan \
  --api-key oa_your_actual_api_key_here \
  --capital 5000000
```

---

## Verification Checklist

After generating and configuring the API key:

- [ ] ✅ Dhan broker connected in OpenAlgo dashboard
- [ ] ✅ OpenAlgo API key generated
- [ ] ✅ API key copied and saved securely
- [ ] ✅ API key added to `portfolio_manager/openalgo_config.json`
- [ ] ✅ Ready to test Portfolio Manager connection

---

## Testing the API Key

You can test if your API key works:

```bash
# Test OpenAlgo connection with API key
curl -H "Authorization: Bearer YOUR_API_KEY_HERE" \
     http://localhost:5000/api/v1/health
```

Expected response:
```json
{"status": "ok", "broker": "dhan"}
```

Or use the Portfolio Manager test script:

```bash
cd portfolio_manager
python3 test_openalgo_connection.py
```

---

## Understanding the Two Different Keys

### 1. Dhan Broker Credentials (Already Done ✅)
- **What:** Your Dhan Client ID and Access Token
- **Where:** Stored in OpenAlgo database after OAuth
- **Purpose:** OpenAlgo uses these to connect to Dhan broker
- **Status:** ✅ Already configured via dashboard

### 2. OpenAlgo API Key (Do This Now ⬅️)
- **What:** API key generated from OpenAlgo dashboard
- **Where:** You need to copy and save it
- **Purpose:** Portfolio Manager uses this to authenticate with OpenAlgo server
- **Status:** ⬅️ Generate this now

---

## Security Best Practices

1. **Never commit API key to git:**
   - `openalgo_config.json` should be in `.gitignore`
   - Use `openalgo_config.json.example` for templates

2. **Rotate keys periodically:**
   - Generate new keys every few months
   - Revoke old keys if compromised

3. **Use different keys for different applications:**
   - One key for Portfolio Manager
   - Another key for testing/development

4. **Store securely:**
   - Use password manager
   - Don't share via email/chat
   - Don't hardcode in scripts

---

## Troubleshooting

### "Invalid API key" error:
- **Check:** API key copied correctly (no extra spaces)
- **Check:** API key hasn't expired
- **Check:** OpenAlgo server is running

### "API key not found":
- **Check:** You generated the key from the correct OpenAlgo instance
- **Check:** Key is saved in `openalgo_config.json`

### "Unauthorized" error:
- **Check:** API key format is correct (starts with `oa_`)
- **Check:** Authorization header format: `Bearer YOUR_API_KEY`

---

## Next Steps After API Key Setup

1. ✅ Generate OpenAlgo API key
2. ✅ Save it to `portfolio_manager/openalgo_config.json`
3. ✅ Test connection: `python3 portfolio_manager/test_openalgo_connection.py`
4. ✅ Start Portfolio Manager in analyzer mode
5. ✅ Send test signal to verify end-to-end flow

---

## Summary

**Yes, you need to generate an OpenAlgo API key!**

- **Dhan connection** = Broker authentication (✅ Done)
- **OpenAlgo API key** = Portfolio Manager authentication (⬅️ Do this now)

The API key is what allows Portfolio Manager to communicate with OpenAlgo server and execute trades through your connected Dhan broker.

---

**Last Updated:** December 2, 2025

