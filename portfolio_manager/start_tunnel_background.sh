#!/bin/bash

# ============================================================================
# Start Cloudflare Tunnel in Background
# ============================================================================
# This script starts cloudflared tunnel in the background and saves the URL
# to a file for easy reference.
#
# Usage:
#   ./start_tunnel_background.sh
# ============================================================================

set -e

PORT=5002
LOG_FILE="tunnel.log"
URL_FILE="tunnel_url.txt"

echo "Starting Cloudflare Tunnel in background..."
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo "   Run: brew install cloudflared"
    exit 1
fi

# Check if portfolio manager is running
if ! lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  WARNING: Portfolio manager is not running on port ${PORT}"
    echo "   Please start it first:"
    echo "   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    exit 1
fi

# Start tunnel in background
echo "Starting tunnel..."
cloudflared tunnel --url http://localhost:${PORT} > ${LOG_FILE} 2>&1 &
TUNNEL_PID=$!

echo "✅ Tunnel started (PID: ${TUNNEL_PID})"
echo "   Logs: ${LOG_FILE}"
echo ""

# Wait a few seconds for tunnel to initialize
sleep 3

# Extract URL from logs
if [ -f "${LOG_FILE}" ]; then
    TUNNEL_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' ${LOG_FILE} | head -n 1)
    
    if [ -n "${TUNNEL_URL}" ]; then
        WEBHOOK_URL="${TUNNEL_URL}/webhook"
        echo "${WEBHOOK_URL}" > ${URL_FILE}
        echo "============================================================================"
        echo "✅ Tunnel is running!"
        echo "============================================================================"
        echo ""
        echo "📡 Public Webhook URL:"
        echo "   ${WEBHOOK_URL}"
        echo ""
        echo "📝 URL saved to: ${URL_FILE}"
        echo ""
        echo "🔍 View logs:"
        echo "   tail -f ${LOG_FILE}"
        echo ""
        echo "🛑 Stop tunnel:"
        echo "   kill ${TUNNEL_PID}"
        echo ""
        echo "============================================================================"
    else
        echo "⚠️  Could not extract URL from logs yet."
        echo "   Check ${LOG_FILE} in a few seconds."
    fi
else
    echo "⚠️  Log file not created yet. Check ${LOG_FILE} in a few seconds."
fi

echo ""
echo "Tunnel PID: ${TUNNEL_PID}"
echo "To stop: kill ${TUNNEL_PID}"

