#!/usr/bin/env python3
"""
Signal Listener for TradingView Webhook Testing

A simple Flask server that receives and logs signals from TradingView alerts.
Use this with the Bitcoin_EOD_Signal_Tester.pine indicator to test
EOD signal generation and webhook integration.

Features:
- Receives JSON webhooks from TradingView
- Parses and validates signal structure
- Logs signals with color-coded output
- Tracks signal statistics
- Supports EOD_MONITOR, BASE_ENTRY, PYRAMID, and EXIT signals

Usage:
    python signal_listener.py [--port PORT] [--host HOST] [--debug]

Examples:
    # Start on default port 5050
    python signal_listener.py

    # Start on custom port
    python signal_listener.py --port 8080

    # Enable debug mode
    python signal_listener.py --debug

TradingView Alert Setup:
    1. Add Bitcoin_EOD_Signal_Tester indicator to chart
    2. Create alert on indicator
    3. Set webhook URL: http://<your-ip>:5050/webhook
    4. Enable "Webhook URL" in alert settings

Note: For public access, use Cloudflare Tunnel:
    cloudflared tunnel --url http://localhost:5050
    Then use the Cloudflare URL in TradingView webhook settings.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Flask not installed. Install with: pip install flask")
    sys.exit(1)

# ============================================================
# ANSI Color Codes for Terminal Output
# ============================================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

def color(text: str, color_code: str) -> str:
    """Apply color to text for terminal output."""
    return f"{color_code}{text}{Colors.RESET}"

# ============================================================
# Signal Statistics Tracker
# ============================================================
class SignalStats:
    """Track signal statistics."""

    def __init__(self):
        self.counts = defaultdict(int)
        self.first_received = {}
        self.last_received = {}
        self.instruments = set()

    def record(self, signal_type: str, instrument: str):
        """Record a signal."""
        now = datetime.now()
        key = f"{signal_type}:{instrument}"

        self.counts[key] += 1
        self.instruments.add(instrument)

        if key not in self.first_received:
            self.first_received[key] = now
        self.last_received[key] = now

    def get_summary(self) -> dict:
        """Get statistics summary."""
        return {
            'total_signals': sum(self.counts.values()),
            'by_type': dict(self.counts),
            'instruments': list(self.instruments),
            'first_received': {k: v.isoformat() for k, v in self.first_received.items()},
            'last_received': {k: v.isoformat() for k, v in self.last_received.items()}
        }

    def print_summary(self):
        """Print formatted summary to console."""
        print(f"\n{color('=' * 50, Colors.CYAN)}")
        print(color("📊 SIGNAL STATISTICS", Colors.BOLD + Colors.CYAN))
        print(color('=' * 50, Colors.CYAN))
        print(f"Total Signals Received: {color(str(sum(self.counts.values())), Colors.GREEN)}")
        print(f"Instruments: {', '.join(self.instruments)}")
        print(f"\nBy Type:")
        for key, count in sorted(self.counts.items()):
            signal_type, instrument = key.split(':')
            type_color = self._get_type_color(signal_type)
            print(f"  {color(signal_type, type_color):30} [{instrument}]: {count}")
        print(color('=' * 50, Colors.CYAN))

    def _get_type_color(self, signal_type: str) -> str:
        """Get color for signal type."""
        colors = {
            'EOD_MONITOR': Colors.YELLOW,
            'BASE_ENTRY': Colors.GREEN,
            'PYRAMID': Colors.BLUE,
            'EXIT': Colors.RED
        }
        return colors.get(signal_type, Colors.RESET)


# ============================================================
# Signal Parser
# ============================================================
def parse_signal(data: dict) -> tuple:
    """
    Parse incoming signal data.

    Returns:
        Tuple of (signal_type, parsed_data, is_valid, error_message)
    """
    if not isinstance(data, dict):
        return None, None, False, "Data must be a dictionary"

    signal_type = data.get('type', '').upper()
    instrument = data.get('instrument', 'UNKNOWN')

    if not signal_type:
        return None, None, False, "Missing 'type' field"

    if signal_type == 'EOD_MONITOR':
        # Validate EOD_MONITOR structure
        required = ['instrument', 'timestamp', 'price', 'conditions', 'indicators', 'position_status']
        missing = [f for f in required if f not in data]
        if missing:
            return signal_type, data, False, f"Missing fields: {', '.join(missing)}"

        # Validate conditions
        conditions = data.get('conditions', {})
        required_conditions = ['rsi_condition', 'ema_condition', 'dc_condition',
                               'adx_condition', 'er_condition', 'st_condition',
                               'not_doji', 'long_entry', 'long_exit']
        missing_cond = [c for c in required_conditions if c not in conditions]
        if missing_cond:
            return signal_type, data, False, f"Missing conditions: {', '.join(missing_cond)}"

        # Validate indicators
        indicators = data.get('indicators', {})
        required_indicators = ['rsi', 'ema', 'dc_upper', 'adx', 'er', 'supertrend', 'atr']
        missing_ind = [i for i in required_indicators if i not in indicators]
        if missing_ind:
            return signal_type, data, False, f"Missing indicators: {', '.join(missing_ind)}"

        return signal_type, data, True, None

    elif signal_type in ['BASE_ENTRY', 'PYRAMID', 'EXIT']:
        # Validate regular signal structure
        required = ['instrument', 'position', 'price', 'timestamp']
        missing = [f for f in required if f not in data]
        if missing:
            return signal_type, data, False, f"Missing fields: {', '.join(missing)}"

        return signal_type, data, True, None

    else:
        return signal_type, data, False, f"Unknown signal type: {signal_type}"


def format_eod_signal(data: dict) -> str:
    """Format EOD_MONITOR signal for display."""
    conditions = data.get('conditions', {})
    indicators = data.get('indicators', {})
    position = data.get('position_status', {})

    # Count conditions met
    condition_fields = ['rsi_condition', 'ema_condition', 'dc_condition',
                        'adx_condition', 'er_condition', 'st_condition', 'not_doji']
    conditions_met = sum(1 for c in condition_fields if conditions.get(c))

    lines = [
        f"  Instrument: {data.get('instrument')}",
        f"  Price: {data.get('price')}",
        f"  Timestamp: {data.get('timestamp')}",
        f"  Conditions: {conditions_met}/7 {'✅ ALL MET' if conditions_met == 7 else '⏳ Waiting'}",
        f"    RSI: {'✓' if conditions.get('rsi_condition') else '✗'} ({indicators.get('rsi', 0):.2f})",
        f"    EMA: {'✓' if conditions.get('ema_condition') else '✗'} ({indicators.get('ema', 0):.2f})",
        f"    DC:  {'✓' if conditions.get('dc_condition') else '✗'} ({indicators.get('dc_upper', 0):.2f})",
        f"    ADX: {'✓' if conditions.get('adx_condition') else '✗'} ({indicators.get('adx', 0):.2f})",
        f"    ER:  {'✓' if conditions.get('er_condition') else '✗'} ({indicators.get('er', 0):.4f})",
        f"    ST:  {'✓' if conditions.get('st_condition') else '✗'} ({indicators.get('supertrend', 0):.2f})",
        f"    Doji: {'✓' if conditions.get('not_doji') else '✗'}",
        f"  Entry Signal: {'YES' if conditions.get('long_entry') else 'NO'}",
        f"  Exit Signal: {'YES' if conditions.get('long_exit') else 'NO'}",
        f"  Position: {'IN' if position.get('in_position') else 'FLAT'}, Pyramids: {position.get('pyramid_count', 0)}",
    ]
    return '\n'.join(lines)


def format_regular_signal(data: dict) -> str:
    """Format regular signal (BASE_ENTRY, PYRAMID, EXIT) for display."""
    lines = [
        f"  Instrument: {data.get('instrument')}",
        f"  Position: {data.get('position')}",
        f"  Price: {data.get('price')}",
        f"  Stop: {data.get('stop', 'N/A')}",
        f"  Timestamp: {data.get('timestamp')}",
    ]

    if 'lots' in data:
        lines.append(f"  Lots: {data.get('lots')}")
    if 'reason' in data:
        lines.append(f"  Reason: {data.get('reason')}")
    if 'atr' in data:
        lines.append(f"  ATR: {data.get('atr')}")
    if 'er' in data:
        lines.append(f"  ER: {data.get('er')}")

    return '\n'.join(lines)


# ============================================================
# Flask Application
# ============================================================
app = Flask(__name__)
stats = SignalStats()

# Suppress Flask's default logging for cleaner output
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook from TradingView."""
    try:
        # Get JSON data
        data = request.get_json(force=True)

        if data is None:
            return jsonify({'status': 'error', 'message': 'No JSON data'}), 400

        # Parse signal
        signal_type, parsed_data, is_valid, error = parse_signal(data)

        # Record in stats
        if signal_type:
            instrument = data.get('instrument', 'UNKNOWN')
            stats.record(signal_type, instrument)

        # Format and print
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        if signal_type == 'EOD_MONITOR':
            type_color = Colors.YELLOW
            formatted = format_eod_signal(data)
        elif signal_type == 'BASE_ENTRY':
            type_color = Colors.GREEN
            formatted = format_regular_signal(data)
        elif signal_type == 'PYRAMID':
            type_color = Colors.BLUE
            formatted = format_regular_signal(data)
        elif signal_type == 'EXIT':
            type_color = Colors.RED
            formatted = format_regular_signal(data)
        else:
            type_color = Colors.RESET
            formatted = json.dumps(data, indent=2)

        # Print signal
        print(f"\n{color('─' * 50, Colors.CYAN)}")
        print(f"[{now}] {color(signal_type or 'UNKNOWN', Colors.BOLD + type_color)}")

        if is_valid:
            print(color("Status: ✅ Valid", Colors.GREEN))
        else:
            print(color(f"Status: ⚠️ Invalid - {error}", Colors.RED))

        print(formatted)
        print(color('─' * 50, Colors.CYAN))

        # Return response
        if is_valid:
            return jsonify({
                'status': 'success',
                'signal_type': signal_type,
                'received_at': now
            }), 200
        else:
            return jsonify({
                'status': 'warning',
                'signal_type': signal_type,
                'error': error,
                'received_at': now
            }), 200

    except json.JSONDecodeError as e:
        print(color(f"\n❌ JSON Parse Error: {e}", Colors.RED))
        return jsonify({'status': 'error', 'message': f'JSON parse error: {e}'}), 400

    except Exception as e:
        print(color(f"\n❌ Error: {e}", Colors.RED))
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get signal statistics."""
    return jsonify(stats.get_summary())


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Signal Listener',
        'version': '1.0',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/', methods=['GET'])
def home():
    """Home page with usage info."""
    return """
    <html>
    <head>
        <title>TradingView Signal Listener</title>
        <style>
            body { font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }
            h1 { color: #00d4ff; }
            code { background: #16213e; padding: 2px 6px; border-radius: 3px; }
            .endpoint { margin: 10px 0; padding: 10px; background: #16213e; border-radius: 5px; }
            .method { color: #00d4ff; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🎯 TradingView Signal Listener</h1>
        <p>Receiving and logging webhook signals from TradingView.</p>

        <h2>Endpoints:</h2>
        <div class="endpoint">
            <span class="method">POST</span> <code>/webhook</code> - Receive TradingView alerts
        </div>
        <div class="endpoint">
            <span class="method">GET</span> <code>/stats</code> - View signal statistics
        </div>
        <div class="endpoint">
            <span class="method">GET</span> <code>/health</code> - Health check
        </div>

        <h2>Setup:</h2>
        <ol>
            <li>Add <code>Bitcoin_EOD_Signal_Tester</code> indicator to your chart</li>
            <li>Create an alert on the indicator</li>
            <li>Set webhook URL to: <code>http://your-ip:5000/webhook</code></li>
            <li>Watch this console for incoming signals!</li>
        </ol>

        <h2>For Public Access (ngrok):</h2>
        <pre>
ngrok http 5000
# Use the ngrok URL in TradingView webhook settings
        </pre>
    </body>
    </html>
    """


# ============================================================
# Main Entry Point
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description='TradingView Signal Listener for EOD Testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python signal_listener.py                 # Start on default port 5050
  python signal_listener.py --port 8080     # Custom port
  python signal_listener.py --debug         # Enable debug mode

TradingView Setup:
  1. Add Bitcoin_EOD_Signal_Tester indicator to chart
  2. Create alert on indicator
  3. Set webhook URL: http://<your-ip>:<port>/webhook
  4. Enable "Webhook URL" in alert settings

For public access, use Cloudflare Tunnel:
  cloudflared tunnel --url http://localhost:5050
  Then use the Cloudflare URL in TradingView
        """
    )

    parser.add_argument('--port', type=int, default=5050,
                        help='Port to listen on (default: 5050)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='Enable Flask debug mode')

    args = parser.parse_args()

    # Print startup banner
    print(color("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🎯 TRADINGVIEW SIGNAL LISTENER                            ║
║   EOD Signal Testing Tool                                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """, Colors.CYAN))

    print(f"Starting server on {color(f'http://{args.host}:{args.port}', Colors.GREEN)}")
    print(f"Webhook endpoint: {color(f'http://{args.host}:{args.port}/webhook', Colors.YELLOW)}")
    print(f"Stats endpoint: {color(f'http://{args.host}:{args.port}/stats', Colors.BLUE)}")
    print(f"\nPress {color('Ctrl+C', Colors.RED)} to stop and see statistics\n")
    print(color('═' * 60, Colors.CYAN))
    print("Waiting for signals...")

    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        stats.print_summary()
        print(color("\n👋 Server stopped.", Colors.YELLOW))


if __name__ == '__main__':
    main()
