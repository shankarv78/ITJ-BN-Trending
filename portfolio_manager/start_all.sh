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
TUNNEL_NAME="portfolio-manager"
CLOUDFLARED_CONFIG="$HOME/.cloudflared/config.yml"
MONITOR_LABEL="com.itj.pipeline-monitor"
MONITOR_PID_FILE="/tmp/pm_monitor.pid"
TEST_MODE=false
SILENT_MODE=false

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

# Parse --test-mode and --silent flags from any position in arguments
parse_flags() {
    for arg in "$@"; do
        if [ "$arg" == "--test-mode" ]; then
            TEST_MODE=true
        fi
        if [ "$arg" == "--silent" ]; then
            SILENT_MODE=true
        fi
    done
    return 0
}

# Remove handled flags from arguments (to pass remaining args to PM)
filter_handled_args() {
    local filtered=()
    for arg in "$@"; do
        if [ "$arg" != "--test-mode" ] && [ "$arg" != "--silent" ]; then
            filtered+=("$arg")
        fi
    done
    echo "${filtered[@]}"
}

# Check for flags in all arguments
parse_flags "$@"

# Banner
echo ""
echo "============================================================"
echo "  TOM BASSO PORTFOLIO MANAGER - UNIFIED STARTUP"
echo "  OpenAlgo + Cloudflare Tunnel + Portfolio Manager"
if [ "$TEST_MODE" = true ]; then
    echo -e "  ${YELLOW}⚠️  TEST MODE ENABLED - 1 LOT ORDERS ONLY${NC}"
fi
if [ "$SILENT_MODE" = true ]; then
    echo -e "  ${BLUE}🔇 SILENT MODE - No voice announcements${NC}"
fi
echo "============================================================"
echo ""

export EMERGENCY_API_KEY="964a99e357f681e8f3111c0c94933007840b52c1d4e2c0970bce6cd750e46480"

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

    # Start OpenAlgo in background using venv python
    # Set FLASK_PORT to run on the desired port
    # FLASK_DEBUG=1 allows Werkzeug to run (otherwise it refuses in "production" mode)
    FLASK_DEBUG=1 FLASK_PORT=$OPENALGO_PORT HOST_SERVER="http://127.0.0.1:$OPENALGO_PORT" \
        nohup "$OPENALGO_DIR/.venv/bin/python" app.py > "$OPENALGO_DIR/log/openalgo.log" 2>&1 &

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
# Start Cloudflare Tunnel
# -----------------------------------------------------------------------------

is_tunnel_running() {
    pgrep -f "cloudflared tunnel run $TUNNEL_NAME" > /dev/null 2>&1
}

start_tunnel() {
    log_info "Checking Cloudflare Tunnel status..."

    # Check if cloudflared is installed
    if ! command -v cloudflared &> /dev/null; then
        log_warn "cloudflared not installed - skipping tunnel"
        log_info "Install with: brew install cloudflared"
        return 1
    fi

    # Check if tunnel exists
    if ! cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
        log_warn "Tunnel '$TUNNEL_NAME' not configured - skipping"
        log_info "Run ./setup_named_tunnel.sh to configure"
        return 1
    fi

    if is_tunnel_running; then
        log_success "Cloudflare Tunnel already running"
        return 0
    fi

    log_info "Starting Cloudflare Tunnel..."

    # Start tunnel in background
    nohup cloudflared tunnel run "$TUNNEL_NAME" > "$SCRIPT_DIR/.tunnel.log" 2>&1 &
    TUNNEL_PID=$!
    echo $TUNNEL_PID > "$SCRIPT_DIR/.tunnel.pid"

    # Wait for tunnel to be ready (check if process is still running after 3 seconds)
    sleep 3

    if is_tunnel_running; then
        # Get hostname from config
        if [ -f "$CLOUDFLARED_CONFIG" ]; then
            HOSTNAME=$(grep -E "^\s+hostname:" "$CLOUDFLARED_CONFIG" | head -n 1 | awk '{print $2}' | tr -d '"' | tr -d "'")
            if [ -n "$HOSTNAME" ]; then
                log_success "Cloudflare Tunnel running"
                echo ""
                echo -e "  ${GREEN}📡 Webhook URL: https://$HOSTNAME/webhook${NC}"
                echo ""
            else
                log_success "Cloudflare Tunnel running (PID $TUNNEL_PID)"
            fi
        else
            log_success "Cloudflare Tunnel running (PID $TUNNEL_PID)"
        fi
        return 0
    else
        log_error "Cloudflare Tunnel failed to start"
        log_info "Check logs: $SCRIPT_DIR/.tunnel.log"
        return 1
    fi
}

