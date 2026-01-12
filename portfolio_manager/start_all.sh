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
FRONTEND_PORT=8080
MARGIN_MONITOR_PORT=5010
SERVICE_MANAGER_PORT=5003
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_MANAGER_DIR="$SCRIPT_DIR/service_manager"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")/frontend"
MARGIN_MONITOR_DIR="$(dirname "$SCRIPT_DIR")/margin-monitor"
LOG_DIR="$SCRIPT_DIR/logs"
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
echo "  OpenAlgo + Tunnel + PM + Frontend + Margin Monitor"
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

    # Check if PostgreSQL is running (required for position persistence)
    if [ -f "$SCRIPT_DIR/db_config.json" ]; then
        log_info "Checking PostgreSQL connection..."
        if command -v pg_isready &> /dev/null; then
            if pg_isready -q 2>/dev/null; then
                log_success "PostgreSQL is running"
            else
                log_warn "PostgreSQL is NOT running - attempting to start..."

                # Try to start PostgreSQL automatically
                POSTGRES_STARTED=false

                # First, check for stale lock file (common after crash/unclean shutdown)
                for PG_DATA in /opt/homebrew/var/postgresql@14 /opt/homebrew/var/postgres /usr/local/var/postgres; do
                    if [ -f "$PG_DATA/postmaster.pid" ]; then
                        STALE_PID=$(head -1 "$PG_DATA/postmaster.pid" 2>/dev/null)
                        if [ -n "$STALE_PID" ] && ! ps -p "$STALE_PID" > /dev/null 2>&1; then
                            log_warn "Found stale PostgreSQL lock file (PID $STALE_PID is dead) - removing..."
                            rm -f "$PG_DATA/postmaster.pid" 2>/dev/null
                            log_info "Stale lock file removed"
                        fi
                    fi
                done

                # Method 1: Try brew services (most common on macOS)
                if command -v brew &> /dev/null; then
                    # Find installed PostgreSQL version
                    PG_VERSION=$(brew list 2>/dev/null | grep -E "^postgresql@[0-9]+" | head -1)
                    if [ -n "$PG_VERSION" ]; then
                        log_info "Starting PostgreSQL via brew services ($PG_VERSION)..."
                        if brew services start "$PG_VERSION" 2>/dev/null; then
                            sleep 2  # Give it time to start
                            if pg_isready -q 2>/dev/null; then
                                log_success "PostgreSQL started successfully"
                                POSTGRES_STARTED=true
                            fi
                        fi
                    fi
                fi

                # Method 2: Try pg_ctl if brew didn't work
                if [ "$POSTGRES_STARTED" = false ] && command -v pg_ctl &> /dev/null; then
                    # Find data directory
                    for PG_DATA in /opt/homebrew/var/postgresql@14 /opt/homebrew/var/postgres /usr/local/var/postgres; do
                        if [ -d "$PG_DATA" ]; then
                            log_info "Starting PostgreSQL via pg_ctl ($PG_DATA)..."
                            if pg_ctl -D "$PG_DATA" start -l "$PG_DATA/server.log" 2>/dev/null; then
                                sleep 2
                                if pg_isready -q 2>/dev/null; then
                                    log_success "PostgreSQL started successfully"
                                    POSTGRES_STARTED=true
                                    break
                                fi
                            fi
                        fi
                    done
                fi

                # If still not started, ask user
                if [ "$POSTGRES_STARTED" = false ]; then
                    log_error "Could not start PostgreSQL automatically"
                    echo ""
                    echo -e "  ${YELLOW}⚠️  Database persistence will be disabled.${NC}"
                    echo -e "  ${YELLOW}   Positions will NOT be saved across restarts.${NC}"
                    echo ""
                    echo -e "  To start PostgreSQL manually:"
                    echo -e "    ${BLUE}brew services start postgresql@14${NC}"
                    echo -e "  Or:"
                    echo -e "    ${BLUE}pg_ctl -D /opt/homebrew/var/postgresql@14 start${NC}"
                    echo ""
                    read -p "Continue without database? (y/N): " -n 1 -r
                    echo ""
                    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                        log_info "Exiting. Start PostgreSQL first, then retry."
                        exit 1
                    fi
                    log_warn "Continuing without database persistence..."
                fi
            fi
        else
            log_warn "pg_isready not found - cannot check PostgreSQL status"
        fi
    else
        log_warn "No db_config.json found - database persistence disabled"
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
# Start Margin Monitor
# -----------------------------------------------------------------------------

