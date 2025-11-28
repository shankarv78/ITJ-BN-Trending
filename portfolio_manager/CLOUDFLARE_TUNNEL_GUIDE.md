# Cloudflare Tunnel Setup Guide

## Quick Start

### ⭐ Option 1: Simple Tunnel (No Domain Required) - EASIEST

**Best for:** Quick setup, no domain needed

```bash
cd portfolio_manager
./setup_tunnel_no_domain.sh
```

**How it works:**
- ✅ No Cloudflare login required
- ✅ No domain needed
- ✅ URL stays same as long as tunnel runs
- ⚠️ URL changes if you restart tunnel (but you can keep it running)

**Perfect if:** You're okay keeping the tunnel running (use `screen`/`tmux` for background)

---

### ⭐ Option 2: Permanent URL with Free Domain - RECOMMENDED

**Best for:** Truly permanent URL that never changes

```bash
cd portfolio_manager
./setup_tunnel_with_free_domain.sh
```

**Benefits:**
- ✅ **Permanent URL** - Never changes, even after restarts
- ✅ **No TradingView reconfiguration** - Set it once, use forever
- ✅ **Free domain** - Get one from Freenom (5 minutes)
- ✅ **Free Cloudflare account** - Just need to sign up (free)

**Takes ~10 minutes total** for a permanent solution.

---

### Option 3: Named Tunnel (If You Have Domain)

**Only use if you already have a domain in Cloudflare:**

```bash
cd portfolio_manager
./setup_named_tunnel.sh
```

**⚠️ Note:** This requires a domain/zone in your Cloudflare account. If you see "No domains found" during setup, use Option 1 or 2 instead.

### Option 2: Quick Tunnel (Temporary - For Testing Only)

**Only use this for testing. URL changes on restart!**

```bash
cd portfolio_manager
./setup_cloudflare_tunnel.sh
```

This script will:
- ✅ Check if `cloudflared` is installed
- ✅ Install it automatically if missing (via Homebrew on macOS)
- ✅ Verify portfolio manager is running
- ✅ Start the tunnel and show you the public URL

**⚠️ Warning:** URL changes every time you restart the tunnel. Not suitable for production.

### Option 3: Manual Setup

1. **Install cloudflared** (if not already installed):
   ```bash
   brew install cloudflared
   ```

2. **Start portfolio manager** (in Terminal 1):
   ```bash
   cd portfolio_manager
   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
   ```

3. **Start tunnel** (in Terminal 2):
   ```bash
   cloudflared tunnel --url http://localhost:5002
   ```

4. **Copy the public URL** shown in Terminal 2:
   ```
   https://random-name.trycloudflare.com
   ```

5. **Use in TradingView**:
   - Webhook URL: `https://random-name.trycloudflare.com/webhook`
   - Add this to your TradingView alert settings

## Important Notes

### ⚠️ Quick Tunnel URLs

When using `cloudflared tunnel --url`, you get a **quick tunnel** with a URL on `trycloudflare.com`. 

**Important clarification:**
- The URL stays the same **as long as the tunnel is running**
- The URL only changes if you **restart the tunnel**
- For daily trading, just **keep the tunnel running** and the URL remains stable

**Practical approach:**
- Start tunnel once at the beginning of your trading session
- Keep it running (use `screen`/`tmux` for background)
- URL stays the same throughout your session

**If you need a permanent URL that survives restarts:**
- Use a **named tunnel** (see Advanced section below)
- This requires a Cloudflare account (free) and provides a stable URL even after restarts

### 🔄 Keep Tunnel Running

- **Keep the tunnel terminal open** while trading
- If the tunnel stops, TradingView alerts will fail
- Use `screen` or `tmux` to run in background (see below)

### 🛑 Stopping the Tunnel

Press `Ctrl+C` in the tunnel terminal to stop it.

## Named Tunnel Setup (Permanent URL) ⭐ RECOMMENDED

For a **permanent URL** that doesn't change, set up a named tunnel. This is the **recommended approach** for production use.

### Automated Setup (Easiest)

```bash
# One-time setup
./setup_named_tunnel.sh

# Start tunnel (every trading session)
./start_named_tunnel.sh
```

The setup script will:
1. ✅ Authenticate with Cloudflare (opens browser)
2. ✅ Create a named tunnel
3. ✅ Configure the tunnel automatically
4. ✅ Provide you with a permanent URL

### Manual Setup (If you prefer step-by-step)

### Step 1: Login to Cloudflare

```bash
cloudflared tunnel login
```

This opens your browser to authenticate with Cloudflare.

### Step 2: Create Named Tunnel

```bash
cloudflared tunnel create portfolio-manager
```