stop_tunnel() {
    if [ -f "$SCRIPT_DIR/.tunnel.pid" ]; then
        TUNNEL_PID=$(cat "$SCRIPT_DIR/.tunnel.pid")
        if ps -p $TUNNEL_PID > /dev/null 2>&1; then
            log_info "Stopping Cloudflare Tunnel (PID $TUNNEL_PID)..."
            kill $TUNNEL_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.tunnel.pid"
            log_success "Cloudflare Tunnel stopped"
        fi
    fi

    # Also try to kill any running tunnel process
    pkill -f "cloudflared tunnel run $TUNNEL_NAME" 2>/dev/null || true
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

    if [ "$TEST_MODE" = true ]; then
        log_warn "TEST MODE: Orders will be 1 lot only (actual calculated lots will be logged)"
    fi
    if [ "$SILENT_MODE" = true ]; then
        log_info "SILENT MODE: Voice announcements disabled, using visual alerts"
    fi

    # Check pipeline monitor daemon (non-blocking warning)
    check_monitor_daemon

    echo ""
    echo "============================================================"
    if [ "$TEST_MODE" = true ] && [ "$SILENT_MODE" = true ]; then
        echo -e "  ${YELLOW}STARTING PORTFOLIO MANAGER (TEST + SILENT MODE)${NC}"
    elif [ "$TEST_MODE" = true ]; then
        echo -e "  ${YELLOW}STARTING PORTFOLIO MANAGER (TEST MODE)${NC}"
    elif [ "$SILENT_MODE" = true ]; then
        echo -e "  ${BLUE}STARTING PORTFOLIO MANAGER (SILENT MODE)${NC}"
    else
        echo "  STARTING PORTFOLIO MANAGER"
    fi
    echo "============================================================"
    echo ""

    # Build PM command with optional flags
    PM_ARGS="--api-key $API_KEY --db-config db_config.json --port $PM_PORT"
    if [ "$TEST_MODE" = true ]; then
        PM_ARGS="$PM_ARGS --test-mode"
    fi
    if [ "$SILENT_MODE" = true ]; then
        PM_ARGS="$PM_ARGS --silent"
    fi

    # Activate venv if not already active
    if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
        log_info "Activated Portfolio Manager venv"
    fi

    # Start Portfolio Manager (filter out handled flags from passed args)
    FILTERED_ARGS=$(filter_handled_args "$@")
    python3 portfolio_manager.py live $PM_ARGS $FILTERED_ARGS
}

# -----------------------------------------------------------------------------
# Stop all services
# -----------------------------------------------------------------------------

stop_all() {
    log_info "Stopping all services..."

    # Stop Portfolio Manager (if running in foreground, Ctrl+C will handle it)
    PM_PID=$(lsof -ti:$PM_PORT 2>/dev/null || true)
    if [ ! -z "$PM_PID" ]; then
        log_info "Stopping Portfolio Manager on port $PM_PORT..."
        kill $PM_PID 2>/dev/null || true
    fi

    # Stop Cloudflare Tunnel
    stop_tunnel

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
        # Check if PM is in test mode via health endpoint
        PM_TEST_MODE=$(curl -s "http://127.0.0.1:$PM_PORT/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('test_mode', False))" 2>/dev/null || echo "false")
        if [ "$PM_TEST_MODE" = "True" ]; then
            log_success "Portfolio Manager: RUNNING at http://127.0.0.1:$PM_PORT (PID $PM_PID) ${YELLOW}[TEST MODE]${NC}"
        else
            log_success "Portfolio Manager: RUNNING at http://127.0.0.1:$PM_PORT (PID $PM_PID)"
        fi
    else
        log_warn "Portfolio Manager: NOT RUNNING"
    fi

    # Cloudflare Tunnel status
    if is_tunnel_running; then
        if [ -f "$CLOUDFLARED_CONFIG" ]; then
            HOSTNAME=$(grep -E "^\s+hostname:" "$CLOUDFLARED_CONFIG" | head -n 1 | awk '{print $2}' | tr -d '"' | tr -d "'")
            if [ -n "$HOSTNAME" ]; then
                log_success "Cloudflare Tunnel: RUNNING → https://$HOSTNAME"
            else
                log_success "Cloudflare Tunnel: RUNNING"
            fi
        else
            log_success "Cloudflare Tunnel: RUNNING"
        fi
    else
        log_warn "Cloudflare Tunnel: NOT RUNNING"
    fi

    # Pipeline Monitor status
    if is_monitor_running; then
        log_success "Pipeline Monitor: RUNNING (launchd daemon)"
    else
        log_warn "Pipeline Monitor: NOT RUNNING"
    fi

    echo ""
}