is_margin_monitor_running() {
    lsof -ti:$MARGIN_MONITOR_PORT > /dev/null 2>&1
}

start_margin_monitor() {
    log_info "Checking Margin Monitor status..."

    if is_margin_monitor_running; then
        log_success "Margin Monitor already running at http://localhost:$MARGIN_MONITOR_PORT"
        return 0
    fi

    if [ ! -d "$MARGIN_MONITOR_DIR" ]; then
        log_warn "Margin Monitor directory not found at $MARGIN_MONITOR_DIR - skipping"
        return 1
    fi

    if [ ! -f "$MARGIN_MONITOR_DIR/run.py" ]; then
        log_warn "Margin Monitor run.py not found - skipping"
        return 1
    fi

    log_info "Starting Margin Monitor..."

    # Create logs directory if it doesn't exist
    mkdir -p "$LOG_DIR"

    cd "$MARGIN_MONITOR_DIR"

    # Check if venv exists
    if [ ! -d "venv" ]; then
        log_warn "Margin Monitor venv not found - creating..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt >> "$LOG_DIR/margin_monitor.log" 2>&1
    else
        source venv/bin/activate
    fi

    # Set environment variables for dry run mode (safer default)
    export AUTO_HEDGE_ENABLED=true
    export AUTO_HEDGE_DRY_RUN=true
    export HEDGE_DEV_MODE=true

    # Start Margin Monitor in background
    MM_LOG="$LOG_DIR/margin_monitor.log"
    nohup python3 run.py >> "$MM_LOG" 2>&1 &
    MM_PID=$!
    echo $MM_PID > "$SCRIPT_DIR/.margin_monitor.pid"

    # Wait for Margin Monitor to be ready
    log_info "Waiting for Margin Monitor to be ready..."

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if is_margin_monitor_running; then
            log_success "Margin Monitor is ready at http://localhost:$MARGIN_MONITOR_PORT"
            echo ""
            echo -e "  ${GREEN}📊 Margin Monitor: http://localhost:$MARGIN_MONITOR_PORT${NC}"
            echo -e "  ${YELLOW}⚠️  Auto-Hedge: DRY RUN mode (no real orders)${NC}"
            echo -e "  ${BLUE}📝 Margin Monitor logs: $MM_LOG${NC}"
            echo ""
            return 0
        fi
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done

    echo ""
    log_error "Margin Monitor failed to start after ${MAX_RETRIES}s"
    log_info "Check logs at: $MM_LOG"
    return 1
}

stop_margin_monitor() {
    if [ -f "$SCRIPT_DIR/.margin_monitor.pid" ]; then
        MM_PID=$(cat "$SCRIPT_DIR/.margin_monitor.pid")
        if ps -p $MM_PID > /dev/null 2>&1; then
            log_info "Stopping Margin Monitor (PID $MM_PID)..."
            kill $MM_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.margin_monitor.pid"
            log_success "Margin Monitor stopped"
        fi
    fi

    # Also try to kill by port
    MM_PID=$(lsof -ti:$MARGIN_MONITOR_PORT 2>/dev/null || true)
    if [ ! -z "$MM_PID" ]; then
        kill $MM_PID 2>/dev/null || true
    fi
}

# -----------------------------------------------------------------------------
# Start Service Manager
# -----------------------------------------------------------------------------

