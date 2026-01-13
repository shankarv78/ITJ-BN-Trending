"""
Voice Announcer for Portfolio Manager

Announces trade events via text-to-speech:
- Pre-trade: Details before execution
- Post-trade: Confirmation after execution
- Errors: Repeated until acknowledged

On macOS: Uses native 'say' command (best quality)
On other platforms: Falls back to pyttsx3

Usage:
    announcer = VoiceAnnouncer()
    announcer.announce_pre_trade(instrument, position, lots, price, risk)
    announcer.announce_trade_executed(instrument, position, lots, price)
    announcer.announce_error(error_message)  # Repeats until acknowledged
"""

import threading
import time
import queue
import logging
import subprocess
import platform
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Check platform for TTS method
IS_MACOS = platform.system() == 'Darwin'

# Try to import pyttsx3 as fallback for non-macOS
TTS_AVAILABLE = False
if not IS_MACOS:
    try:
        import pyttsx3
        TTS_AVAILABLE = True
    except ImportError:
        logger.warning("pyttsx3 not installed. Voice announcements disabled.")
else:
    TTS_AVAILABLE = True  # macOS uses 'say' command
    logger.info("Using macOS native 'say' command for voice announcements")

# Try to import speech recognition for voice acknowledgment
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    logger.info("speech_recognition not installed. Voice acknowledgment disabled.")


