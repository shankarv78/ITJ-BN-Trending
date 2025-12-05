# Dhan Redirect URL Configuration for OpenAlgo

## Redirect URL for Dhan

When setting up Dhan broker integration with OpenAlgo, use this redirect URL:

```
http://127.0.0.1:5000/dhan/callback
```

---

## Two Places to Configure

### 1. In OpenAlgo `.env` File

In your `~/openalgo/.env` file, you can use either:

**Option A: Generic format (recommended if using multiple brokers)**
```env
REDIRECT_URL=http://127.0.0.1:5000/<broker>/callback
```
OpenAlgo will automatically substitute `<broker>` with "dhan" when needed.

**Option B: Explicit format (if only using Dhan)**
```env
REDIRECT_URL=http://127.0.0.1:5000/dhan/callback
```

---

### 2. In Dhan Developer Portal

**IMPORTANT:** You must also configure this redirect URL in Dhan's developer portal when creating your API credentials.

**Steps:**

1. **Login to Dhan Developer Portal:**
   - Go to https://dhan.co/developers or your Dhan developer dashboard
   - Navigate to API Key management

2. **Create/Edit API Application:**
   - Create a new application or edit existing one
   - Find the "Redirect URL" or "Callback URL" field

3. **Set Redirect URL:**
   ```
   http://127.0.0.1:5000/dhan/callback
   ```

4. **Save and Note Credentials:**
   - Save the application
   - Copy your **Client ID** (this becomes `BROKER_API_KEY` in OpenAlgo)
   - Copy your **Access Token** (this becomes `BROKER_API_SECRET` in OpenAlgo)

---

## Complete Dhan Setup Example

### Step 1: Dhan Developer Portal
- Create API application
- Set redirect URL: `http://127.0.0.1:5000/dhan/callback`
- Get Client ID and Access Token

### Step 2: OpenAlgo `.env` File
```env
VALID_BROKERS=dhan
BROKER_API_KEY=your_dhan_client_id_here
BROKER_API_SECRET=your_dhan_access_token_here
REDIRECT_URL=http://127.0.0.1:5000/dhan/callback
```

### Step 3: OpenAlgo Dashboard
1. Start OpenAlgo server
2. Open http://localhost:5000
3. Login to dashboard
4. Go to Broker Settings → Connect Dhan
5. Complete OAuth flow (will redirect to Dhan login)
6. After authorization, you'll be redirected back to: `http://127.0.0.1:5000/dhan/callback`

---

## Important Notes

✅ **Both places must match:**
- The redirect URL in Dhan developer portal
- The redirect URL in OpenAlgo `.env` file

✅ **For localhost:**
- Use `http://127.0.0.1:5000` (not `http://localhost:5000`)
- Port 5000 is OpenAlgo's default port

✅ **For production/deployed servers:**
- Replace `127.0.0.1:5000` with your actual server domain/IP
- Example: `https://yourdomain.com/dhan/callback`

✅ **Dhan Sandbox:**
- If using Dhan sandbox, the redirect URL format is the same
- Just ensure `VALID_BROKERS` includes `dhan_sandbox` instead of `dhan`

---

## Troubleshooting

### "Redirect URI mismatch" error:
- **Cause:** Redirect URL in Dhan portal doesn't match OpenAlgo `.env`
- **Fix:** Ensure both URLs are exactly: `http://127.0.0.1:5000/dhan/callback`

### "Invalid redirect URL" in Dhan portal:
- **Cause:** Dhan may require exact format
- **Fix:** Use `http://127.0.0.1:5000/dhan/callback` (not `localhost`)

### OAuth flow doesn't redirect back:
- **Cause:** Redirect URL not configured correctly
- **Fix:** Verify URL in both Dhan portal and OpenAlgo `.env` file

---

## Summary

**For Dhan broker with OpenAlgo:**
- **Redirect URL:** `http://127.0.0.1:5000/dhan/callback`
- **Configure in:** Dhan developer portal AND OpenAlgo `.env` file
- **Must match exactly** in both places

---

**Last Updated:** December 2, 2025

