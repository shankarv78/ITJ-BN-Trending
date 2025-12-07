#!/bin/bash
# ============================================
# Install Pipeline Monitor as LaunchAgent
# ============================================
# This makes the monitor auto-start on login
# and auto-restart if it crashes.
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.itj.pipeline-monitor.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🔧 Pipeline Monitor Service Installer"
echo "======================================"
echo ""

# Check if plist exists
if [ ! -f "$PLIST_SRC" ]; then
    echo "❌ Error: $PLIST_SRC not found!"
    exit 1
fi

# Create LaunchAgents directory if needed
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing service if running
if launchctl list | grep -q "com.itj.pipeline-monitor"; then
    echo "⏹️  Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
echo "📋 Copying plist to ~/Library/LaunchAgents/..."
cp "$PLIST_SRC" "$PLIST_DEST"

# Load the service
echo "▶️  Loading service..."
launchctl load "$PLIST_DEST"

# Check if it started
sleep 1
if launchctl list | grep -q "com.itj.pipeline-monitor"; then
    echo ""
    echo "✅ Pipeline Monitor service installed successfully!"
    echo ""
    echo "📌 Service Details:"
    echo "   - Starts automatically on login"
    echo "   - Restarts automatically if it crashes"
    echo "   - Respects MCX market hours (sleeps outside trading hours)"
    echo ""
    echo "📁 Log files:"
    echo "   - $SCRIPT_DIR/monitor.log (main log)"
    echo "   - $SCRIPT_DIR/monitor_launchd.log (stdout)"
    echo "   - $SCRIPT_DIR/monitor_launchd_error.log (errors)"
    echo ""
    echo "🔧 Management Commands:"
    echo "   Stop:    launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
    echo "   Start:   launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
    echo "   Status:  launchctl list | grep pipeline-monitor"
    echo "   Uninstall: ./uninstall_monitor_service.sh"
else
    echo "❌ Failed to start service. Check logs for details."
    exit 1
fi