This creates a tunnel named `portfolio-manager` and saves credentials.

### Step 3: Configure Tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: portfolio-manager
credentials-file: /Users/YOUR_USERNAME/.cloudflared/TUNNEL_ID.json

ingress:
  - hostname: portfolio-manager.YOUR_DOMAIN.com
    service: http://localhost:5002
  - service: http_status:404
```

### Step 4: Route DNS (Optional)

If you have a domain:
```bash
cloudflared tunnel route dns portfolio-manager portfolio-manager.YOUR_DOMAIN.com
```

### Step 5: Run Tunnel

```bash
cloudflared tunnel run portfolio-manager
```

## Running in Background

### Using `screen`:

```bash
# Start screen session
screen -S tunnel

# Run tunnel
cloudflared tunnel --url http://localhost:5002

# Detach: Press Ctrl+A, then D
# Reattach: screen -r tunnel
```

### Using `tmux`:

```bash
# Start tmux session
tmux new -s tunnel

# Run tunnel
cloudflared tunnel --url http://localhost:5002

# Detach: Press Ctrl+B, then D
# Reattach: tmux attach -t tunnel
```

### Using `nohup`:

```bash
nohup cloudflared tunnel --url http://localhost:5002 > tunnel.log 2>&1 &
```

Check logs: `tail -f tunnel.log`

## Troubleshooting

### "Port 5002 not accessible"

**Problem**: Portfolio manager isn't running.

**Solution**: Start the portfolio manager first:
```bash
cd portfolio_manager
python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
```

### "cloudflared: command not found"

**Problem**: `cloudflared` is not installed or not in PATH.

**Solution**: 
```bash
brew install cloudflared
```

Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

### "Tunnel URL keeps changing"

**Problem**: Quick tunnel URLs change when you restart.

**Solution**: 
- **Option 1**: Keep the tunnel running (don't restart it)
- **Option 2**: Set up a named tunnel for a permanent URL (see Advanced section above)

### "TradingView can't reach webhook"

**Problem**: Tunnel might be down or URL changed.

**Solution**: 
1. Check tunnel is running: `ps aux | grep cloudflared`
2. Verify URL in TradingView matches current tunnel URL
3. Test webhook manually:
   ```bash
   curl -X POST https://YOUR_TUNNEL_URL/webhook \
     -H "Content-Type: application/json" \
     -d '{"type":"BASE_ENTRY","instrument":"BANK_NIFTY","position":"Long_1","price":52000,"stop":51650,"lots":5,"atr":350,"er":0.82,"supertrend":51650,"timestamp":"2025-11-27T10:30:00Z"}'
   ```

## Testing the Webhook

Once the tunnel is running, test it:

```bash
curl -X POST https://YOUR_TUNNEL_URL/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000,
    "stop": 51650,
    "lots": 5,
    "atr": 350,
    "er": 0.82,
    "supertrend": 51650,
    "timestamp": "2025-11-27T10:30:00Z"
  }'
```

Expected response:
```json
{
  "status": "processed",
  "request_id": "abc12345",
  "result": {
    "status": "executed",
    ...
  }
}
```

## Security Considerations

### Webhook Secret (Optional)

The portfolio manager supports webhook authentication via `TRADINGVIEW_WEBHOOK_SECRET`:

1. **Set environment variable**:
   ```bash
   export TRADINGVIEW_WEBHOOK_SECRET="your-secret-key"
   ```

2. **Start portfolio manager**:
   ```bash
   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
   ```

3. **TradingView** will need to include the signature in headers (requires custom webhook setup or TradingView Plus/Premium).

### Rate Limiting

The webhook endpoint has built-in rate limiting:
- **100 requests per 60 seconds per IP**
- Exceeding this returns `429 Too Many Requests`

### Payload Size

Maximum payload size: **10 KB**

## Alternative: ngrok

If you prefer ngrok over Cloudflare Tunnel:

```bash
# Install ngrok
brew install ngrok

# Start tunnel
ngrok http 5002

# Use the HTTPS URL shown (e.g., https://abc123.ngrok-free.app/webhook)
```

**Note**: ngrok free tier has limitations (URL changes, connection limits). Cloudflare Tunnel is recommended for better free tier.

## Summary

1. ✅ Start portfolio manager: `python portfolio_manager.py live ...`
2. ✅ Start tunnel: `./setup_cloudflare_tunnel.sh` or `cloudflared tunnel --url http://localhost:5002`
3. ✅ Copy public URL from tunnel output
4. ✅ Add to TradingView: `https://YOUR_URL/webhook`
5. ✅ Keep tunnel running while trading!

---

**Questions?** Check the main README.md or open an issue.