# -----------------------------------------------------------------------------
# Check Pipeline Monitor Daemon
# -----------------------------------------------------------------------------

is_monitor_running() {
    # Check via launchctl (preferred)
    if launchctl list 2>/dev/null | grep -q "$MONITOR_LABEL"; then
        return 0
    fi

    # Fallback: check PID file
    if [ -f "$MONITOR_PID_FILE" ]; then
        MONITOR_PID=$(cat "$MONITOR_PID_FILE")
        if ps -p $MONITOR_PID > /dev/null 2>&1; then
            return 0
        fi
    fi

    return 1
}

check_monitor_daemon() {
    log_info "Checking Pipeline Monitor daemon..."

    if is_monitor_running; then
        log_success "Pipeline Monitor daemon is running"
        return 0
    else
        log_warn "Pipeline Monitor daemon is NOT running!"
        echo ""
        echo -e "  ${YELLOW}⚠️  The pipeline monitor daemon should be running to alert you${NC}"
        echo -e "  ${YELLOW}   if the trading pipeline goes down during market hours.${NC}"
        echo ""
        echo -e "  To start it manually:"
        echo -e "    ${BLUE}launchctl load ~/Library/LaunchAgents/com.itj.pipeline-monitor.plist${NC}"
        echo ""
        echo -e "  Or install it as a startup service:"
        echo -e "    ${BLUE}./install_monitor_service.sh${NC}"
        echo ""
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Signal handler for graceful shutdown
# -----------------------------------------------------------------------------

cleanup() {
    echo ""
    log_info "Shutting down..."
    # Stop tunnel on Ctrl+C (OpenAlgo keeps running)
    stop_tunnel
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
        start_tunnel  # Start tunnel in background before PM (PM runs in foreground)
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
        start_tunnel
        start_portfolio_manager "${@:2}"
        ;;
    openalgo)
        # Start only OpenAlgo (useful for debugging)
        check_dependencies
        start_openalgo
        log_success "OpenAlgo started. Run './start_all.sh pm' to start Portfolio Manager separately"
        ;;
    tunnel)
        # Start only Cloudflare Tunnel
        start_tunnel
        ;;
    pm)
        # Start only Portfolio Manager (assumes OpenAlgo is running)
        if ! is_openalgo_running; then
            log_error "OpenAlgo is not running. Start it first with './start_all.sh openalgo'"
            exit 1
        fi
        start_tunnel  # Also start tunnel when starting PM
        start_portfolio_manager "${@:2}"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|openalgo|tunnel|pm} [--test-mode] [--silent]"
        echo ""
        echo "Commands:"
        echo "  start    - Start OpenAlgo, Cloudflare Tunnel, and Portfolio Manager"
        echo "  stop     - Stop all services"
        echo "  status   - Show status of all services"
        echo "  restart  - Restart all services"
        echo "  openalgo - Start only OpenAlgo"
        echo "  tunnel   - Start only Cloudflare Tunnel"
        echo "  pm       - Start Portfolio Manager + Tunnel (OpenAlgo must be running)"
        echo ""
        echo "Options:"
        echo "  --test-mode  Enable test mode (1 lot orders only, logged calculated lots)"
        echo "  --silent     Disable voice announcements (use visual alerts instead)"
        echo ""
        echo "Examples:"
        echo "  $0 start              # Normal startup"
        echo "  $0 start --test-mode  # Start in test mode"
        echo "  $0 start --silent     # Start in silent mode (no voice)"
        echo "  $0 pm --test-mode --silent  # PM with both modes"
        echo ""
        exit 1
        ;;
esac
