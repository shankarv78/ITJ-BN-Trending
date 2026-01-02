#!/bin/bash
# ================================================================
# Margin Monitor + Auto-Hedge Development Startup Script
# ================================================================
#
# Usage: ./start_dev.sh [--live]
#
# Modes:
#   Default (no args): Dry run mode - no real orders placed
#   --live:           Live mode - REAL orders will be placed!
#
# ================================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Margin Monitor + Auto-Hedge Startup  ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check for --live flag
LIVE_MODE=false
if [[ "$1" == "--live" ]]; then
    LIVE_MODE=true
    echo -e "${RED}⚠️  WARNING: LIVE MODE - Real orders will be placed!${NC}"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# ================================================================
# Environment Variables
# ================================================================

# Auto-Hedge System
export AUTO_HEDGE_ENABLED=true

if [[ "$LIVE_MODE" == "true" ]]; then
    export AUTO_HEDGE_DRY_RUN=false
    echo -e "${RED}🔴 DRY_RUN: OFF (LIVE ORDERS)${NC}"
else
    export AUTO_HEDGE_DRY_RUN=true
    echo -e "${GREEN}🟢 DRY_RUN: ON (Paper trading)${NC}"
fi

# Development mode - allows manual actions without API key
export HEDGE_DEV_MODE=true
echo -e "${YELLOW}🔧 DEV_MODE: ON (No API key required)${NC}"

# Optional: Uncomment and set for production
# export HEDGE_API_KEY="your_secure_api_key_here"

# Optional: Telegram notifications
# export TELEGRAM_BOT_TOKEN="your_bot_token"
# export TELEGRAM_CHAT_ID="your_chat_id"

# Optional: OpenAlgo (for real order execution)
# export OPENALGO_BASE_URL="http://localhost:5000"
# export OPENALGO_API_KEY="your_openalgo_api_key"

echo ""
echo -e "${BLUE}Environment:${NC}"
echo "  AUTO_HEDGE_ENABLED = $AUTO_HEDGE_ENABLED"
echo "  AUTO_HEDGE_DRY_RUN = $AUTO_HEDGE_DRY_RUN"
echo "  HEDGE_DEV_MODE     = $HEDGE_DEV_MODE"
echo ""

# ================================================================
# Activate Virtual Environment
# ================================================================

if [[ -d "venv" ]]; then
    echo -e "${BLUE}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}Error: venv not found. Run: python3 -m venv venv && pip install -r requirements.txt${NC}"
    exit 1
fi

# ================================================================
# Start Server
# ================================================================

echo ""
echo -e "${GREEN}Starting Margin Monitor on http://localhost:5010${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

python3 run.py
