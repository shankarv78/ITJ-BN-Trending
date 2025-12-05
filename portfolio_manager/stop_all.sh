#!/bin/bash

# =============================================================================
# UNIFIED SHUTDOWN SCRIPT
# Stops OpenAlgo and Portfolio Manager gracefully
# =============================================================================

# Configuration
OPENALGO_PORT=5000
PM_PORT=5002
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENALGO_DIR="$HOME/openalgo"

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
echo "  TOM BASSO PORTFOLIO MANAGER - SHUTDOWN"
echo "  End of Day Cleanup"
echo "============================================================"
echo ""

# -----------------------------------------------------------------------------
# Stop Portfolio Manager
# -----------------------------------------------------------------------------

stop_portfolio_manager() {
    log_info "Checking Portfolio Manager..."
    
    PM_PIDS=$(lsof -ti:$PM_PORT 2>/dev/null || true)
    
    if [ -z "$PM_PIDS" ]; then
        log_warn "Portfolio Manager is not running (port $PM_PORT)"
        return 0
    fi
    
    log_info "Stopping Portfolio Manager on port $PM_PORT..."
    
    for PID in $PM_PIDS; do
        log_info "  Sending SIGTERM to PID $PID..."
        kill -TERM $PID 2>/dev/null || true
    done
    
    # Wait a bit for graceful shutdown
    sleep 2
    
    # Check if still running
    PM_PIDS=$(lsof -ti:$PM_PORT 2>/dev/null || true)
    if [ ! -z "$PM_PIDS" ]; then
        log_warn "  Processes still running, sending SIGKILL..."
        for PID in $PM_PIDS; do
            kill -9 $PID 2>/dev/null || true
        done
        sleep 1
    fi
    
    # Verify stopped
    PM_PIDS=$(lsof -ti:$PM_PORT 2>/dev/null || true)
    if [ -z "$PM_PIDS" ]; then
        log_success "Portfolio Manager stopped"
    else
        log_error "Failed to stop Portfolio Manager"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Stop OpenAlgo
# -----------------------------------------------------------------------------

stop_openalgo() {
    log_info "Checking OpenAlgo..."
    
    # First try from PID file
    if [ -f "$SCRIPT_DIR/.openalgo.pid" ]; then
        OPENALGO_PID=$(cat "$SCRIPT_DIR/.openalgo.pid")
        if ps -p $OPENALGO_PID > /dev/null 2>&1; then
            log_info "Stopping OpenAlgo (PID $OPENALGO_PID from PID file)..."
            kill -TERM $OPENALGO_PID 2>/dev/null || true
            sleep 2
        fi
        rm -f "$SCRIPT_DIR/.openalgo.pid"
    fi
    
    # Also check by port
    OPENALGO_PIDS=$(lsof -ti:$OPENALGO_PORT 2>/dev/null || true)
    
    if [ -z "$OPENALGO_PIDS" ]; then
        log_warn "OpenAlgo is not running (port $OPENALGO_PORT)"
        return 0
    fi
    
    log_info "Stopping OpenAlgo on port $OPENALGO_PORT..."
    
    for PID in $OPENALGO_PIDS; do
        log_info "  Sending SIGTERM to PID $PID..."
        kill -TERM $PID 2>/dev/null || true
    done
    
    # Wait for graceful shutdown
    sleep 3
    
    # Check if still running
    OPENALGO_PIDS=$(lsof -ti:$OPENALGO_PORT 2>/dev/null || true)
    if [ ! -z "$OPENALGO_PIDS" ]; then
        log_warn "  Processes still running, sending SIGKILL..."
        for PID in $OPENALGO_PIDS; do
            kill -9 $PID 2>/dev/null || true
        done
        sleep 1
    fi
    
    # Verify stopped
    OPENALGO_PIDS=$(lsof -ti:$OPENALGO_PORT 2>/dev/null || true)
    if [ -z "$OPENALGO_PIDS" ]; then
        log_success "OpenAlgo stopped"
    else
        log_error "Failed to stop OpenAlgo"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Stop any stray gunicorn processes
# -----------------------------------------------------------------------------

stop_gunicorn() {
    log_info "Checking for stray gunicorn processes..."
    
    GUNICORN_PIDS=$(pgrep -f "gunicorn.*openalgo\|gunicorn.*app:app" 2>/dev/null || true)
    
    if [ -z "$GUNICORN_PIDS" ]; then
        return 0
    fi
    
    log_info "Found gunicorn processes: $GUNICORN_PIDS"
    
    for PID in $GUNICORN_PIDS; do
        log_info "  Stopping gunicorn PID $PID..."
        kill -TERM $PID 2>/dev/null || true
    done
    
    sleep 2
    
    # Force kill if needed
    GUNICORN_PIDS=$(pgrep -f "gunicorn.*openalgo\|gunicorn.*app:app" 2>/dev/null || true)
    if [ ! -z "$GUNICORN_PIDS" ]; then
        for PID in $GUNICORN_PIDS; do
            kill -9 $PID 2>/dev/null || true
        done
    fi
    
    log_success "Gunicorn processes cleaned up"
}

# -----------------------------------------------------------------------------
# Show final status
# -----------------------------------------------------------------------------

show_final_status() {
    echo ""
    echo "============================================================"
    echo "  FINAL STATUS"
    echo "============================================================"
    echo ""
    
    # Check OpenAlgo
    if lsof -ti:$OPENALGO_PORT > /dev/null 2>&1; then
        log_error "OpenAlgo: STILL RUNNING on port $OPENALGO_PORT"
    else
        log_success "OpenAlgo: STOPPED"
    fi
    
    # Check Portfolio Manager
    if lsof -ti:$PM_PORT > /dev/null 2>&1; then
        log_error "Portfolio Manager: STILL RUNNING on port $PM_PORT"
    else
        log_success "Portfolio Manager: STOPPED"
    fi
    
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

case "${1:-all}" in
    all)
        stop_portfolio_manager
        stop_openalgo
        stop_gunicorn
        show_final_status
        log_success "End of day shutdown complete. See you tomorrow! 👋"
        ;;
    pm)
        stop_portfolio_manager
        log_success "Portfolio Manager stopped (OpenAlgo still running)"
        ;;
    openalgo)
        stop_openalgo
        stop_gunicorn
        log_success "OpenAlgo stopped"
        ;;
    status)
        show_final_status
        ;;
    force)
        log_warn "Force stopping all processes..."
        
        # Kill everything on the ports
        for PORT in $PM_PORT $OPENALGO_PORT; do
            PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
            if [ ! -z "$PIDS" ]; then
                log_info "Force killing processes on port $PORT: $PIDS"
                kill -9 $PIDS 2>/dev/null || true
            fi
        done
        
        # Kill gunicorn
        pkill -9 -f "gunicorn.*app:app" 2>/dev/null || true
        
        sleep 1
        show_final_status
        ;;
    *)
        echo "Usage: $0 {all|pm|openalgo|status|force}"
        echo ""
        echo "Commands:"
        echo "  all      - Stop both OpenAlgo and Portfolio Manager (default)"
        echo "  pm       - Stop only Portfolio Manager"
        echo "  openalgo - Stop only OpenAlgo"
        echo "  status   - Show status of all services"
        echo "  force    - Force kill all processes (use if normal stop fails)"
        echo ""
        exit 1
        ;;
esac

