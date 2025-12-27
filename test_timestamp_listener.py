#!/usr/bin/env python3
"""
Test Timestamp Listener
-----------------------
Standalone webhook listener to test Pine Script timestamp methods.

Usage:
    python3 test_timestamp_listener.py

Then expose with ngrok:
    ngrok http 5004

Or use cloudflared:
    cloudflared tunnel --url http://localhost:5004
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from dateutil import parser as date_parser

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store received signals for analysis
received_signals = []


def get_current_time_info():
    """Get current time in various formats for comparison."""
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()

    return {
        'server_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'server_local': now_local.strftime('%Y-%m-%dT%H:%M:%S'),
        'server_local_tz': now_local.astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')
    }


def analyze_timestamp(ts_str: str, label: str, server_time: datetime) -> dict:
    """Analyze a timestamp string and compare with server time."""
    try:
        parsed = date_parser.parse(ts_str)

        # If naive, assume IST (Pine Script outputs chart timezone, our charts are IST)
        # This matches the fix in PM's signal_validator.py
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
            tz_assumed = "IST (naive)"
        else:
            tz_assumed = str(parsed.tzinfo)

        # Convert to UTC for comparison
        parsed_utc = parsed.astimezone(timezone.utc)
        server_utc = server_time.astimezone(timezone.utc) if server_time.tzinfo else server_time.replace(tzinfo=timezone.utc)

        diff_seconds = (server_utc - parsed_utc).total_seconds()

        return {
            'label': label,
            'raw': ts_str,
            'tz_assumed': tz_assumed,
            'parsed_utc': parsed_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'parsed_ist': parsed.astimezone(IST).strftime('%Y-%m-%dT%H:%M:%S IST'),
            'diff_from_server_seconds': round(diff_seconds, 1),
            'interpretation': interpret_diff(diff_seconds)
        }
    except Exception as e:
        return {
            'label': label,
            'raw': ts_str,
            'error': str(e)
        }


def interpret_diff(diff_seconds: float) -> str:
    """Interpret the time difference."""
    if abs(diff_seconds) < 5:
        return "✅ CORRECT (within 5s of server time)"
    elif diff_seconds > 0:
        return f"⏰ Signal is {abs(diff_seconds):.0f}s IN THE PAST"
    else:
        return f"⚠️ Signal is {abs(diff_seconds):.0f}s IN THE FUTURE (timezone bug?)"


@app.route('/webhook', methods=['POST'])
def webhook():
    """Receive and analyze test signals."""
    server_time = datetime.now(timezone.utc)

    try:
        # Parse JSON
        if request.is_json:
            data = request.get_json()
        else:
            # TradingView may not set Content-Type
            data = json.loads(request.data.decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        return jsonify({'error': str(e)}), 400

    logger.info("=" * 60)
    logger.info("📨 RECEIVED TEST SIGNAL")
    logger.info("=" * 60)

    # Log raw data
    logger.info(f"Raw payload: {json.dumps(data, indent=2)}")

    # Get server time info
    server_info = get_current_time_info()
    logger.info(f"Server time (UTC): {server_info['server_utc']}")
    logger.info(f"Server time (local): {server_info['server_local']}")

    # Analyze each timestamp method
    results = []

    if 'timenow' in data:
        result = analyze_timestamp(data['timenow'], 'timenow', server_time)
        results.append(result)
        logger.info(f"\n🔹 timenow: {result['raw']}")
        logger.info(f"   Timezone assumed: {result.get('tz_assumed', 'N/A')}")
        logger.info(f"   Parsed as IST: {result.get('parsed_ist', 'N/A')}")
        logger.info(f"   Parsed as UTC: {result.get('parsed_utc', 'N/A')}")
        logger.info(f"   Diff from server: {result.get('diff_from_server_seconds', 'N/A')}s")
        logger.info(f"   {result.get('interpretation', result.get('error', ''))}")

    if 'time_close' in data:
        result = analyze_timestamp(data['time_close'], 'time_close', server_time)
        results.append(result)
        logger.info(f"\n🔹 time_close: {result['raw']}")
        logger.info(f"   Timezone assumed: {result.get('tz_assumed', 'N/A')}")
        logger.info(f"   Parsed as IST: {result.get('parsed_ist', 'N/A')}")
        logger.info(f"   Parsed as UTC: {result.get('parsed_utc', 'N/A')}")
        logger.info(f"   Diff from server: {result.get('diff_from_server_seconds', 'N/A')}s")
        logger.info(f"   {result.get('interpretation', result.get('error', ''))}")

    if 'time_open' in data:
        result = analyze_timestamp(data['time_open'], 'time_open (bar open)', server_time)
        results.append(result)
        logger.info(f"\n🔹 time_open: {result['raw']}")
        logger.info(f"   Timezone assumed: {result.get('tz_assumed', 'N/A')}")
        logger.info(f"   Parsed as IST: {result.get('parsed_ist', 'N/A')}")
        logger.info(f"   Parsed as UTC: {result.get('parsed_utc', 'N/A')}")
        logger.info(f"   Diff from server: {result.get('diff_from_server_seconds', 'N/A')}s")
        logger.info(f"   {result.get('interpretation', result.get('error', ''))}")

    logger.info("=" * 60)

    # Determine winner
    winner = None
    min_diff = float('inf')
    for r in results:
        diff = abs(r.get('diff_from_server_seconds', float('inf')))
        if diff < min_diff:
            min_diff = diff
            winner = r['label']

    if winner:
        logger.info(f"🏆 WINNER: {winner} (closest to server time, {min_diff:.1f}s diff)")

    logger.info("=" * 60 + "\n")

    # Store for later analysis
    received_signals.append({
        'received_at': server_time.isoformat(),
        'data': data,
        'analysis': results,
        'winner': winner
    })

    return jsonify({
        'status': 'received',
        'server_time': server_info,
        'analysis': results,
        'winner': winner
    }), 200


@app.route('/signals', methods=['GET'])
def list_signals():
    """List all received signals for review."""
    return jsonify({
        'count': len(received_signals),
        'signals': received_signals[-20:]  # Last 20
    }), 200


@app.route('/clear', methods=['POST'])
def clear_signals():
    """Clear stored signals."""
    global received_signals
    received_signals = []
    return jsonify({'status': 'cleared'}), 200


@app.route('/health', methods=['GET'])
def health():
    """Health check."""
    return jsonify({
        'status': 'healthy',
        'signals_received': len(received_signals),
        'server_time': get_current_time_info()
    }), 200


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════════╗
║           TIMESTAMP TEST WEBHOOK LISTENER                   ║
╠══════════════════════════════════════════════════════════════╣
║  This server listens for test signals and compares:         ║
║    - timenow     (Pine Script real-time)                    ║
║    - time_close  (Bar close time)                           ║
║    - time        (Bar open time)                            ║
╠══════════════════════════════════════════════════════════════╣
║  USAGE:                                                      ║
║  1. Start this server: python3 test_timestamp_listener.py   ║
║  2. Expose with ngrok: ngrok http 5004                       ║
║     Or cloudflared: cloudflared tunnel --url localhost:5004  ║
║  3. Copy the public URL to TradingView alert webhook        ║
║  4. Apply test_timestamp_signal.pine to a 1-min chart       ║
║  5. Create alert with "Any alert() function call"           ║
╚══════════════════════════════════════════════════════════════╝
    """)

    logger.info("Starting test webhook listener on port 5004...")
    logger.info("Endpoints:")
    logger.info("  POST /webhook  - Receive test signals")
    logger.info("  GET  /signals  - List received signals")
    logger.info("  POST /clear    - Clear signal history")
    logger.info("  GET  /health   - Health check")

    app.run(host='0.0.0.0', port=5004, debug=False)