class VoiceAnnouncer:
    """
    Text-to-speech announcer for trading events

    Features:
    - Pre-trade announcements (no confirmation needed)
    - Post-trade confirmations
    - Error announcements with repeat until acknowledged
    - Optional voice acknowledgment
    - Silent mode: No voice, uses macOS notifications instead
    """

    def __init__(self,
                 enabled: bool = True,
                 rate: int = 175,  # Words per minute
                 volume: float = 1.0,
                 voice_index: int = 0,  # 0 = default voice
                 error_repeat_interval: float = 30.0,  # Seconds between error repeats
                 silent_mode: bool = False):  # Silent mode: no voice, visual alerts only
        """
        Initialize voice announcer

        Args:
            enabled: Whether announcements are enabled
            rate: Speech rate (words per minute)
            volume: Volume (0.0 to 1.0)
            voice_index: Index of voice to use (0 = default)
            error_repeat_interval: Seconds between error repeat announcements
            silent_mode: If True, disable voice and use macOS notifications instead
        """
        self.silent_mode = silent_mode
        self.enabled = enabled and TTS_AVAILABLE and not silent_mode
        self.rate = rate
        self.volume = volume
        self.voice_index = voice_index
        self.error_repeat_interval = error_repeat_interval

        # TTS engine (created per-thread for thread safety)
        self._engine_lock = threading.Lock()

        # Error queue for repeat announcements
        self._error_queue = queue.Queue()
        self._pending_errors = []  # List of unacknowledged errors
        self._error_lock = threading.Lock()
        self._error_thread: Optional[threading.Thread] = None
        self._stop_error_thread = threading.Event()

        # Callbacks
        self._on_error_acknowledged: Optional[Callable] = None

        # Dual-channel confirmation manager (for Telegram + macOS simultaneous confirmations)
        self._confirmation_manager = None

        # Voice recognition
        self._voice_listener_thread: Optional[threading.Thread] = None
        self._stop_voice_listener = threading.Event()

        if self.silent_mode:
            logger.info("Voice announcer initialized in SILENT MODE (visual alerts only)")
            self._start_error_repeat_thread()  # Still need error repeat for dialogs
        elif self.enabled:
            logger.info("Voice announcer initialized")
            self._start_error_repeat_thread()
        else:
            logger.info("Voice announcer disabled (pyttsx3 not available)")

    def set_confirmation_manager(self, manager):
        """
        Set the dual-channel confirmation manager.

        When set, confirmations will be sent to BOTH macOS dialog AND Telegram
        simultaneously. First response wins, other channel is cancelled.

        Args:
            manager: SyncConfirmationBridge instance (from telegram_bot.sync_bridge)
        """
        self._confirmation_manager = manager
        logger.info("[VoiceAnnouncer] Dual-channel confirmation manager set")

    def _speak(self, text: str, priority: str = "normal", voice: str = None):
        """
        Speak text using TTS

        On macOS: Uses native 'say' command with Alex/Samantha voices
        On other platforms: Uses pyttsx3

        Args:
            text: Text to speak
            priority: "normal", "high", or "critical"
            voice: Voice name (macOS: "Alex", "Samantha", etc.)
        """
        if self.silent_mode:
            logger.info(f"[SILENT MODE] Would announce: {text}")
            return

        if not self.enabled:
            logger.debug(f"[VOICE DISABLED] Would announce: {text}")
            return

        def speak_thread():
            try:
                if IS_MACOS:
                    # Use macOS native 'say' command - MUCH better quality
                    voice_name = voice or "Alex"  # Alex for alerts, Samantha for confirmations

                    # Rate: 180-220 is good for clarity (default is ~175)
                    cmd = ["say", "-v", voice_name, "-r", str(self.rate), text]

                    logger.info(f"[VOICE:{voice_name}] {text}")
                    result = subprocess.run(cmd, capture_output=True, timeout=30)

                    if result.returncode != 0:
                        logger.error(f"say command failed: {result.stderr.decode()}")
                else:
                    # Fallback to pyttsx3 for non-macOS
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty('rate', self.rate)
                    engine.setProperty('volume', self.volume)
                    logger.info(f"[VOICE] {text}")
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()

            except subprocess.TimeoutExpired:
                logger.error("Voice announcement timed out")
            except Exception as e:
                logger.error(f"TTS error: {e}")

        # Run in thread to not block
        thread = threading.Thread(target=speak_thread, daemon=True)
        thread.start()

        # Wait for high priority messages
        if priority in ("high", "critical"):
            thread.join(timeout=30)

    # =========================================================================
    # SILENT MODE NOTIFICATIONS (macOS)
    # =========================================================================

    def show_notification(self, title: str, message: str):
        """
        Show macOS notification center notification (auto-dismisses)

        Used in silent mode for non-critical alerts.

        Args:
            title: Notification title
            message: Notification message
        """
        if not IS_MACOS:
            logger.info(f"[NOTIFICATION] {title}: {message}")
            return

        def notify_thread():
            try:
                # Escape quotes in message
                safe_message = message.replace('"', '\\"').replace("'", "\\'")
                safe_title = title.replace('"', '\\"').replace("'", "\\'")

                cmd = [
                    "osascript", "-e",
                    f'display notification "{safe_message}" with title "{safe_title}"'
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=10)

                if result.returncode != 0:
                    logger.error(f"Notification failed: {result.stderr.decode()}")
                else:
                    logger.info(f"[NOTIFICATION] {title}: {message}")

            except Exception as e:
                logger.error(f"Failed to show notification: {e}")

        # Run in thread to not block
        threading.Thread(target=notify_thread, daemon=True).start()

    def show_transient_alert(self, title: str, message: str, timeout_seconds: int = 15):
        """
        Show a transient macOS dialog that auto-dismisses after timeout

        Used in silent mode for alerts that need attention but aren't critical.
        Dialog will close automatically after timeout_seconds.

        Args:
            title: Alert title
            message: Alert message
            timeout_seconds: Seconds before auto-dismiss (default: 15)
        """
        if not IS_MACOS:
            logger.warning(f"[TRANSIENT ALERT] {title}: {message}")
            return

        def alert_thread():
            try:
                # Escape quotes
                safe_message = message.replace('"', '\\"').replace("'", "\\'")
                safe_title = title.replace('"', '\\"').replace("'", "\\'")

                # AppleScript with timeout - dialog auto-dismisses
                script = f'''
                tell application "System Events"
                    display dialog "{safe_message}" ¬
                        with title "{safe_title}" ¬
                        buttons {{"OK"}} ¬
                        default button "OK" ¬
                        giving up after {timeout_seconds}
                end tell
                '''

                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=timeout_seconds + 5
                )

                logger.info(f"[TRANSIENT ALERT] {title}: {message} (shown for {timeout_seconds}s)")

            except subprocess.TimeoutExpired:
                logger.debug(f"Transient alert timed out as expected")
            except Exception as e:
                logger.error(f"Failed to show transient alert: {e}")

        # Run in thread to not block
        threading.Thread(target=alert_thread, daemon=True).start()

    # =========================================================================
    # PRE-TRADE ANNOUNCEMENT
    # =========================================================================

    def announce_pre_trade(self,
                          instrument: str,
                          position: str,
                          signal_type: str,
                          lots: int,
                          price: float,
                          stop: float,
                          risk_amount: float,
                          risk_percent: float):
        """
        Announce trade details before execution

        Args:
            instrument: GOLD_MINI or BANK_NIFTY
            position: Long_1, Long_2, etc.
            signal_type: BASE_ENTRY, PYRAMID, EXIT
            lots: Number of lots
            price: Entry/exit price
            stop: Stop loss price
            risk_amount: Risk in rupees
            risk_percent: Risk as percentage of equity
        """
        # Format instrument name for speech
        if instrument == "GOLD_MINI":
            instrument_name = "Gold Mini"
        elif instrument == "COPPER":
            instrument_name = "Copper"
        elif instrument == "SILVER_MINI":
            instrument_name = "Silver Mini"
        else:
            instrument_name = "Bank Nifty"

        # Format position
        pos_parts = position.split("_")
        layer = pos_parts[1] if len(pos_parts) > 1 else "1"

        # Build announcement
        if signal_type == "BASE_ENTRY":
            announcement = (
                f"Placing {instrument_name} base entry. "
                f"{lots} lots at {price:.0f}. "
                f"Stop loss at {stop:.0f}. "
                f"Risk: {risk_amount:,.0f} rupees, {risk_percent:.1f} percent."
            )
        elif signal_type == "PYRAMID":
            announcement = (
                f"Adding {instrument_name} pyramid level {layer}. "
                f"{lots} lots at {price:.0f}. "
                f"Stop at {stop:.0f}. "
                f"Additional risk: {risk_amount:,.0f} rupees."
            )
        elif signal_type == "EXIT":
            announcement = (
                f"Exiting {instrument_name} position {layer}. "
                f"{lots} lots at {price:.0f}."
            )
        else:
            announcement = (
                f"{signal_type} signal for {instrument_name}. "
                f"{lots} lots at {price:.0f}."
            )

        # Use Alex voice for trade announcements (clear, authoritative)
        self._speak(announcement, voice="Alex")

    # =========================================================================
    # POST-TRADE ANNOUNCEMENT
    # =========================================================================

    def announce_trade_executed(self,
                               instrument: str,
                               position: str,
                               signal_type: str,
                               lots: int,
                               price: float,
                               order_id: Optional[str] = None,
                               pnl: Optional[float] = None):
        """
        Announce successful trade execution

        Args:
            instrument: GOLD_MINI or BANK_NIFTY
            position: Long_1, Long_2, etc.
            signal_type: BASE_ENTRY, PYRAMID, EXIT
            lots: Number of lots executed
            price: Execution price
            order_id: Broker order ID
            pnl: P&L for exits
        """
        if instrument == "GOLD_MINI":
            instrument_name = "Gold Mini"
        elif instrument == "COPPER":
            instrument_name = "Copper"
        elif instrument == "SILVER_MINI":
            instrument_name = "Silver Mini"
        else:
            instrument_name = "Bank Nifty"

        if signal_type == "EXIT" and pnl is not None:
            pnl_word = "profit" if pnl >= 0 else "loss"
            announcement = (
                f"{instrument_name} exit executed. "
                f"{lots} lots at {price:.0f}. "
                f"Realized {pnl_word}: {abs(pnl):,.0f} rupees."
            )
        else:
            action = "entry" if signal_type == "BASE_ENTRY" else signal_type.lower()
            announcement = (
                f"{instrument_name} {action} executed. "
                f"{lots} lots filled at {price:.0f}."
            )

        # Use Samantha voice for confirmations (friendly, clear)
        self._speak(announcement, voice="Samantha")

    # =========================================================================
    # ERROR ANNOUNCEMENT (REPEATS UNTIL ACKNOWLEDGED)
    # =========================================================================

    def announce_error(self, error_message: str, error_type: str = "execution"):
        """
        Announce error, show popup dialog, and repeat until acknowledged

        In silent mode: Shows dialog only (no voice)
        In normal mode: Voice announcement + dialog

        Args:
            error_message: Error description
            error_type: Type of error (execution, connection, validation)
        """
        timestamp = datetime.now()
        error_id = f"{timestamp.strftime('%H%M%S')}_{len(self._pending_errors)}"

        error_info = {
            'id': error_id,
            'message': error_message,
            'type': error_type,
            'timestamp': timestamp,
            'acknowledged': False
        }

        with self._error_lock:
            self._pending_errors.append(error_info)

        logger.error(f"[ERROR] {error_id}: {error_message}")

        if self.silent_mode:
            # Silent mode: Log and show dialog only (no voice)
            logger.info(f"[SILENT MODE] Critical error - showing dialog: {error_message}")
        else:
            # Normal mode: Voice announcement
            announcement = (
                f"Alert! {error_type} error. {error_message}. "
                f"Please acknowledge to stop this alert."
            )
            self._speak(announcement, priority="critical", voice="Alex")

        # Show macOS popup dialog (non-blocking, in separate thread)
        # This happens in BOTH silent and normal modes for critical errors
        if IS_MACOS:
            threading.Thread(
                target=self._show_error_dialog,
                args=(error_id, error_type, error_message),
                daemon=True
            ).start()

    def _show_error_dialog(self, error_id: str, error_type: str, error_message: str):
        """Show macOS native dialog for error acknowledgment"""
        try:
            # AppleScript for native macOS dialog
            script = f'''
            display dialog "⚠️ {error_type.upper()} ERROR\\n\\n{error_message}\\n\\nClick OK to acknowledge and stop alerts." ¬
                with title "Portfolio Manager Alert" ¬
                buttons {{"OK"}} ¬
                default button "OK" ¬
                with icon caution
            '''

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                # User clicked OK - acknowledge the error
                self.acknowledge_error(error_id)
                logger.info(f"Error {error_id} acknowledged via dialog")
        except subprocess.TimeoutExpired:
            logger.warning(f"Error dialog timed out for {error_id}")
        except Exception as e:
            logger.error(f"Failed to show error dialog: {e}")

    def acknowledge_error(self, error_id: Optional[str] = None) -> bool:
        """
        Acknowledge an error to stop repeat announcements

        Args:
            error_id: Specific error ID, or None to acknowledge all

        Returns:
            True if error(s) acknowledged
        """
        with self._error_lock:
            if error_id:
                # Acknowledge specific error
                for error in self._pending_errors:
                    if error['id'] == error_id:
                        error['acknowledged'] = True
                        self._pending_errors.remove(error)
                        if not self.silent_mode:
                            self._speak("Error acknowledged.", priority="high", voice="Samantha")
                        logger.info(f"Error acknowledged: {error_id}")
                        return True
                return False
            else:
                # Acknowledge all errors
                count = len(self._pending_errors)
                self._pending_errors.clear()
                if count > 0:
                    if not self.silent_mode:
                        self._speak(f"{count} errors acknowledged.", priority="high", voice="Samantha")
                    logger.info(f"All {count} errors acknowledged")
                return count > 0

    def get_pending_errors(self) -> list:
        """Get list of unacknowledged errors"""
        with self._error_lock:
            return [e.copy() for e in self._pending_errors]

    def _start_error_repeat_thread(self):
        """Start background thread to repeat error announcements"""
        if self._error_thread and self._error_thread.is_alive():
            return

        self._stop_error_thread.clear()
        self._error_thread = threading.Thread(target=self._error_repeat_loop, daemon=True)
        self._error_thread.start()

    def _error_repeat_loop(self):
        """Background loop to repeat unacknowledged errors"""
        while not self._stop_error_thread.is_set():
            time.sleep(self.error_repeat_interval)

            with self._error_lock:
                if self._pending_errors:
                    count = len(self._pending_errors)
                    latest = self._pending_errors[-1]

                    if self.silent_mode:
                        # Silent mode: Show transient notification reminder
                        self.show_notification(
                            "PM Error Reminder",
                            f"{count} unacknowledged error(s). Latest: {latest['message'][:50]}..."
                        )
                    else:
                        # Normal mode: Voice reminder
                        announcement = (
                            f"Reminder: {count} unacknowledged error{'s' if count > 1 else ''}. "
                            f"Latest: {latest['message']}. "
                            f"Please acknowledge."
                        )

                        # Don't block the loop - use Alex for urgency
                        threading.Thread(
                            target=self._speak,
                            args=(announcement, "normal", "Alex"),
                            daemon=True
                        ).start()

    # =========================================================================
    # VOICE ACKNOWLEDGMENT (OPTIONAL)
    # =========================================================================

    def start_voice_listener(self):
        """Start listening for voice acknowledgment commands"""
        if not SPEECH_RECOGNITION_AVAILABLE:
            logger.warning("Speech recognition not available. Install with: pip install SpeechRecognition pyaudio")
            return False

        if self._voice_listener_thread and self._voice_listener_thread.is_alive():
            return True

        self._stop_voice_listener.clear()
        self._voice_listener_thread = threading.Thread(target=self._voice_listener_loop, daemon=True)
        self._voice_listener_thread.start()
        logger.info("Voice listener started")
        return True

    def stop_voice_listener(self):
        """Stop voice listener"""
        self._stop_voice_listener.set()
        if self._voice_listener_thread:
            self._voice_listener_thread.join(timeout=5)

    def _voice_listener_loop(self):
        """Background loop to listen for voice commands"""
        if not SPEECH_RECOGNITION_AVAILABLE:
            return

        recognizer = sr.Recognizer()

        try:
            mic = sr.Microphone()
        except Exception as e:
            logger.error(f"Microphone not available: {e}")
            return

        # Adjust for ambient noise
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)

        logger.info("Voice listener ready. Say 'understood, will handle it' to acknowledge errors.")

        while not self._stop_voice_listener.is_set():
            try:
                with mic as source:
                    # Listen with timeout
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)

                # Recognize speech
                try:
                    text = recognizer.recognize_google(audio).lower()
                    logger.debug(f"Voice input: {text}")

                    # Check for acknowledgment phrases
                    ack_phrases = [
                        "understood",
                        "will handle it",
                        "acknowledged",
                        "got it",
                        "okay",
                        "ok"
                    ]

                    if any(phrase in text for phrase in ack_phrases):
                        logger.info(f"Voice acknowledgment received: {text}")
                        self.acknowledge_error()  # Acknowledge all

                except sr.UnknownValueError:
                    pass  # Couldn't understand
                except sr.RequestError as e:
                    logger.error(f"Speech recognition service error: {e}")
                    time.sleep(5)  # Wait before retry

            except sr.WaitTimeoutError:
                pass  # No speech detected in timeout period
            except Exception as e:
                logger.error(f"Voice listener error: {e}")
                time.sleep(1)

    # =========================================================================
    # VALIDATION CONFIRMATION (BLOCKING DIALOG)
    # =========================================================================

    def _request_dual_channel_confirmation(
        self,
        instrument: str,
        signal_type: str,
        rejection_reason: str,
        details: str
    ) -> bool:
        """
        Request confirmation via dual-channel (macOS dialog + Telegram).

        First response wins, other channel is cancelled.

        Args:
            instrument: e.g., "GOLD_MINI"
            signal_type: e.g., "BASE_ENTRY", "PYRAMID"
            rejection_reason: e.g., "signal_timestamp_in_future"
            details: Additional context about the rejection

        Returns:
            True = Execute anyway, False = Reject signal
        """
        try:
            from telegram_bot.confirmations import (
                ConfirmationType,
                ConfirmationAction,
                ConfirmationOption,
            )

            # Format the reason for display
            reason_display = rejection_reason.replace('_', ' ').title()

            logger.info(
                f"[VoiceAnnouncer] Requesting dual-channel confirmation for "
                f"{instrument} {signal_type}: {rejection_reason}"
            )

            result = self._confirmation_manager.request_confirmation(
                confirmation_type=ConfirmationType.VALIDATION_FAILED,
                context={
                    'Instrument': instrument,
                    'Signal': signal_type,
                    'Reason': reason_display,
                    'Details': details
                },
                options=[
                    ConfirmationOption(
                        ConfirmationAction.REJECT,
                        "Reject Signal",
                        is_default=True
                    ),
                    ConfirmationOption(
                        ConfirmationAction.EXECUTE_ANYWAY,
                        "Execute Anyway"
                    )
                ],
                timeout_seconds=300  # 5 minutes
            )

            execute = result.action == ConfirmationAction.EXECUTE_ANYWAY

            logger.info(
                f"[VoiceAnnouncer] Confirmation result: "
                f"action={result.action.value}, source={result.source}, execute={execute}"
            )

            # Voice feedback based on result
            if execute:
                if not self.silent_mode:
                    self._speak("Executing signal as requested.", priority="high", voice="Samantha")
            else:
                if not self.silent_mode:
                    self._speak("Signal rejected.", priority="high", voice="Samantha")

            return execute

        except Exception as e:
            logger.error(f"[VoiceAnnouncer] Dual-channel confirmation error: {e}")
            # On error, reject the signal for safety
            return False

    def request_validation_confirmation(
        self,
        instrument: str,
        signal_type: str,
        rejection_reason: str,
        details: str
    ) -> bool:
        """
        Show blocking dialog for validation failure confirmation.

        If dual-channel confirmation manager is set, sends to BOTH macOS dialog
        AND Telegram simultaneously. First response wins.

        Otherwise, voice announces the issue every 5 seconds until user responds.
        Returns True if user wants to execute anyway, False to reject.

        Args:
            instrument: e.g., "GOLD_MINI"
            signal_type: e.g., "BASE_ENTRY", "PYRAMID"
            rejection_reason: e.g., "signal_timestamp_in_future"
            details: Additional context about the rejection

        Returns:
            True = Execute anyway, False = Reject signal
        """
        # Check if dual-channel manager is available
        if self._confirmation_manager:
            return self._request_dual_channel_confirmation(
                instrument, signal_type, rejection_reason, details
            )

        # Fall back to macOS-only dialog
        if not IS_MACOS:
            logger.warning("Confirmation dialog only available on macOS. Auto-rejecting.")
            return False

        # Format the reason for display
        reason_display = rejection_reason.replace('_', ' ').title()

        # Build the dialog message
        dialog_message = (
            f"⚠️ SIGNAL VALIDATION FAILED\\n\\n"
            f"Instrument: {instrument}\\n"
            f"Signal: {signal_type}\\n"
            f"Reason: {reason_display}\\n\\n"
            f"Details: {details}\\n\\n"
            f"Do you want to execute anyway?"
        )

        # Voice message
        voice_message = (
            f"Attention! {instrument} {signal_type.replace('_', ' ')} signal validation failed. "
            f"Reason: {reason_display}. {details}. "
            f"Please confirm whether to execute or reject."
        )

        # Start repeating voice announcement in background
        stop_voice = threading.Event()

        def voice_repeat_loop():
            while not stop_voice.is_set():
                if not self.silent_mode:
                    self._speak(voice_message, priority="critical", voice="Alex")
                # Wait 5 seconds before repeating, but check stop flag frequently
                for _ in range(10):  # 10 × 0.5s = 5s
                    if stop_voice.is_set():
                        break
                    time.sleep(0.5)

        voice_thread = threading.Thread(target=voice_repeat_loop, daemon=True)
        voice_thread.start()

        try:
            # AppleScript for native macOS dialog with two buttons
            script = f'''
            display dialog "{dialog_message}" ¬
                with title "Signal Validation Failed" ¬
                buttons {{"Reject Signal", "Execute Anyway"}} ¬
                default button "Reject Signal" ¬
                cancel button "Reject Signal" ¬
                with icon caution
            '''

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            # Stop voice announcements
            stop_voice.set()
            voice_thread.join(timeout=2)

            if result.returncode == 0:
                # User clicked "Execute Anyway"
                output = result.stdout.strip()
                if "Execute Anyway" in output:
                    logger.info(f"User approved execution despite validation failure: {rejection_reason}")
                    if not self.silent_mode:
                        self._speak("Executing signal as requested.", priority="high", voice="Samantha")
                    return True

            # User clicked "Reject Signal" or dialog was cancelled
            logger.info(f"User confirmed rejection: {rejection_reason}")
            if not self.silent_mode:
                self._speak("Signal rejected.", priority="high", voice="Samantha")
            return False

        except subprocess.TimeoutExpired:
            stop_voice.set()
            logger.warning(f"Confirmation dialog timed out for {instrument} {signal_type}")
            if not self.silent_mode:
                self._speak("Confirmation timed out. Signal rejected for safety.", priority="high", voice="Alex")
            return False
        except Exception as e:
            stop_voice.set()
            logger.error(f"Failed to show confirmation dialog: {e}")
            return False

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    def shutdown(self):
        """Shutdown announcer and background threads"""
        self._stop_error_thread.set()
        self._stop_voice_listener.set()

        if self._error_thread:
            self._error_thread.join(timeout=2)
        if self._voice_listener_thread:
            self._voice_listener_thread.join(timeout=2)

        logger.info("Voice announcer shutdown")


# Global instance
_announcer: Optional[VoiceAnnouncer] = None


def get_announcer() -> Optional[VoiceAnnouncer]:
    """Get global voice announcer instance"""
    return _announcer


def init_announcer(silent_mode: bool = False, **kwargs) -> VoiceAnnouncer:
    """
    Initialize global voice announcer

    Args:
        silent_mode: If True, disable voice and use visual alerts only
        **kwargs: Other VoiceAnnouncer parameters
    """
    global _announcer
    _announcer = VoiceAnnouncer(silent_mode=silent_mode, **kwargs)
    return _announcer
