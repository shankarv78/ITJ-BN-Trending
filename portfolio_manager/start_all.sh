#!/bin/bash

# =============================================================================
# UNIFIED STARTUP SCRIPT
# Starts OpenAlgo and Portfolio Manager with single command
# =============================================================================

set -e  # Exit on error

# Configuration
OPENALGO_DIR="$HOME/openalgo"
OPENALGO_PORT=5000
OPENALGO_URL="http://127.0.0.1:$OPENALGO_PORT"
PM_PORT=5002
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Banner
echo ""
echo "============================================================"
echo "  TOM BASSO PORTFOLIO MANAGER - UNIFIED STARTUP"
echo "============================================================"
echo ""

# -----------------------------------------------------------------------------
# Check dependencies
# -----------------------------------------------------------------------------

check_dependencies() {
    log_info "Checking dependencies..."

    # Check if OpenAlgo directory exists
    if [ ! -d "$OPENALGO_DIR" ]; then
        log_error "OpenAlgo not found at $OPENALGO_DIR"
        log_info "Please install OpenAlgo first: https://docs.openalgo.in"
        exit 1
    fi

    # Check if OpenAlgo venv exists
    if [ ! -f "$OPENALGO_DIR/.venv/bin/python" ]; then
        log_error "OpenAlgo virtual environment not found"
        log_info "Please run: cd $OPENALGO_DIR && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # Check if openalgo_config.json exists
    if [ ! -f "$SCRIPT_DIR/openalgo_config.json" ]; then
        log_error "openalgo_config.json not found"
        log_info "Please copy openalgo_config.json.example and configure it"
        exit 1
    fi

    log_success "All dependencies found"
}

# -----------------------------------------------------------------------------
# Check if OpenAlgo is running
# -----------------------------------------------------------------------------

is_openalgo_running() {
    # Check if OpenAlgo API responds with valid JSON containing "status"
    # This distinguishes OpenAlgo from macOS AirPlay (which returns 403 or empty)
    RESPONSE=$(curl -s "$OPENALGO_URL/api/v1/ping" -X POST -H "Content-Type: application/json" -d '{"apikey":"test"}' 2>/dev/null)
    if echo "$RESPONSE" | grep -q '"status"'; then
        return 0  # OpenAlgo is running
    else
        return 1  # Not OpenAlgo (could be AirPlay or nothing)
    fi
}

# -----------------------------------------------------------------------------
# Start OpenAlgo
# -----------------------------------------------------------------------------

start_openalgo() {
    log_info "Checking OpenAlgo status..."

    if is_openalgo_running; then
        log_success "OpenAlgo already running at $OPENALGO_URL"
        return 0
    fi

    log_info "Starting OpenAlgo..."

    cd "$OPENALGO_DIR"

    # Create required directories
    mkdir -p db log strategies keys 2>/dev/null || true

    # Start OpenAlgo in background using uv run
    # Set FLASK_PORT to run on the desired port
    # FLASK_DEBUG=1 allows Werkzeug to run (otherwise it refuses in "production" mode)
    FLASK_DEBUG=1 FLASK_PORT=$OPENALGO_PORT HOST_SERVER="http://127.0.0.1:$OPENALGO_PORT" \
        nohup uv run app.py > "$OPENALGO_DIR/log/openalgo.log" 2>&1 &

    OPENALGO_PID=$!
    echo $OPENALGO_PID > "$SCRIPT_DIR/.openalgo.pid"

    log_info "OpenAlgo starting with PID $OPENALGO_PID"

    # Wait for OpenAlgo to be ready
    log_info "Waiting for OpenAlgo to be ready..."

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if is_openalgo_running; then
            log_success "OpenAlgo is ready at $OPENALGO_URL"
            return 0
        fi
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done

    echo ""
    log_error "OpenAlgo failed to start after ${MAX_RETRIES}s"
    log_info "Check logs at: $OPENALGO_DIR/log/openalgo.log"
    exit 1
}

# -----------------------------------------------------------------------------
# Start Portfolio Manager
# -----------------------------------------------------------------------------

