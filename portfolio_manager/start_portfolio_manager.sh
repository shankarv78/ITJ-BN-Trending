#!/bin/bash

# Quick start script for Portfolio Manager with OpenAlgo

# Check if OpenAlgo config exists
if [ ! -f "openalgo_config.json" ]; then
    echo "Error: openalgo_config.json not found"
    echo "Please copy openalgo_config.json.example and configure it"
    exit 1
fi

# Extract API key and broker from config
API_KEY=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['openalgo_api_key'])")
BROKER=$(python3 -c "import json; print(json.load(open('openalgo_config.json')).get('broker', 'dhan'))")

if [ "$API_KEY" == "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD" ]; then
    echo "Error: Please configure your OpenAlgo API key in openalgo_config.json"
    exit 1
fi

# Validate broker choice
if [ "$BROKER" != "zerodha" ] && [ "$BROKER" != "dhan" ]; then
    echo "Error: Broker in config must be 'zerodha' or 'dhan' (found: $BROKER)"
    echo "Please update openalgo_config.json with the correct broker name"
    exit 1
fi

echo "Starting Portfolio Manager with OpenAlgo..."
echo "  Broker: $BROKER"
echo "  API Key: ${API_KEY:0:20}..."
echo ""

# Start Portfolio Manager
python3 portfolio_manager.py live \
  --broker "$BROKER" \
  --api-key "$API_KEY" \
  --capital 5000000 \
  "$@"
