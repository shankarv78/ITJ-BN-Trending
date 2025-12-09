"""
Safety Manager - Live Trading Safety Features

Implements:
1. Pre-order margin safety checks
2. Trading pause/resume (kill switch)
3. Market hours validation
4. Price sanity checks
"""
import logging
import threading
from datetime import datetime, time as dt_time
from typing import Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class MarginSafetyLevel(Enum):
    """Margin utilization safety levels"""
    SAFE = "safe"           # < 50% - all clear
    WARNING = "warning"     # 50-80% - voice warning, proceed
    CRITICAL = "critical"   # > 80% - block order, require override


class SafetyManager:
    """
    Centralized safety management for live trading

    Features:
    - Margin utilization checks before orders
    - Trading pause/resume (kill switch)
    - Market hours validation
    - Price sanity checks
    """

    # Margin thresholds
    MARGIN_WARNING_THRESHOLD = 0.50   # 50%
    MARGIN_CRITICAL_THRESHOLD = 0.80  # 80%

    # Price deviation threshold
    PRICE_DEVIATION_THRESHOLD = 0.05  # 5%

    # Market hours (IST)
    MARKET_HOURS = {
        'BANK_NIFTY': {
            'start': dt_time(9, 15),
            'end': dt_time(15, 30)
        },
        'GOLD_MINI': {
            'start': dt_time(9, 0),
            'end': dt_time(23, 30)  # Summer timing, winter is 23:55
        }
    }

    def __init__(self, portfolio_state_manager=None, voice_announcer=None, telegram_notifier=None, holiday_calendar=None):
        """
        Initialize SafetyManager

        Args:
            portfolio_state_manager: PortfolioStateManager for margin checks
            voice_announcer: VoiceAnnouncer for audio alerts
            telegram_notifier: TelegramNotifier for mobile alerts
            holiday_calendar: HolidayCalendar for market holiday checks
        """
        self.portfolio = portfolio_state_manager
        self.voice = voice_announcer
        self.telegram = telegram_notifier
        self.holiday_calendar = holiday_calendar

        # Trading state
        self._trading_paused = False
        self._pause_reason = None
        self._pause_lock = threading.Lock()

        # Last known prices for sanity checks
        self._last_prices: Dict[str, float] = {}
        self._price_lock = threading.Lock()

        logger.info(f"[SAFETY] SafetyManager initialized (holidays: {'enabled' if holiday_calendar else 'disabled'})")

    # =========================================================================
    # Trading Pause/Resume (Kill Switch)
    # =========================================================================

    def pause_trading(self, reason: str = "Manual pause") -> bool:
        """
        Pause trading - reject all new signals

        Args:
            reason: Reason for pausing

        Returns:
            True if paused successfully
        """
        with self._pause_lock:
            if self._trading_paused:
                logger.warning(f"[SAFETY] Trading already paused: {self._pause_reason}")
                return False

            self._trading_paused = True
            self._pause_reason = reason

        logger.warning(f"[SAFETY] ⚠️ TRADING PAUSED: {reason}")

        # Alert via voice
        if self.voice:
            self.voice._speak(
                f"Warning! Trading has been paused. Reason: {reason}",
                priority="critical",
                voice="Alex"
            )

        # Alert via Telegram
        if self.telegram:
            self.telegram.send_alert(f"⚠️ TRADING PAUSED\nReason: {reason}")

        return True

    def resume_trading(self) -> bool:
        """
        Resume trading - accept signals again

        Returns:
            True if resumed successfully
        """
        with self._pause_lock:
            if not self._trading_paused:
                logger.info("[SAFETY] Trading was not paused")
                return False

            old_reason = self._pause_reason
            self._trading_paused = False
            self._pause_reason = None

        logger.info(f"[SAFETY] ✅ TRADING RESUMED (was paused: {old_reason})")

        # Alert via voice
        if self.voice:
            self.voice._speak(
                "Trading has been resumed. System is now accepting signals.",
                priority="normal",
                voice="Samantha"
            )

        # Alert via Telegram
        if self.telegram:
            self.telegram.send_info(f"✅ TRADING RESUMED\nPrevious reason: {old_reason}")

        return True

    def is_trading_paused(self) -> Tuple[bool, Optional[str]]:
        """
        Check if trading is paused

        Returns:
            Tuple of (is_paused, reason)
        """
        with self._pause_lock:
            return self._trading_paused, self._pause_reason

    # =========================================================================
    # Margin Safety Checks
    # =========================================================================

    def check_margin_safety(
        self,
        estimated_margin_required: float = 0
    ) -> Tuple[MarginSafetyLevel, str, bool]:
        """
        Check margin utilization before placing an order

        Args:
            estimated_margin_required: Additional margin this order will use

        Returns:
            Tuple of (safety_level, message, should_proceed)
        """
        if not self.portfolio:
            logger.warning("[SAFETY] No portfolio manager - skipping margin check")
            return MarginSafetyLevel.SAFE, "No portfolio manager", True

        state = self.portfolio.get_current_state()

        # Calculate current and projected utilization
        current_utilization = state.margin_utilization_percent / 100.0

        # Project utilization if we add this order
        if state.margin_available > 0 and estimated_margin_required > 0:
            projected_margin_used = state.margin_used + estimated_margin_required
            projected_utilization = projected_margin_used / (state.margin_used + state.margin_available)
        else:
            projected_utilization = current_utilization

        # Determine safety level based on projected utilization
        if projected_utilization >= self.MARGIN_CRITICAL_THRESHOLD:
            level = MarginSafetyLevel.CRITICAL
            message = (
                f"CRITICAL: Margin utilization will be {projected_utilization*100:.1f}% "
                f"(threshold: {self.MARGIN_CRITICAL_THRESHOLD*100:.0f}%). "
                f"Order BLOCKED. Use override to force."
            )
            should_proceed = False

            # Voice alert
            if self.voice:
                self.voice.announce_error(
                    f"Order blocked! Margin utilization at {projected_utilization*100:.0f} percent. "
                    f"Exceeds {self.MARGIN_CRITICAL_THRESHOLD*100:.0f} percent safety limit.",
                    error_type="margin"
                )

            # Telegram alert
            if self.telegram:
                self.telegram.send_alert(
                    f"🛑 ORDER BLOCKED - MARGIN CRITICAL\n"
                    f"Current: {current_utilization*100:.1f}%\n"
                    f"Projected: {projected_utilization*100:.1f}%\n"
                    f"Threshold: {self.MARGIN_CRITICAL_THRESHOLD*100:.0f}%"
                )

        elif projected_utilization >= self.MARGIN_WARNING_THRESHOLD:
            level = MarginSafetyLevel.WARNING
            message = (
                f"WARNING: Margin utilization will be {projected_utilization*100:.1f}% "
                f"(warning threshold: {self.MARGIN_WARNING_THRESHOLD*100:.0f}%). "
                f"Proceeding with caution."
            )
            should_proceed = True

            # Voice warning
            if self.voice:
                self.voice._speak(
                    f"Margin warning. Utilization at {projected_utilization*100:.0f} percent. Proceeding with order.",
                    priority="normal",
                    voice="Alex"
                )

            # Telegram warning
            if self.telegram:
                self.telegram.send_alert(
                    f"⚠️ MARGIN WARNING\n"
                    f"Utilization: {projected_utilization*100:.1f}%\n"
                    f"Proceeding with order..."
                )
        else:
            level = MarginSafetyLevel.SAFE
            message = f"Margin OK: {projected_utilization*100:.1f}%"
            should_proceed = True

        logger.info(f"[SAFETY] Margin check: {level.value} - {message}")
        return level, message, should_proceed

    # =========================================================================
    # Market Hours Validation
    # =========================================================================

    def is_market_open(self, instrument: str) -> Tuple[bool, str]:
        """
        Check if market is open for the instrument

        Checks:
        1. Holiday calendar (if configured)
        2. Market hours

        Args:
            instrument: Instrument name (GOLD_MINI, BANK_NIFTY)

        Returns:
            Tuple of (is_open, message)
        """
        from datetime import date

        # Determine exchange for instrument
        exchange = "MCX" if instrument == "GOLD_MINI" else "NSE"

        # ============================
        # HOLIDAY CHECK FIRST
        # ============================
        if self.holiday_calendar:
            is_holiday, holiday_reason = self.holiday_calendar.is_holiday(date.today(), exchange)
            if is_holiday:
                logger.info(f"[SAFETY] Market closed - {exchange} holiday: {holiday_reason}")
                return False, f"Market closed - {exchange} holiday: {holiday_reason}"

        # ============================
        # MARKET HOURS CHECK
        # ============================
        now = datetime.now().time()

        # Get market hours for instrument
        hours = self.MARKET_HOURS.get(instrument)
        if not hours:
            # Unknown instrument - allow by default
            return True, f"Unknown instrument {instrument}, allowing"

        start = hours['start']
        end = hours['end']

        # Handle overnight markets (MCX can trade till 23:30)
        if start <= end:
            # Normal case: start < end (e.g., 9:15 to 15:30)
            is_open = start <= now <= end
        else:
            # Overnight case: start > end (e.g., 18:00 to 02:00)
            is_open = now >= start or now <= end

        if is_open:
            return True, f"Market open for {instrument}"
        else:
            return False, f"Market closed for {instrument} (hours: {start}-{end}, current: {now})"

    # =========================================================================
    # Price Sanity Checks
    # =========================================================================

    def update_last_price(self, instrument: str, price: float):
        """Update last known price for an instrument"""
        with self._price_lock:
            self._last_prices[instrument] = price

    def check_price_sanity(self, instrument: str, signal_price: float) -> Tuple[bool, str]:
        """
        Check if signal price is within reasonable range of last known price

        Args:
            instrument: Instrument name
            signal_price: Price from the signal

        Returns:
            Tuple of (is_valid, message)
        """
        with self._price_lock:
            last_price = self._last_prices.get(instrument)

        if last_price is None:
            # No reference price - allow and record
            self.update_last_price(instrument, signal_price)
            return True, f"No reference price for {instrument}, recording {signal_price}"

        # Calculate deviation
        deviation = abs(signal_price - last_price) / last_price

        if deviation > self.PRICE_DEVIATION_THRESHOLD:
            message = (
                f"Price deviation {deviation*100:.2f}% exceeds threshold "
                f"({self.PRICE_DEVIATION_THRESHOLD*100:.0f}%). "
                f"Signal: {signal_price}, Last: {last_price}"
            )
            logger.warning(f"[SAFETY] {message}")

            # Alert
            if self.telegram:
                self.telegram.send_alert(
                    f"⚠️ PRICE DEVIATION\n"
                    f"Instrument: {instrument}\n"
                    f"Signal Price: {signal_price:,.2f}\n"
                    f"Last Price: {last_price:,.2f}\n"
                    f"Deviation: {deviation*100:.2f}%"
                )

            return False, message

        # Update last price
        self.update_last_price(instrument, signal_price)
        return True, f"Price OK: {signal_price} (deviation: {deviation*100:.2f}%)"

    # =========================================================================
    # Combined Pre-Order Safety Check
    # =========================================================================

    def pre_order_safety_check(
        self,
        instrument: str,
        signal_price: float,
        estimated_margin: float = 0,
        override: bool = False
    ) -> Tuple[bool, str]:
        """
        Comprehensive pre-order safety check

        Args:
            instrument: Instrument name
            signal_price: Price from signal
            estimated_margin: Estimated margin required for order
            override: If True, bypass critical margin check

        Returns:
            Tuple of (should_proceed, message)
        """
        messages = []

        # 1. Check if trading is paused
        paused, pause_reason = self.is_trading_paused()
        if paused:
            return False, f"Trading paused: {pause_reason}"

        # 2. Check market hours
        market_open, market_msg = self.is_market_open(instrument)
        if not market_open:
            messages.append(market_msg)
            logger.warning(f"[SAFETY] {market_msg}")
            # Don't block - TradingView might send slightly early/late signals
            # Just log and alert
            if self.telegram:
                self.telegram.send_alert(f"⚠️ Signal received outside market hours\n{market_msg}")

        # 3. Check price sanity
        price_ok, price_msg = self.check_price_sanity(instrument, signal_price)
        if not price_ok:
            return False, price_msg

        # 4. Check margin safety
        margin_level, margin_msg, margin_ok = self.check_margin_safety(estimated_margin)
        messages.append(margin_msg)

        if not margin_ok:
            if override:
                logger.warning(f"[SAFETY] Margin check OVERRIDDEN: {margin_msg}")
                messages.append("OVERRIDE APPLIED")
            else:
                return False, margin_msg

        return True, " | ".join(messages)

    def get_status(self) -> Dict:
        """Get current safety status"""
        paused, pause_reason = self.is_trading_paused()

        status = {
            'trading_paused': paused,
            'pause_reason': pause_reason,
            'margin_warning_threshold': self.MARGIN_WARNING_THRESHOLD * 100,
            'margin_critical_threshold': self.MARGIN_CRITICAL_THRESHOLD * 100,
            'price_deviation_threshold': self.PRICE_DEVIATION_THRESHOLD * 100,
            'last_prices': dict(self._last_prices)
        }

        if self.portfolio:
            state = self.portfolio.get_current_state()
            status['current_margin_utilization'] = state.margin_utilization_percent

        return status


# Global instance
_safety_manager: Optional[SafetyManager] = None


def init_safety_manager(
    portfolio_state_manager=None,
    voice_announcer=None,
    telegram_notifier=None,
    holiday_calendar=None
) -> SafetyManager:
    """Initialize global SafetyManager instance"""
    global _safety_manager
    _safety_manager = SafetyManager(
        portfolio_state_manager=portfolio_state_manager,
        voice_announcer=voice_announcer,
        telegram_notifier=telegram_notifier,
        holiday_calendar=holiday_calendar
    )
    return _safety_manager


def get_safety_manager() -> Optional[SafetyManager]:
    """Get global SafetyManager instance"""
    return _safety_manager