is_service_manager_running() {
    lsof -ti:$SERVICE_MANAGER_PORT > /dev/null 2>&1
}

start_service_manager() {
    log_info "Checking Service Manager status..."

    if is_service_manager_running; then
        log_success "Service Manager already running at http://localhost:$SERVICE_MANAGER_PORT"
        return 0
    fi

    if [ ! -d "$SERVICE_MANAGER_DIR" ]; then
        log_warn "Service Manager directory not found at $SERVICE_MANAGER_DIR - skipping"
        return 1
    fi

    if [ ! -f "$SERVICE_MANAGER_DIR/app.py" ]; then
        log_warn "Service Manager app.py not found - skipping"
        return 1
    fi

    log_info "Starting Service Manager..."

    # Create logs directory if it doesn't exist
    mkdir -p "$LOG_DIR"

    cd "$SCRIPT_DIR"

    # Activate PM venv (service_manager uses same dependencies)
    if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
    fi

    # Start Service Manager in background
    SM_LOG="$LOG_DIR/service_manager.log"
    nohup python3 -m service_manager.app >> "$SM_LOG" 2>&1 &
    SM_PID=$!
    echo $SM_PID > "$SCRIPT_DIR/.service_manager.pid"

    # Wait for Service Manager to be ready
    log_info "Waiting for Service Manager to be ready..."

    MAX_RETRIES=15
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if is_service_manager_running; then
            log_success "Service Manager is ready at http://localhost:$SERVICE_MANAGER_PORT"
            echo ""
            echo -e "  ${GREEN}🔧 Service Manager: http://localhost:$SERVICE_MANAGER_PORT${NC}"
            echo -e "  ${BLUE}📝 Service Manager logs: $SM_LOG${NC}"
            echo ""
            return 0
        fi
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done

    echo ""
    log_error "Service Manager failed to start after ${MAX_RETRIES}s"
    log_info "Check logs at: $SM_LOG"
    return 1
}

stop_service_manager() {
    if [ -f "$SCRIPT_DIR/.service_manager.pid" ]; then
        SM_PID=$(cat "$SCRIPT_DIR/.service_manager.pid")
        if ps -p $SM_PID > /dev/null 2>&1; then
            log_info "Stopping Service Manager (PID $SM_PID)..."
            kill $SM_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.service_manager.pid"
            log_success "Service Manager stopped"
        fi
    fi

    # Also try to kill by port
    SM_PID=$(lsof -ti:$SERVICE_MANAGER_PORT 2>/dev/null || true)
    if [ ! -z "$SM_PID" ]; then
        kill $SM_PID 2>/dev/null || true
    fi
}

# -----------------------------------------------------------------------------
# Start Frontend
# -----------------------------------------------------------------------------

is_frontend_running() {
    lsof -ti:$FRONTEND_PORT > /dev/null 2>&1
}

start_frontend() {
    log_info "Checking Frontend status..."

    if is_frontend_running; then
        log_success "Frontend already running at http://localhost:$FRONTEND_PORT"
        return 0
    fi

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_warn "Frontend directory not found at $FRONTEND_DIR - skipping"
        return 1
    fi

    if [ ! -f "$FRONTEND_DIR/package.json" ]; then
        log_warn "No package.json found in frontend directory - skipping"
        return 1
    fi

    log_info "Starting Frontend..."

    # Create logs directory if it doesn't exist
    mkdir -p "$LOG_DIR"

    cd "$FRONTEND_DIR"

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        log_info "Installing frontend dependencies..."
        npm install >> "$LOG_DIR/frontend.log" 2>&1
    fi

    # Start frontend in background
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$SCRIPT_DIR/.frontend.pid"

    # Wait for frontend to be ready
    log_info "Waiting for Frontend to be ready..."

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if is_frontend_running; then
            log_success "Frontend is ready at http://localhost:$FRONTEND_PORT"
            echo ""
            echo -e "  ${GREEN}🖥️  Frontend URL: http://localhost:$FRONTEND_PORT${NC}"
            echo -e "  ${BLUE}📝 Frontend logs: $LOG_DIR/frontend.log${NC}"
            echo ""
            return 0
        fi
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done

    echo ""
    log_error "Frontend failed to start after ${MAX_RETRIES}s"
    log_info "Check logs at: $LOG_DIR/frontend.log"
    return 1
}

