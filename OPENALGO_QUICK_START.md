# OpenAlgo Quick Start Guide

## 🚀 Installation Commands

### 1. Install OpenAlgo Server (5 minutes)

```bash
# Clone and setup
cd ~
git clone https://github.com/marketcalls/openalgo.git
cd openalgo
pip install uv
cp .sample.env .env

# Edit .env with your broker credentials
nano .env

# Required variables in .env:
# BROKER_API_KEY=your_broker_api_key
# BROKER_API_SECRET=your_broker_api_secret
# APP_KEY=generate_with: python -c "import secrets; print(secrets.token_hex(32))"
# API_KEY_PEPPER=generate_with: python -c "import secrets; print(secrets.token_hex(32))"

# Start server
uv run app.py
# Server runs on http://localhost:5000
```

### 2. Get OpenAlgo API Key (2 minutes)

1. Open http://localhost:5000 in browser
2. Login to dashboard
3. Go to Settings → API Keys
4. Generate new API key
5. **Copy and save the API key**

### 3. Integrate with Portfolio Manager (2 minutes)

```bash
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending

# Run integration script
./setup_openalgo_integration.sh

# Configure with your API key
cd portfolio_manager
cp openalgo_config.json.example openalgo_config.json
nano openalgo_config.json  # Add your API key
```

### 4. Test Integration (2 minutes)

```bash
cd portfolio_manager

# Run integration tests
pytest tests/integration/test_openalgo_integration.py -v

# Start Portfolio Manager (analyzer mode)
./start_portfolio_manager.sh
```

---

## 📝 Configuration

**Edit `portfolio_manager/openalgo_config.json`:**

```json
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "YOUR_API_KEY_HERE",  ← PUT YOUR KEY HERE
  "broker": "zerodha",
  "execution_mode": "analyzer"  ← START WITH THIS
}
```

---

## 🧪 Testing Checklist

- [ ] OpenAlgo server running on port 5000
- [ ] Can access http://localhost:5000 in browser
- [ ] API key generated and saved
- [ ] Integration script completed successfully
- [ ] `openalgo_config.json` configured with API key
- [ ] Integration tests passing
- [ ] Portfolio Manager starts without errors

---

## 🎯 Quick Test

```bash
# Terminal 1: Start OpenAlgo
cd ~/openalgo
uv run app.py

# Terminal 2: Start Portfolio Manager
cd /Users/shankarvasudevan/claude-code/ITJ-BN-Trending/portfolio_manager
./start_portfolio_manager.sh

# Terminal 3: Send test signal
curl -X POST http://localhost:5001/webhook \
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

**Expected:** Signal processed, position size calculated, logged (not executed in analyzer mode)

---

## 🔧 Troubleshooting

### OpenAlgo won't start
```bash
# Check Python version (needs 3.8+)
python --version

# Reinstall UV
pip install --upgrade uv

# Check .env file exists
ls -la ~/openalgo/.env
```

### Portfolio Manager can't connect
```bash
# Verify OpenAlgo is running
curl http://localhost:5000/api/v1/health

# Check API key in config
cat portfolio_manager/openalgo_config.json | grep api_key
```

### Tests failing
```bash
# Install test dependencies
cd portfolio_manager
pip install -r requirements.txt

# Run with verbose output
pytest tests/integration/test_openalgo_integration.py -vv
```

---

## 📚 Full Documentation

- **Complete Guide:** `OPENALGO_SETUP_GUIDE.md`
- **Portfolio Manager:** `portfolio_manager/README.md`
- **Database Setup:** `portfolio_manager/DATABASE_SETUP.md`
- **OpenAlgo Docs:** https://docs.openalgo.in

---

## ⚠️ Safety First

**Always start in ANALYZER mode:**
- No real trades executed
- Test signal processing
- Verify position sizing
- Check logs for errors

**Run for 1-2 weeks before going live!**

---

## 🎉 Success Indicators

You're ready to proceed when:
- ✅ OpenAlgo dashboard accessible
- ✅ Portfolio Manager starts without errors
- ✅ Test signals processed correctly
- ✅ Position sizing calculations correct
- ✅ Logs show proper signal flow
- ✅ No errors in analyzer mode

---

**Need Help?** See `OPENALGO_SETUP_GUIDE.md` for detailed instructions.

**Last Updated:** December 2, 2025


