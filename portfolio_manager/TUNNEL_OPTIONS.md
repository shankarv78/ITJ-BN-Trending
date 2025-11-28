# Tunnel Options for Permanent TradingView Webhook URL

## Your Requirement
✅ **Permanent URL that never changes** - No daily TradingView reconfiguration

## Solution Options

### Option 1: Named Tunnel with Free Domain (Recommended) ⭐

**Best for:** Production use, truly permanent URL

**Requirements:**
- Free Cloudflare account
- Free domain (e.g., from Freenom, or use a subdomain of a domain you own)

**Steps:**
1. Get a free domain (e.g., `yourname.tk` from Freenom) or use a subdomain
2. Add domain to Cloudflare (free)
3. Run: `./setup_named_tunnel.sh`
4. Configure DNS: `cloudflared tunnel route dns portfolio-manager webhook.yourname.tk`
5. Your permanent URL: `https://webhook.yourname.tk/webhook`

**Pros:**
- ✅ Truly permanent URL
- ✅ Professional appearance
- ✅ Full control

**Cons:**
- ⚠️ Requires domain setup (one-time, ~10 minutes)

---

### Option 2: Named Tunnel with Cloudflare Public Hostname

**Best for:** Quick setup, no domain needed

**How it works:**
- Cloudflare assigns a random subdomain on first run
- That subdomain becomes permanent for your tunnel
- URL format: `https://random-name.trycloudflare.com`

**Steps:**
1. Run: `./setup_named_tunnel.sh`
2. Run: `./start_named_tunnel.sh`
3. Copy the URL shown in terminal (first time only)
4. Use that URL in TradingView (never changes after first assignment)

**Pros:**
- ✅ No domain needed
- ✅ URL becomes permanent after first run
- ✅ Free

**Cons:**
- ⚠️ Random subdomain (not customizable)
- ⚠️ Requires Cloudflare account

**Note:** The config file has been updated to let Cloudflare assign the hostname automatically.

---

### Option 3: Quick Tunnel + Process Manager (Not Recommended)

**Best for:** Testing only

**How it works:**
- Use `cloudflared tunnel --url` 
- Run it as a system service (launchd on macOS)
- URL stays same as long as process runs

**Pros:**
- ✅ No Cloudflare account needed
- ✅ Simple setup

**Cons:**
- ❌ URL changes if process restarts
- ❌ Not truly permanent
- ❌ Requires process management setup

---

## Recommendation

**For your use case (no daily reconfiguration):**

👉 **Use Option 2** (Named Tunnel with Cloudflare Public Hostname)

**Why:**
- ✅ One-time setup (~5 minutes)
- ✅ Permanent URL after first run
- ✅ No domain needed
- ✅ Free Cloudflare account is all you need

**Setup:**
```bash
# One-time setup
./setup_named_tunnel.sh

# Start tunnel (every trading session)
./start_named_tunnel.sh

# Copy the URL shown (first time only)
# Use in TradingView - never changes after that!
```

---

## Quick Comparison

| Option | Permanent? | Domain Needed? | Setup Time | Best For |
|--------|-----------|----------------|------------|----------|
| Named + Domain | ✅ Yes | ✅ Yes | 10 min | Production |
| Named + Public Hostname | ✅ Yes* | ❌ No | 5 min | **Recommended** |
| Quick Tunnel | ❌ No | ❌ No | 2 min | Testing only |

*Permanent after first assignment

---

## Next Steps

1. **Choose Option 2** (easiest, meets your needs)
2. Run `./setup_named_tunnel.sh`
3. Run `./start_named_tunnel.sh` 
4. Copy the URL from terminal output
5. Add to TradingView once - done forever! 🎉