stop_frontend() {
    if [ -f "$SCRIPT_DIR/.frontend.pid" ]; then
        FRONTEND_PID=$(cat "$SCRIPT_DIR/.frontend.pid")
        if ps -p $FRONTEND_PID > /dev/null 2>&1; then
            log_info "Stopping Frontend (PID $FRONTEND_PID)..."
            kill $FRONTEND_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.frontend.pid"
            log_success "Frontend stopped"
        fi
    fi

    # Also try to kill by port
    FRONTEND_PID=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || true)
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
}

# -----------------------------------------------------------------------------
# Start Portfolio Manager
# -----------------------------------------------------------------------------

start_portfolio_manager() {
    log_info "Starting Portfolio Manager..."

    cd "$SCRIPT_DIR"

    # Create logs directory if it doesn't exist
    mkdir -p "$LOG_DIR"

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

    # Run PM in background with logging
    PM_LOG="$LOG_DIR/portfolio_manager.log"
    log_info "Logging PM output to: $PM_LOG"

    nohup python3 portfolio_manager.py live $PM_ARGS $FILTERED_ARGS >> "$PM_LOG" 2>&1 &
    PM_PID=$!
    echo $PM_PID > "$SCRIPT_DIR/.pm.pid"

    # Wait for PM to be ready
    log_info "Waiting for Portfolio Manager to be ready..."

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if lsof -ti:$PM_PORT > /dev/null 2>&1; then
            log_success "Portfolio Manager is ready at http://127.0.0.1:$PM_PORT"
            echo ""
            echo -e "  ${GREEN}📊 PM Dashboard: http://127.0.0.1:$PM_PORT/dashboard${NC}"
            echo -e "  ${BLUE}📝 PM logs: $PM_LOG${NC}"
            echo -e "  ${BLUE}📝 Tail logs: tail -f $PM_LOG${NC}"
            echo ""
            return 0
        fi
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done

    echo ""
    log_error "Portfolio Manager failed to start after ${MAX_RETRIES}s"
    log_info "Check logs at: $PM_LOG"
    exit 1
}

# -----------------------------------------------------------------------------
# Stop all services
# -----------------------------------------------------------------------------