start_portfolio_manager() {
    log_info "Starting Portfolio Manager..."

    cd "$SCRIPT_DIR"

    # Extract config values
    API_KEY=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['openalgo_api_key'])")
    BROKER=$(python3 -c "import json; print(json.load(open('openalgo_config.json')).get('broker', 'dhan'))")

    if [ "$API_KEY" == "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD" ]; then
        log_error "Please configure your OpenAlgo API key in openalgo_config.json"
        exit 1
    fi

    log_info "Broker: $BROKER"
    log_info "API Key: ${API_KEY:0:20}..."
    log_info "Port: $PM_PORT"

    echo ""
    echo "============================================================"
    echo "  STARTING PORTFOLIO MANAGER"
    echo "============================================================"
    echo ""

    # Start Portfolio Manager
    python3 portfolio_manager.py live \
        --broker "$BROKER" \
        --api-key "$API_KEY" \
        --capital 5000000 \
        --port $PM_PORT \
        "$@"
}

# -----------------------------------------------------------------------------
# Stop all services
# -----------------------------------------------------------------------------

stop_all() {
    log_info "Stopping all services..."

    # Stop Portfolio Manager (if running in foreground, Ctrl+C will handle it)

    # Stop OpenAlgo
    if [ -f "$SCRIPT_DIR/.openalgo.pid" ]; then
        OPENALGO_PID=$(cat "$SCRIPT_DIR/.openalgo.pid")
        if ps -p $OPENALGO_PID > /dev/null 2>&1; then
            log_info "Stopping OpenAlgo (PID $OPENALGO_PID)..."
            kill $OPENALGO_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.openalgo.pid"
            log_success "OpenAlgo stopped"
        fi
    fi

    # Also try to kill by port
    OPENALGO_PID=$(lsof -ti:$OPENALGO_PORT 2>/dev/null || true)
    if [ ! -z "$OPENALGO_PID" ]; then
        log_info "Stopping OpenAlgo on port $OPENALGO_PORT..."
        kill $OPENALGO_PID 2>/dev/null || true
    fi

    log_success "All services stopped"
}

# -----------------------------------------------------------------------------
# Show status
# -----------------------------------------------------------------------------

show_status() {
    echo ""
    echo "============================================================"
    echo "  SERVICE STATUS"
    echo "============================================================"
    echo ""

    # OpenAlgo status
    if is_openalgo_running; then
        log_success "OpenAlgo: RUNNING at $OPENALGO_URL"
    else
        log_warn "OpenAlgo: NOT RUNNING"
    fi

    # Portfolio Manager status
    PM_PID=$(lsof -ti:$PM_PORT 2>/dev/null || true)
    if [ ! -z "$PM_PID" ]; then
        log_success "Portfolio Manager: RUNNING at http://127.0.0.1:$PM_PORT (PID $PM_PID)"
    else
        log_warn "Portfolio Manager: NOT RUNNING"
    fi

    echo ""
}

# -----------------------------------------------------------------------------
# Signal handler for graceful shutdown
# -----------------------------------------------------------------------------

cleanup() {
    echo ""
    log_info "Shutting down..."
    # Note: OpenAlgo keeps running, only PM stops
    exit 0
}

trap cleanup SIGINT SIGTERM

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

case "${1:-start}" in
    start)
        check_dependencies
        start_openalgo
        start_portfolio_manager "${@:2}"
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    restart)
        stop_all
        sleep 2
        check_dependencies
        start_openalgo
        start_portfolio_manager "${@:2}"
        ;;
    openalgo)
        # Start only OpenAlgo (useful for debugging)
        check_dependencies
        start_openalgo
        log_success "OpenAlgo started. Run './start_all.sh pm' to start Portfolio Manager separately"
        ;;
    pm)
        # Start only Portfolio Manager (assumes OpenAlgo is running)
        if ! is_openalgo_running; then
            log_error "OpenAlgo is not running. Start it first with './start_all.sh openalgo'"
            exit 1
        fi
        start_portfolio_manager "${@:2}"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|openalgo|pm}"
        echo ""
        echo "Commands:"
        echo "  start    - Start OpenAlgo and Portfolio Manager"
        echo "  stop     - Stop all services"
        echo "  status   - Show status of all services"
        echo "  restart  - Restart all services"
        echo "  openalgo - Start only OpenAlgo"
        echo "  pm       - Start only Portfolio Manager (OpenAlgo must be running)"
        echo ""
        exit 1
        ;;
esac
