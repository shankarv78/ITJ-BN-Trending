#!/usr/bin/env python3
"""
🔔 Pipeline Monitor Daemon
==========================
Runs in background, checks pipeline health every N seconds.
Triggers macOS alert + sound when something breaks.

Usage:
  python monitor_pipeline.py              # Run in foreground (respects market hours)
  python monitor_pipeline.py --check      # One-time health check (ignores market hours)
  python monitor_pipeline.py --force      # Run continuously, ignoring market hours
  python monitor_pipeline.py --daemon     # Run in background
  python monitor_pipeline.py --stop       # Stop background daemon
  python monitor_pipeline.py --status     # Check if daemon running
  python monitor_pipeline.py --market     # Show MCX market hours status

Shortcuts:
  python monitor_pipeline.py -c           # Same as --check
  python monitor_pipeline.py -f           # Same as --force
  python monitor_pipeline.py -d           # Same as --daemon
  python monitor_pipeline.py -m           # Same as --market

Configuration:
  CHECK_INTERVAL = 30  seconds between checks
  ALERT_COOLDOWN = 300  seconds between repeated alerts for same issue

MCX Market Hours (IST):
  Winter (Nov-Mar): 9:00 AM - 11:55 PM
  Summer (Apr-Oct): 9:00 AM - 11:30 PM (US DST adjustment)
  No trading on weekends (Saturday, Sunday)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import pytz

# Configuration
CHECK_INTERVAL_NORMAL = 10   # seconds when all OK
CHECK_INTERVAL_ALERT = 3     # seconds when issue detected
VOICE_REPEAT_INTERVAL = 5    # seconds between voice repeats during alert
OUTSIDE_MARKET_CHECK = 60    # seconds between checks when outside market hours
PM_URL = "http://127.0.0.1:5002"
OPENALGO_URL = "http://127.0.0.1:5000"
CONFIG_FILE = "openalgo_config.json"
PID_FILE = "/tmp/pm_monitor.pid"
LOG_FILE = "monitor.log"

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# Track state
last_voice_time: float = 0
current_issues: Dict[str, str] = {}
last_market_status_log: float = 0


def is_winter_month(month: int) -> bool:
    """
    Check if the month is in winter period (November to March).
    MCX adjusts timings based on US Daylight Saving Time.
    Winter: November (11) to March (3) - market closes at 11:55 PM
    Summer: April (4) to October (10) - market closes at 11:30 PM
    """
    return month in [11, 12, 1, 2, 3]


def get_market_hours(now_ist: datetime) -> Tuple[int, int, int, int]:
    """
    Get MCX market hours based on current month.
    Returns: (start_hour, start_min, end_hour, end_min)

    MCX Trading Hours (IST):
      Winter (Nov-Mar): 9:00 AM - 11:55 PM
      Summer (Apr-Oct): 9:00 AM - 11:30 PM
    """
    if is_winter_month(now_ist.month):
        # Winter: 9:00 AM to 11:55 PM
        return (9, 0, 23, 55)
    else:
        # Summer: 9:00 AM to 11:30 PM
        return (9, 0, 23, 30)


def is_market_open() -> Tuple[bool, str]:
    """
    Check if MCX market is currently open.
    Returns: (is_open, reason)
    """
    now_ist = datetime.now(IST)

    # Check weekend (Monday=0, Sunday=6)
    if now_ist.weekday() == 5:  # Saturday
        return False, "Weekend (Saturday)"
    if now_ist.weekday() == 6:  # Sunday
        return False, "Weekend (Sunday)"

    # Get market hours for current month
    start_h, start_m, end_h, end_m = get_market_hours(now_ist)

    # Current time in minutes from midnight
    current_minutes = now_ist.hour * 60 + now_ist.minute
    market_start = start_h * 60 + start_m
    market_end = end_h * 60 + end_m

    # Check if within market hours
    if current_minutes < market_start:
        return False, f"Before market hours (opens at {start_h}:{start_m:02d} AM)"
    if current_minutes > market_end:
        season = "Winter" if is_winter_month(now_ist.month) else "Summer"
        return False, f"After market hours ({season}: closes at {end_h}:{end_m:02d})"

    return True, "Market open"


def get_time_until_market_open() -> int:
    """
    Get seconds until market opens.
    Returns seconds to wait (capped at 1 hour for reasonable sleep intervals).
    """
    now_ist = datetime.now(IST)

    # If weekend, calculate time to Monday 9 AM
    if now_ist.weekday() == 5:  # Saturday
        # Days until Monday
        days_to_monday = 2
        next_open = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
        next_open = next_open + timedelta(days=days_to_monday)
    elif now_ist.weekday() == 6:  # Sunday
        days_to_monday = 1
        next_open = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
        next_open = next_open + timedelta(days=days_to_monday)
    else:
        # Weekday - either before market or after market
        start_h, start_m, end_h, end_m = get_market_hours(now_ist)
        current_minutes = now_ist.hour * 60 + now_ist.minute
        market_start = start_h * 60 + start_m
        market_end = end_h * 60 + end_m

        if current_minutes < market_start:
            # Before market opens today
            next_open = now_ist.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        elif current_minutes > market_end:
            # After market close - next open is tomorrow (or Monday if Friday)
            if now_ist.weekday() == 4:  # Friday
                days_to_monday = 3
            else:
                days_to_monday = 1
            next_open = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
            next_open = next_open + timedelta(days=days_to_monday)
        else:
            # Market is open
            return 0

    seconds_until_open = (next_open - now_ist).total_seconds()
    # Cap at 1 hour to periodically re-check (in case of date/time issues)
    return min(int(seconds_until_open), 3600)

def log(msg: str, level: str = "INFO"):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if level == "ERROR":
        print(line)  # Also print errors to console

def load_api_key() -> Optional[str]:
    """Load API key from config"""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get('openalgo_api_key')
    except:
        return None

def play_alarm_sound():
    """
    Play a real alarm sound - loud and attention-grabbing
    """
    # Play alarm sound multiple times for urgency
    alarm_sounds = [
        "/System/Library/Sounds/Funk.aiff",      # Attention-grabbing
        "/System/Library/Sounds/Ping.aiff",      # Sharp
        "/System/Library/Sounds/Glass.aiff",     # Clear
    ]

    try:
        # Play the alarm sequence
        for sound in alarm_sounds:
            if os.path.exists(sound):
                subprocess.run(["afplay", "-v", "2", sound], capture_output=True, timeout=2)
                time.sleep(0.1)
    except:
        pass

def play_voice_alert(message: str):
    """
    Play voice announcement
    """
    global last_voice_time
    now = time.time()

    # Only play voice if enough time has passed
    if now - last_voice_time >= VOICE_REPEAT_INTERVAL:
        last_voice_time = now
        try:
            # Use Alex voice for urgency, rate 200 for faster speech
            subprocess.run(
                ["say", "-v", "Alex", "-r", "200", message],
                capture_output=True,
                timeout=10
            )
        except:
            pass

def trigger_alarm(component: str, issue: str):
    """
    Trigger full alarm sequence: sound + voice
    """
    # 1. Play alarm sound first
    play_alarm_sound()

    # 2. Then voice announcement
    voice_msg = f"Alert! {component} is down. {issue}"
    play_voice_alert(voice_msg)

    # 3. Show macOS notification
    script = f'''
    display notification "{issue}" with title "🔴 {component} DOWN!" sound name "Basso"
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True)
    except:
        pass

def trigger_recovery_alert(component: str):
    """
    Alert when component recovers
    """
    try:
        subprocess.run(
            ["say", "-v", "Samantha", f"{component} is back online"],
            capture_output=True,
            timeout=5
        )
        script = f'''
        display notification "{component} recovered" with title "✅ {component} OK" sound name "Glass"
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True)
    except:
        pass

def check_pm() -> tuple[bool, str]:
    """Check Portfolio Manager health"""
    try:
        response = requests.get(f"{PM_URL}/health", timeout=5)
        if response.status_code == 200:
            return True, "OK"
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)

def check_openalgo() -> tuple[bool, str]:
    """Check OpenAlgo health"""
    try:
        response = requests.get(f"{OPENALGO_URL}/", timeout=5)
        if response.status_code == 200:
            return True, "OK"
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)

def check_broker(api_key: str) -> tuple[bool, str]:
    """Check broker connection and mode via funds endpoint"""
    try:
        # Use funds endpoint to check broker connection AND mode
        response = requests.post(
            f"{OPENALGO_URL}/api/v1/funds",
            json={"apikey": api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            mode = data.get('mode', 'unknown')

            # Check if in analyzer mode (not connected to real broker)
            if mode == 'analyze':
                return False, "⚠️ ANALYZER MODE - not connected to broker!"

            # Check if funds request was successful
            if data.get('status') == 'success':
                return True, f"Live mode - broker connected"

            return True, f"OK (mode: {mode})"
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

def check_tunnel() -> tuple[bool, str]:
    """Check Cloudflare tunnel is running"""
    try:
        # Cloudflare tunnel runs metrics server on port 20241
        response = requests.get("http://127.0.0.1:20241/metrics", timeout=3)
        if response.status_code == 200:
            return True, "Tunnel active"
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Tunnel DOWN - no signals from TradingView!"
    except Exception as e:
        return False, str(e)

def run_checks() -> Dict[str, tuple[bool, str]]:
    """Run all health checks"""
    api_key = load_api_key()

    results = {
        "Tunnel": check_tunnel(),  # Check tunnel FIRST - most critical for signals
        "PM": check_pm(),
        "OpenAlgo": check_openalgo(),
    }

    if api_key:
        results["Broker"] = check_broker(api_key)

    return results

def monitor_loop(ignore_market_hours: bool = False):
    """Main monitoring loop with dynamic intervals and market hours awareness"""
    global current_issues, last_market_status_log

    log("Monitor started", "INFO")
    now_ist = datetime.now(IST)
    season = "Winter" if is_winter_month(now_ist.month) else "Summer"
    _, _, end_h, end_m = get_market_hours(now_ist)
    print(f"🔔 Monitor active - MCX {season} hours (9:00 AM - {end_h}:{end_m:02d} PM)")
    print(f"   Normal: every {CHECK_INTERVAL_NORMAL}s | Alert: every {CHECK_INTERVAL_ALERT}s")
    if ignore_market_hours:
        print(f"   ⚠️  FORCE MODE: Ignoring market hours - monitoring 24/7")
    else:
        print(f"   Outside market hours: sleep mode")

    consecutive_failures = {"Tunnel": 0, "PM": 0, "OpenAlgo": 0, "Broker": 0}
    previous_issues: Dict[str, str] = {}

    while True:
        try:
            # Check if market is open (skip if force mode)
            if not ignore_market_hours:
                market_open, market_reason = is_market_open()

                if not market_open:
                    # Market is closed - sleep mode
                    now = time.time()

                    # Log market status every 30 minutes
                    if now - last_market_status_log > 1800:
                        log(f"Market closed: {market_reason}. Sleeping...", "INFO")
                        last_market_status_log = now

                    # Calculate sleep time (check every minute or until market opens)
                    sleep_time = min(get_time_until_market_open(), OUTSIDE_MARKET_CHECK)
                    time.sleep(max(sleep_time, OUTSIDE_MARKET_CHECK))
                    continue

            # Market is open - run health checks
            results = run_checks()

            # Track current issues
            new_issues: Dict[str, str] = {}

            for component, (status, msg) in results.items():
                if status:
                    # Component is OK
                    if component in consecutive_failures:
                        consecutive_failures[component] = 0

                    # Check if this was previously down (recovery)
                    if component in previous_issues:
                        log(f"{component} RECOVERED", "INFO")
                        trigger_recovery_alert(component)
                else:
                    # Component is DOWN
                    consecutive_failures[component] = consecutive_failures.get(component, 0) + 1

                    # Alert immediately on first failure (no delay)
                    if consecutive_failures[component] >= 1:
                        new_issues[component] = msg

                        # Log first occurrence
                        if component not in previous_issues:
                            log(f"{component} FAILED: {msg}", "ERROR")

                        # Trigger alarm (will repeat voice based on interval)
                        trigger_alarm(component, msg)

            # Update issue tracking
            previous_issues = new_issues.copy()
            current_issues = new_issues.copy()

            # Dynamic interval: fast checking during issues, slow when OK
            if new_issues:
                check_interval = CHECK_INTERVAL_ALERT
            else:
                check_interval = CHECK_INTERVAL_NORMAL

            # Log periodic status (every 5 minutes when OK)
            if not new_issues and int(time.time()) % 300 < CHECK_INTERVAL_NORMAL:
                status_str = ", ".join(f"{k}:{'✓' if v[0] else '✗'}" for k, v in results.items())
                log(f"Status: {status_str}", "INFO")

        except Exception as e:
            log(f"Monitor error: {e}", "ERROR")

        time.sleep(check_interval)

def write_pid():
    """Write PID file for daemon"""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def read_pid() -> Optional[int]:
    """Read PID from file"""
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except:
        return None

def is_running() -> bool:
    """Check if daemon is already running"""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except OSError:
            pass
    return False

def stop_daemon():
    """Stop the daemon"""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"✓ Stopped monitor daemon (PID {pid})")
            os.remove(PID_FILE)
        except OSError:
            print("Daemon not running")
    else:
        print("No PID file found")

def start_daemon():
    """Start as background daemon"""
    if is_running():
        print("Monitor daemon already running")
        return

    # Fork to background
    pid = os.fork()
    if pid > 0:
        print(f"✓ Monitor daemon started (PID {pid})")
        print(f"  Normal check: every {CHECK_INTERVAL_NORMAL}s")
        print(f"  Alert mode:   every {CHECK_INTERVAL_ALERT}s + voice every {VOICE_REPEAT_INTERVAL}s")
        print(f"  Log file: {LOG_FILE}")
        print(f"  Stop with: python monitor_pipeline.py --stop")
        return

    # Child process
    os.setsid()

    # Redirect stdio to log file instead of /dev/null for debugging
    sys.stdin = open('/dev/null')
    # Keep stdout/stderr going to log

    write_pid()

    # Handle termination
    def cleanup(signum, frame):
        try:
            os.remove(PID_FILE)
        except:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    monitor_loop()

def print_market_status():
    """Print current market status and hours"""
    now_ist = datetime.now(IST)
    market_open, reason = is_market_open()
    season = "Winter" if is_winter_month(now_ist.month) else "Summer"
    start_h, start_m, end_h, end_m = get_market_hours(now_ist)

    print(f"\n📊 MCX Market Status")
    print(f"   Current Time (IST): {now_ist.strftime('%Y-%m-%d %H:%M:%S %A')}")
    print(f"   Season: {season} (Nov-Mar=Winter, Apr-Oct=Summer)")
    print(f"   Market Hours: {start_h}:{start_m:02d} AM - {end_h}:{end_m:02d} PM")
    print(f"   Status: {'🟢 OPEN' if market_open else '🔴 CLOSED'} - {reason}")

    if not market_open:
        wait_time = get_time_until_market_open()
        hours, remainder = divmod(wait_time, 3600)
        minutes, _ = divmod(remainder, 60)
        print(f"   Next Open: ~{int(hours)}h {int(minutes)}m")
    print()


def run_single_check():
    """Run a single health check and print results (ignores market hours)"""
    now_ist = datetime.now(IST)
    print(f"\n🔍 Pipeline Health Check - {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 50)

    results = run_checks()
    all_ok = True

    for component, (status, msg) in results.items():
        if status:
            print(f"   ✅ {component}: {msg}")
        else:
            print(f"   ❌ {component}: {msg}")
            all_ok = False

    print("=" * 50)
    if all_ok:
        print("✅ All systems operational!")
    else:
        print("⚠️  Some components need attention!")
    print()

    return all_ok


def main():
    parser = argparse.ArgumentParser(description='Pipeline Monitor Daemon')
    parser.add_argument('--daemon', '-d', action='store_true', help='Run as background daemon')
    parser.add_argument('--stop', action='store_true', help='Stop daemon')
    parser.add_argument('--status', action='store_true', help='Check daemon status')
    parser.add_argument('--market', '-m', action='store_true', help='Show MCX market hours status')
    parser.add_argument('--test-alert', action='store_true', help='Test alert sound')
    parser.add_argument('--force', '-f', action='store_true', help='Force monitoring even outside market hours')
    parser.add_argument('--check', '-c', action='store_true', help='Run one-time health check and exit (ignores market hours)')
    args = parser.parse_args()

    os.chdir(Path(__file__).parent)

    if args.stop:
        stop_daemon()
    elif args.status:
        if is_running():
            pid = read_pid()
            print(f"✓ Monitor daemon running (PID {pid})")
        else:
            print("✗ Monitor daemon not running")
        print_market_status()
    elif args.market:
        print_market_status()
    elif args.test_alert:
        print("Testing alarm sequence...")
        print("1. Playing alarm sounds...")
        play_alarm_sound()
        print("2. Playing voice alert...")
        trigger_alarm("Test Component", "This is a test alert")
        print("3. Testing recovery notification...")
        time.sleep(2)
        trigger_recovery_alert("Test Component")
        print("Done!")
    elif args.check:
        # One-time health check (ignores market hours)
        run_single_check()
    elif args.daemon:
        start_daemon()
    else:
        # Run in foreground
        now_ist = datetime.now(IST)
        season = "Winter" if is_winter_month(now_ist.month) else "Summer"
        _, _, end_h, end_m = get_market_hours(now_ist)

        print(f"🔔 Pipeline Monitor (Ctrl+C to stop)")
        print(f"   MCX {season} hours: 9:00 AM - {end_h}:{end_m:02d} PM (Mon-Fri)")
        print(f"   Normal: every {CHECK_INTERVAL_NORMAL}s | Alert: every {CHECK_INTERVAL_ALERT}s")
        print(f"   Voice repeats every {VOICE_REPEAT_INTERVAL}s during alerts")
        print(f"   Log file: {LOG_FILE}")

        market_open, reason = is_market_open()
        if not market_open and not args.force:
            print(f"\n⏳ Market currently closed: {reason}")
            print(f"   Monitor will sleep and wake when market opens.")
            print(f"   Use --force / -f to monitor anyway, or --check / -c for one-time check")
        elif args.force:
            print(f"\n⚠️  FORCE MODE: Ignoring market hours")
        print()

        try:
            monitor_loop(ignore_market_hours=args.force)
        except KeyboardInterrupt:
            print("\nMonitor stopped")

if __name__ == "__main__":
    main()