stop_all() {
    log_info "Stopping all services..."

    # Stop Service Manager
    stop_service_manager

    # Stop Margin Monitor
    stop_margin_monitor

    # Stop Frontend
    stop_frontend

    # Stop Pipeline Monitor daemon
    if [ -f "$MONITOR_PID_FILE" ]; then
        MONITOR_PID=$(cat "$MONITOR_PID_FILE")
        if ps -p $MONITOR_PID > /dev/null 2>&1; then
            log_info "Stopping Pipeline Monitor (PID $MONITOR_PID)..."
            kill $MONITOR_PID 2>/dev/null || true
            rm "$MONITOR_PID_FILE"
            log_success "Pipeline Monitor stopped"
        fi
    fi
    # Also try via launchctl
    if launchctl list 2>/dev/null | grep -q "$MONITOR_LABEL"; then
        log_info "Unloading Pipeline Monitor from launchctl..."
        launchctl unload "$HOME/Library/LaunchAgents/com.itj.pipeline-monitor.plist" 2>/dev/null || true
    fi

    # Stop Portfolio Manager
    if [ -f "$SCRIPT_DIR/.pm.pid" ]; then
        PM_PID=$(cat "$SCRIPT_DIR/.pm.pid")
        if ps -p $PM_PID > /dev/null 2>&1; then
            log_info "Stopping Portfolio Manager (PID $PM_PID)..."
            kill $PM_PID 2>/dev/null || true
            rm "$SCRIPT_DIR/.pm.pid"
            log_success "Portfolio Manager stopped"
        fi
    fi
    # Also try to kill by port
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

    # PostgreSQL status
    if command -v pg_isready &> /dev/null; then
        if pg_isready -q 2>/dev/null; then
            log_success "PostgreSQL: RUNNING on port 5432"
        else
            log_warn "PostgreSQL: NOT RUNNING (positions not persisted!)"
        fi
    else
        log_warn "PostgreSQL: UNKNOWN (pg_isready not found)"
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

    # Frontend status
    if is_frontend_running; then
        log_success "Frontend: RUNNING at http://localhost:$FRONTEND_PORT"
    else
        log_warn "Frontend: NOT RUNNING"
    fi

    # Margin Monitor status
    if is_margin_monitor_running; then
        log_success "Margin Monitor: RUNNING at http://localhost:$MARGIN_MONITOR_PORT"
    else
        log_warn "Margin Monitor: NOT RUNNING"
    fi

    # Service Manager status
    if is_service_manager_running; then
        log_success "Service Manager: RUNNING at http://localhost:$SERVICE_MANAGER_PORT"
    else
        log_warn "Service Manager: NOT RUNNING"
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

    # Log file locations
    echo ""
    echo "============================================================"
    echo "  LOG FILES"
    echo "============================================================"
    echo ""
    echo -e "  ${BLUE}PM Logs:       $LOG_DIR/portfolio_manager.log${NC}"
    echo -e "  ${BLUE}Frontend Logs: $LOG_DIR/frontend.log${NC}"
    echo -e "  ${BLUE}OpenAlgo Logs: $OPENALGO_DIR/log/openalgo.log${NC}"
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
        log_warn "Pipeline Monitor daemon is NOT running - attempting to start..."

        # Try to start via launchctl first (if plist exists)
        PLIST_PATH="$HOME/Library/LaunchAgents/com.itj.pipeline-monitor.plist"
        if [ -f "$PLIST_PATH" ]; then
            log_info "Loading monitor daemon via launchctl..."
            launchctl load "$PLIST_PATH" 2>/dev/null
            sleep 2
            if is_monitor_running; then
                log_success "Pipeline Monitor daemon started successfully"
                return 0
            fi
        fi

        # Fallback: Start monitor directly in background
        log_info "Starting Pipeline Monitor in background..."
        MONITOR_LOG="$LOG_DIR/pipeline_monitor.log"
        nohup python3 "$SCRIPT_DIR/monitor_pipeline.py" --daemon >> "$MONITOR_LOG" 2>&1 &
        MONITOR_PID=$!
        echo $MONITOR_PID > "$MONITOR_PID_FILE"
        sleep 2

        if ps -p $MONITOR_PID > /dev/null 2>&1; then
            log_success "Pipeline Monitor started (PID: $MONITOR_PID)"
            return 0
        else
            log_warn "Failed to start Pipeline Monitor daemon"
            echo ""
            echo -e "  ${YELLOW}⚠️  The pipeline monitor daemon could not be started.${NC}"
            echo -e "  ${YELLOW}   You can try starting it manually:${NC}"
            echo ""
            echo -e "    ${BLUE}python3 monitor_pipeline.py --daemon${NC}"
            echo ""
            return 1
        fi
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
        start_tunnel  # Start tunnel in background before PM
        start_service_manager  # Start service manager early so it can manage other services
        start_portfolio_manager "${@:2}"
        start_frontend
        start_margin_monitor
        echo ""
        echo "============================================================"
        echo -e "  ${GREEN}✅ ALL SERVICES STARTED${NC}"
        echo "============================================================"
        echo ""
        echo -e "  ${GREEN}🖥️  Frontend:       http://localhost:$FRONTEND_PORT${NC}"
        echo -e "  ${GREEN}📊 PM API:         http://127.0.0.1:$PM_PORT${NC}"
        echo -e "  ${GREEN}📈 Margin Monitor: http://localhost:$MARGIN_MONITOR_PORT${NC}"
        echo -e "  ${GREEN}🔧 Service Manager: http://localhost:$SERVICE_MANAGER_PORT${NC}"
        echo -e "  ${GREEN}🔌 OpenAlgo:       $OPENALGO_URL${NC}"
        echo ""
        echo -e "  ${BLUE}📝 View PM logs:             tail -f $LOG_DIR/portfolio_manager.log${NC}"
        echo -e "  ${BLUE}📝 View Frontend logs:       tail -f $LOG_DIR/frontend.log${NC}"
        echo -e "  ${BLUE}📝 View Margin Monitor logs: tail -f $LOG_DIR/margin_monitor.log${NC}"
        echo -e "  ${BLUE}📝 View Service Manager logs: tail -f $LOG_DIR/service_manager.log${NC}"
        echo ""
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
        start_service_manager
        start_portfolio_manager "${@:2}"
        start_frontend
        start_margin_monitor
        echo ""
        log_success "All services restarted"
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
    frontend)
        # Start only Frontend
        start_frontend
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
    margin-monitor)
        # Start only Margin Monitor
        start_margin_monitor
        ;;
    service-manager)
        # Start only Service Manager
        start_service_manager
        ;;
    logs)
        # Tail all logs
        echo "Tailing logs from: $LOG_DIR"
        echo "Press Ctrl+C to stop"
        echo ""
        tail -f "$LOG_DIR/portfolio_manager.log" "$LOG_DIR/frontend.log" "$LOG_DIR/margin_monitor.log" 2>/dev/null || tail -f "$LOG_DIR/portfolio_manager.log" 2>/dev/null || echo "No log files found yet"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|openalgo|tunnel|frontend|pm|margin-monitor|service-manager|logs} [--test-mode] [--silent]"
        echo ""
        echo "Commands:"
        echo "  start           - Start all services (OpenAlgo, Tunnel, PM, Frontend, Margin Monitor, Service Manager)"
        echo "  stop            - Stop all services"
        echo "  status          - Show status of all services"
        echo "  restart         - Restart all services"
        echo "  openalgo        - Start only OpenAlgo"
        echo "  tunnel          - Start only Cloudflare Tunnel"
        echo "  frontend        - Start only Frontend"
        echo "  pm              - Start Portfolio Manager + Tunnel (OpenAlgo must be running)"
        echo "  margin-monitor  - Start only Margin Monitor (auto-hedge system)"
        echo "  service-manager - Start only Service Manager (for restarting services via UI)"
        echo "  logs            - Tail all log files"
        echo ""
        echo "Options:"
        echo "  --test-mode  Enable test mode (1 lot orders only, logged calculated lots)"
        echo "  --silent     Disable voice announcements (use visual alerts instead)"
        echo ""
        echo "Examples:"
        echo "  $0 start              # Normal startup (all services)"
        echo "  $0 start --test-mode  # Start in test mode"
        echo "  $0 start --silent     # Start in silent mode (no voice)"
        echo "  $0 pm --test-mode --silent  # PM with both modes"
        echo "  $0 margin-monitor     # Start only Margin Monitor"
        echo "  $0 logs               # View all logs in real-time"
        echo ""
        echo "Log files:"
        echo "  PM:             $LOG_DIR/portfolio_manager.log"
        echo "  Frontend:       $LOG_DIR/frontend.log"
        echo "  Margin Monitor: $LOG_DIR/margin_monitor.log"
        echo "  OpenAlgo:       $OPENALGO_DIR/log/openalgo.log"
        echo ""
        exit 1
        ;;
esac
