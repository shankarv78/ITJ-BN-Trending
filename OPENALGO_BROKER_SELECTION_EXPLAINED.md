# How OpenAlgo Determines Which Broker You're Using

## Overview

OpenAlgo uses a **two-step process** to determine and connect to your broker:

1. **Environment Configuration** (`.env` file) - Enables brokers and provides credentials
2. **Dashboard Selection** (Web UI) - Selects and authenticates the specific broker

---

## Step 1: Enable Brokers in `.env` File

In your `~/openalgo/.env` file, you specify which brokers are **available** (enabled):

```env
# List of brokers you want to enable
VALID_BROKERS=zerodha,dhan,fyers,upstox

# Generic broker credentials (used during OAuth authentication)
BROKER_API_KEY=your_broker_api_key_here
BROKER_API_SECRET=your_broker_api_secret_here
```

**What this does:**
- `VALID_BROKERS` - Lists which broker integrations are enabled
- `BROKER_API_KEY` and `BROKER_API_SECRET` - Your broker's API credentials (used during OAuth)

**Important:** These credentials are **generic** - they're the same variable names regardless of which broker you use. OpenAlgo uses them during the OAuth authentication flow.

---

## Step 2: Select Broker in Dashboard

After starting OpenAlgo server, you **select and authenticate** your broker through the web dashboard:

### Process:

1. **Start OpenAlgo Server:**
   ```bash
   cd ~/openalgo
   uv run app.py
   ```

2. **Open Dashboard:**
   - Navigate to http://localhost:5000
   - Login to OpenAlgo dashboard

3. **Select Your Broker:**
   - Go to **Broker Settings** or **Connect Broker** section
   - You'll see a list of brokers you enabled in `VALID_BROKERS`
   - Click on your broker (e.g., "Zerodha" or "Dhan")

4. **Complete OAuth Authentication:**
   - OpenAlgo will redirect you to your broker's login page
   - Login with your broker credentials
   - Authorize OpenAlgo to access your account
   - You'll be redirected back to OpenAlgo dashboard

5. **Broker Connection Stored:**
   - OpenAlgo stores the authenticated broker connection in its database
   - The broker type and authentication tokens are saved
   - You can now use this broker for trading

---

## How OpenAlgo Knows Which Broker to Use

Once you've authenticated a broker through the dashboard:

1. **Database Storage:** OpenAlgo saves the broker connection in its SQLite database (`db/openalgo.db`)
2. **API Context:** When you make API calls to OpenAlgo, it uses the authenticated broker from the database
3. **User Session:** The broker is associated with your OpenAlgo user account

---

## Example Flow

### For Zerodha:

```env
# .env file
VALID_BROKERS=zerodha
BROKER_API_KEY=your_zerodha_api_key
BROKER_API_SECRET=your_zerodha_api_secret
```

1. Start server → Dashboard shows "Zerodha" as available
2. Click "Connect Zerodha" in dashboard
3. Redirected to Zerodha login → Login → Authorize
4. Back to OpenAlgo → Broker connected
5. All API calls now use Zerodha

### For Dhan:

```env
# .env file
VALID_BROKERS=dhan
BROKER_API_KEY=your_dhan_client_id
BROKER_API_SECRET=your_dhan_access_token
```

1. Start server → Dashboard shows "Dhan" as available
2. Click "Connect Dhan" in dashboard
3. Complete Dhan authentication
4. Broker connected → All API calls use Dhan

---

## Multiple Brokers

You can enable multiple brokers in `VALID_BROKERS`:

```env
VALID_BROKERS=zerodha,dhan,fyers
```

Then in the dashboard, you can:
- Connect to multiple brokers
- Switch between them
- Each broker connection is stored separately

---

## Key Points

✅ **No `BROKER` variable needed** - Broker selection happens in dashboard  
✅ **`VALID_BROKERS`** - Enables which brokers are available  
✅ **`BROKER_API_KEY/SECRET`** - Generic credentials used during OAuth  
✅ **Dashboard Selection** - Where you actually choose and authenticate your broker  
✅ **Database Storage** - OpenAlgo remembers your broker connection  

---

## Troubleshooting

### "Broker not found" error:
- Check that your broker is in `VALID_BROKERS` list
- Restart OpenAlgo server after changing `.env`

### "Authentication failed":
- Verify `BROKER_API_KEY` and `BROKER_API_SECRET` are correct
- Check that credentials match the broker you're trying to connect

### "No broker connected":
- Make sure you've completed the OAuth flow in the dashboard
- Check that broker connection shows as "Connected" in dashboard

---

## Summary

**OpenAlgo determines your broker through:**
1. `.env` file → Enables brokers (`VALID_BROKERS`) and provides credentials
2. Dashboard → You select and authenticate the specific broker
3. Database → OpenAlgo stores the broker connection for future use

The broker type is **not** specified in `.env` - it's selected and authenticated through the web dashboard after the server starts.

---

**Last Updated:** December 2, 2025

