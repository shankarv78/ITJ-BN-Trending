"""
Portfolio Manager Telegram Bot

Provides query interface for signal audit trail and system status.

Commands:
- /start, /help - Help message
- /status - System status and health
- /signals [N] [instrument] - Recent signals
- /orders [N] - Recent orders
- /stats [days] - Signal statistics
- /sizing <signal_id> - Position sizing breakdown
- /positions - Current open positions
"""

import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

# PM API endpoint
PM_API_URL = "http://127.0.0.1:5002"
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

logger = logging.getLogger(__name__)


class PortfolioManagerBot:
    """
    Telegram bot for Portfolio Manager.

    Query-only bot for viewing signal audit trail, orders, and statistics.
    """

    def __init__(
        self,
        token: str,
        audit_service,
        order_logger,
        portfolio_manager=None,
        allowed_user_ids: List[int] = None
    ):
        """
        Initialize Telegram bot.

        Args:
            token: Telegram bot token from BotFather
            audit_service: SignalAuditService instance
            order_logger: OrderExecutionLogger instance
            portfolio_manager: Optional PortfolioStateManager for positions
            allowed_user_ids: List of allowed Telegram user IDs (None = allow all)
        """
        self.token = token
        self.audit_service = audit_service
        self.order_logger = order_logger
        self.portfolio_manager = portfolio_manager
        # Note: None means allow all, empty set means deny all
        self.allowed_user_ids = set(allowed_user_ids) if allowed_user_ids is not None else None

        self.application: Optional[Application] = None
        self._running = False

        # Dual-channel confirmation manager (optional)
        self.confirmation_manager = None

        logger.info("[TelegramBot] Bot initialized")

    def set_confirmation_manager(self, manager):
        """
        Set the dual-channel confirmation manager.

        This enables the bot to handle inline keyboard callbacks
        for confirmation dialogs.

        Args:
            manager: DualChannelConfirmationManager instance
        """
        self.confirmation_manager = manager
        logger.info("[TelegramBot] Confirmation manager set")

    async def _check_authorized(self, update: Update) -> bool:
        """
        Check if user is authorized to use the bot.

        Authorization logic:
        - allowed_user_ids=None: Allow all users (open access)
        - allowed_user_ids=[]: Deny all users (no access)
        - allowed_user_ids=[123, 456]: Only allow specified user IDs

        Args:
            update: Telegram update

        Returns:
            True if authorized
        """
        # None means no restriction - allow all
        if self.allowed_user_ids is None:
            return True

        user_id = update.effective_user.id if update.effective_user else None

        # Empty set or user not in set - deny access
        if not self.allowed_user_ids or user_id not in self.allowed_user_ids:
            logger.warning(f"[TelegramBot] Unauthorized access attempt: user_id={user_id}")
            await update.message.reply_text("Unauthorized. Contact admin to get access.")
            return False

        return True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start and /help commands."""
        if not await self._check_authorized(update):
            return

        help_text = """Portfolio Manager Bot

Query signals, orders, and system status.

Commands:
/status - System status
/signals - Recent signals
/signals 5 BANK_NIFTY - Filter by count/instrument
/signal 39 - Full details for signal #39 (rejection reason, sizing, etc.)
/sizing 25 - Position sizing breakdown
/orders - Recent orders
/stats 7 - Signal statistics (default 30 days)
/positions - Open positions
"""
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - system status."""
        if not await self._check_authorized(update):
            return

        try:
            # Get audit trail stats
            stats = self.audit_service.get_signal_stats(days=1)

            # Get system info
            status_lines = [
                "**System Status**",
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "**Today's Signals:**",
                f"  Total: {stats.get('total_signals', 0)}",
                f"  Processed: {stats.get('processed', 0)}",
                f"  Rejected: {stats.get('rejected', 0)}",
                ""
            ]

            # Add position info if available
            if self.portfolio_manager:
                try:
                    state = self.portfolio_manager.get_current_state()
                    open_positions = len([p for p in state.positions.values() if p.status == 'open'])
                    status_lines.extend([
                        "**Portfolio:**",
                        f"  Equity: Rs {state.equity:,.0f}",
                        f"  Open Positions: {open_positions}",
                        ""
                    ])
                except Exception as e:
                    logger.debug(f"Could not get portfolio state: {e}")

            status_lines.append("Bot Status: Online")

            await update.message.reply_text('\n'.join(status_lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in status command: {e}")
            await update.message.reply_text(f"Error getting status: {e}")

    async def signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command - recent signals from audit trail."""
        if not await self._check_authorized(update):
            return

        try:
            # Parse arguments
            limit = 10
            instrument = None

            if context.args:
                # First arg could be limit or instrument
                if context.args[0].isdigit():
                    limit = min(int(context.args[0]), 50)  # Max 50
                    if len(context.args) > 1:
                        instrument = context.args[1].upper()
                else:
                    instrument = context.args[0].upper()

            # Query signal_audit table
            if not self.audit_service:
                await update.message.reply_text("Audit service not connected. Use /signalsold for historic signals.")
                return

            signals = self.audit_service.get_recent_signals(
                limit=limit,
                instrument=instrument
            )

            if not signals:
                await update.message.reply_text("No audit records yet. Use /signalsold for historic signals.")
                return

            # Format output
            lines = [f"**Signal Audit Trail** (last {len(signals)})\n"]

            for sig in signals:
                outcome_emoji = self._get_outcome_emoji(sig.get('outcome', ''))

                line = (
                    f"{outcome_emoji} #{sig.get('id', '?')} "
                    f"{sig.get('instrument', '?')} {sig.get('signal_type', '?')} "
                    f"- {sig.get('outcome', '?')}"
                )
                if sig.get('outcome_reason'):
                    line += f"\n   _{sig.get('outcome_reason')[:50]}_"

                lines.append(line)

            await update.message.reply_text('\n'.join(lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in signals command: {e}")
            await update.message.reply_text(f"Error getting signals: {e}")

    async def signalsold_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signalsold command - historic signals from PM's signal_log."""
        if not await self._check_authorized(update):
            return

        try:
            # Parse arguments
            limit = 10
            instrument = None

            if context.args:
                if context.args[0].isdigit():
                    limit = min(int(context.args[0]), 50)
                    if len(context.args) > 1:
                        instrument = context.args[1].upper()
                else:
                    instrument = context.args[0].upper()

            # Query PM API for signals
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {"limit": limit}
                if instrument:
                    params["instrument"] = instrument
                response = await client.get(f"{PM_API_URL}/signals", params=params)

                if response.status_code != 200:
                    await update.message.reply_text(f"PM API error: {response.status_code}")
                    return

                data = response.json()
                signals = data.get("signals", [])

            if not signals:
                await update.message.reply_text("No signals found.")
                return

            # Format output
            lines = [f"**Historic Signals** (last {len(signals)})\n"]

            for sig in signals:
                status = sig.get('status', 'unknown')
                status_emoji = {"executed": "✅", "rejected": "❌", "blocked": "🚫", "error": "⚠️"}.get(status, "❓")

                line = (
                    f"{status_emoji} #{sig.get('id', '?')} "
                    f"{sig.get('instrument', '?')} {sig.get('signal_type', '?')} "
                    f"- {status}"
                )
                lines.append(line)

            await update.message.reply_text('\n'.join(lines))

        except httpx.ConnectError:
            await update.message.reply_text("Cannot connect to PM. Is it running?")
        except Exception as e:
            logger.error(f"[TelegramBot] Error in signalsold command: {e}")
            await update.message.reply_text(f"Error getting signals: {e}")

    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command - recent orders."""
        if not await self._check_authorized(update):
            return

        try:
            # Parse limit argument
            limit = 10
            if context.args and context.args[0].isdigit():
                limit = min(int(context.args[0]), 50)

            # Get recent orders
            orders = self.order_logger.get_recent_orders(limit=limit)

            if not orders:
                await update.message.reply_text("No orders found.")
                return

            # Format output
            lines = [f"**Recent Orders** (last {len(orders)})\n"]

            for order in orders:
                status_emoji = self._get_order_status_emoji(order.get('order_status', ''))
                placed_at = order.get('order_placed_at', '')
                if isinstance(placed_at, datetime):
                    placed_at = placed_at.strftime('%m-%d %H:%M')

                # Format price info
                fill_info = ""
                if order.get('fill_price'):
                    fill_info = f"@ Rs {order['fill_price']:,.2f}"
                    if order.get('slippage_pct'):
                        slip = order['slippage_pct'] * 100
                        fill_info += f" ({slip:+.2f}%)"

                line = (
                    f"{status_emoji} {order.get('instrument', '?')} "
                    f"{order.get('action', '?')} {order.get('lots', '?')}L "
                    f"{fill_info}"
                )
                lines.append(line)

            await update.message.reply_text('\n'.join(lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in orders command: {e}")
            await update.message.reply_text(f"Error getting orders: {e}")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command - signal statistics."""
        if not await self._check_authorized(update):
            return

        try:
            # Parse days argument
            days = 30
            if context.args and context.args[0].isdigit():
                days = min(int(context.args[0]), 90)  # Max 90 days

            # Get stats
            stats = self.audit_service.get_signal_stats(days=days)

            # Format output
            lines = [
                f"**Signal Statistics** (last {days} days)\n",
                f"Total Signals: {stats.get('total_signals', 0)}",
                "",
                "**By Outcome:**"
            ]

            # Outcome breakdown
            by_outcome = stats.get('by_outcome', {})
            for outcome, count in sorted(by_outcome.items(), key=lambda x: -x[1]):
                emoji = self._get_outcome_emoji(outcome)
                lines.append(f"  {emoji} {outcome}: {count}")

            lines.append("")
            lines.append("**By Instrument:**")

            # Instrument breakdown
            by_instrument = stats.get('by_instrument', {})
            for instrument, count in sorted(by_instrument.items(), key=lambda x: -x[1]):
                lines.append(f"  {instrument}: {count}")

            # Add slippage stats if available
            slippage_stats = self.order_logger.get_slippage_stats(days=days)
            if slippage_stats.get('statistics'):
                lines.append("")
                lines.append("**Slippage (completed orders):**")
                for stat in slippage_stats['statistics']:
                    avg_slip = stat.get('avg_slippage_pct', 0) or 0
                    lines.append(
                        f"  {stat.get('instrument', '?')}: "
                        f"avg {avg_slip*100:.3f}% ({stat.get('order_count', 0)} orders)"
                    )

            await update.message.reply_text('\n'.join(lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in stats command: {e}")
            await update.message.reply_text(f"Error getting stats: {e}")

    async def sizing_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sizing command - position sizing breakdown."""
        if not await self._check_authorized(update):
            return

        try:
            if not context.args or not context.args[0].isdigit():
                await update.message.reply_text(
                    "Usage: /sizing <signal_id>\nExample: /sizing 123"
                )
                return

            signal_id = int(context.args[0])

            # Get signal audit record
            signal = self.audit_service.get_audit_by_id(signal_id)

            if not signal:
                await update.message.reply_text(f"Signal #{signal_id} not found.")
                return

            lines = [f"**Signal #{signal_id} Details**\n"]

            # Basic info
            lines.extend([
                f"Instrument: {signal.get('instrument', '?')}",
                f"Type: {signal.get('signal_type', '?')}",
                f"Outcome: {signal.get('outcome', '?')}",
                f"Time: {signal.get('signal_timestamp', '?')}",
                ""
            ])

            # Sizing calculation
            sizing = signal.get('sizing_calculation')
            if sizing:
                lines.append("**Position Sizing:**")
                if isinstance(sizing, dict):
                    inputs = sizing.get('inputs', {})
                    calc = sizing.get('calculation', {})

                    if inputs:
                        lines.append(f"  Method: {sizing.get('method', 'TOM_BASSO')}")
                        lines.append(f"  Equity: Rs {inputs.get('equity_high', 0):,.0f}")
                        lines.append(f"  Risk %: {inputs.get('risk_percent', 0)}%")
                        lines.append(f"  Stop Distance: {inputs.get('stop_distance', 0):.2f}")

                    if calc:
                        lines.append("")
                        lines.append("**Calculation:**")
                        lines.append(f"  Risk Amount: Rs {calc.get('risk_amount', 0):,.0f}")
                        lines.append(f"  Raw Lots: {calc.get('raw_lots', 0):.2f}")
                        lines.append(f"  Final Lots: {calc.get('final_lots', 0)}")

                    limiter = sizing.get('limiter', 'unknown')
                    lines.append(f"  Limiter: {limiter}")
            else:
                lines.append("_No sizing data available_")

            # Order execution
            lines.append("")
            order_exec = signal.get('order_execution')
            if order_exec:
                lines.append("**Execution:**")
                if isinstance(order_exec, dict):
                    lines.append(f"  Status: {order_exec.get('execution_status', '?')}")
                    if order_exec.get('fill_price'):
                        lines.append(f"  Fill: Rs {order_exec['fill_price']:,.2f}")
                    if order_exec.get('slippage_pct'):
                        lines.append(f"  Slippage: {order_exec['slippage_pct']*100:.3f}%")
            else:
                lines.append("_No execution data available_")

            await update.message.reply_text('\n'.join(lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in sizing command: {e}")
            await update.message.reply_text(f"Error getting sizing details: {e}")

    async def signal_detail_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signal <id> command - full signal details including rejection reason."""
        if not await self._check_authorized(update):
            return

        try:
            if not context.args or not context.args[0].isdigit():
                await update.message.reply_text(
                    "Usage: /signal <id>\nExample: /signal 39"
                )
                return

            signal_id = int(context.args[0])

            # Get signal audit record
            signal = self.audit_service.get_audit_by_id(signal_id)

            if not signal:
                await update.message.reply_text(f"Signal #{signal_id} not found.")
                return

            outcome = signal.get('outcome', '?')
            emoji = self._get_outcome_emoji(outcome)

            lines = [
                f"{emoji} Signal #{signal_id}",
                "",
                f"Instrument: {signal.get('instrument', '?')}",
                f"Type: {signal.get('signal_type', '?')}",
                f"Position: {signal.get('position', '?')}",
                f"Time: {signal.get('signal_timestamp', '?')}",
                "",
                f"Outcome: {outcome}",
            ]

            # Show rejection reason
            outcome_reason = signal.get('outcome_reason')
            if outcome_reason:
                lines.append(f"Reason: {outcome_reason}")

            # Validation details (especially for rejections)
            validation = signal.get('validation_result')
            if validation and isinstance(validation, dict):
                lines.append("")
                lines.append("--- Validation Details ---")

                if validation.get('is_valid') is not None:
                    lines.append(f"Valid: {validation.get('is_valid')}")
                if validation.get('severity'):
                    lines.append(f"Severity: {validation.get('severity')}")
                if validation.get('signal_age_seconds'):
                    lines.append(f"Signal Age: {validation.get('signal_age_seconds'):.2f}s")
                if validation.get('divergence_pct'):
                    lines.append(f"Divergence: {validation.get('divergence_pct')*100:.2f}%")
                if validation.get('risk_increase_pct'):
                    lines.append(f"Risk Increase: {validation.get('risk_increase_pct')*100:.2f}%")
                if validation.get('direction'):
                    lines.append(f"Direction: {validation.get('direction')}")
                if validation.get('reason'):
                    lines.append(f"Validation Reason: {validation.get('reason')}")

            # Sizing details (for processed signals)
            sizing = signal.get('sizing_calculation')
            if sizing and isinstance(sizing, dict):
                lines.append("")
                lines.append("--- Position Sizing ---")

                inputs = sizing.get('inputs', {})
                calc = sizing.get('calculation', {})

                if inputs.get('equity_high'):
                    lines.append(f"Equity: Rs {inputs.get('equity_high'):,.0f}")
                if inputs.get('risk_percent'):
                    lines.append(f"Risk %: {inputs.get('risk_percent')}%")
                if inputs.get('stop_distance'):
                    lines.append(f"Stop Distance: {inputs.get('stop_distance'):.2f}")
                if calc.get('final_lots'):
                    lines.append(f"Final Lots: {calc.get('final_lots')}")
                if sizing.get('limiter'):
                    lines.append(f"Limiter: {sizing.get('limiter')}")

            # Order execution details
            order_exec = signal.get('order_execution')
            if order_exec and isinstance(order_exec, dict):
                lines.append("")
                lines.append("--- Execution ---")
                lines.append(f"Status: {order_exec.get('execution_status', '?')}")
                if order_exec.get('fill_price'):
                    lines.append(f"Fill Price: Rs {order_exec['fill_price']:,.2f}")
                if order_exec.get('slippage_pct'):
                    lines.append(f"Slippage: {order_exec['slippage_pct']*100:.3f}%")

            # Processing duration
            if signal.get('processing_duration_ms'):
                lines.append("")
                lines.append(f"Processing Time: {signal.get('processing_duration_ms')}ms")

            await update.message.reply_text('\n'.join(lines))

        except Exception as e:
            logger.error(f"[TelegramBot] Error in signal detail command: {e}")
            await update.message.reply_text(f"Error getting signal details: {e}")

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - current open positions."""
        if not await self._check_authorized(update):
            return

        try:
            # Query PM API for positions
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{PM_API_URL}/positions", params={"status": "open"})

                if response.status_code != 200:
                    await update.message.reply_text(f"PM API error: {response.status_code}")
                    return

                data = response.json()
                positions_dict = data.get("positions", {})
                positions = list(positions_dict.values()) if isinstance(positions_dict, dict) else positions_dict

            if not positions:
                await update.message.reply_text("No open positions.")
                return

            lines = [f"**Open Positions** ({len(positions)})\n"]

            for pos in positions:
                # Calculate unrealized P&L if possible
                pnl_str = ""
                unrealized_pnl = pos.get('unrealized_pnl')
                if unrealized_pnl is not None:
                    pnl_emoji = "📈" if unrealized_pnl >= 0 else "📉"
                    pnl_str = f" ({pnl_emoji} Rs {abs(unrealized_pnl):,.0f})"

                instrument = pos.get('instrument', 'Unknown')
                lots = pos.get('lots', 0)
                entry_price = pos.get('entry_price', 0)
                current_stop = pos.get('current_stop', 0)

                line = (
                    f"**{instrument}**\n"
                    f"  Lots: {lots} @ Rs {entry_price:,.2f}{pnl_str}\n"
                    f"  Stop: Rs {current_stop:,.2f}"
                )
                lines.append(line)

            await update.message.reply_text('\n'.join(lines))

        except httpx.ConnectError:
            await update.message.reply_text("Cannot connect to PM. Is it running?")
        except Exception as e:
            logger.error(f"[TelegramBot] Error in positions command: {e}")
            await update.message.reply_text(f"Error getting positions: {e}")

    def _get_outcome_emoji(self, outcome: str) -> str:
        """Get emoji for signal outcome."""
        emoji_map = {
            'PROCESSED': '',
            'REJECTED_VALIDATION': '',
            'REJECTED_RISK': '',
            'REJECTED_DUPLICATE': '',
            'REJECTED_MARKET': '',
            'REJECTED_MANUAL': '',
            'FAILED_ORDER': '',
            'PARTIAL_FILL': ''
        }
        return emoji_map.get(outcome, '')

    def _get_order_status_emoji(self, status: str) -> str:
        """Get emoji for order status."""
        emoji_map = {
            'COMPLETE': '',
            'PENDING': '',
            'OPEN': '',
            'PARTIAL': '',
            'REJECTED': '',
            'CANCELLED': '',
            'FAILED': ''
        }
        return emoji_map.get(status, '')

    def setup_handlers(self):
        """Set up command handlers."""
        if not self.application:
            return

        # Command handlers
        self.application.add_handler(CommandHandler(['start', 'help'], self.start_command))
        self.application.add_handler(CommandHandler('status', self.status_command))
        self.application.add_handler(CommandHandler('signals', self.signals_command))
        self.application.add_handler(CommandHandler('signalsold', self.signalsold_command))
        self.application.add_handler(CommandHandler('orders', self.orders_command))
        self.application.add_handler(CommandHandler('stats', self.stats_command))
        self.application.add_handler(CommandHandler('sizing', self.sizing_command))
        self.application.add_handler(CommandHandler('signal', self.signal_detail_command))
        self.application.add_handler(CommandHandler('positions', self.positions_command))

        # Callback handler for inline keyboard confirmations
        self.application.add_handler(
            CallbackQueryHandler(
                self._handle_confirmation_callback,
                pattern="^confirm:"
            )
        )

        logger.info("[TelegramBot] Command handlers registered")

    async def _handle_confirmation_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Handle callback queries from confirmation inline keyboards.

        Routes callbacks to the confirmation manager if available.
        """
        if not update.callback_query:
            return

        callback_query = update.callback_query

        # Check authorization
        user_id = callback_query.from_user.id if callback_query.from_user else None
        if self.allowed_user_ids is not None:
            if not self.allowed_user_ids or user_id not in self.allowed_user_ids:
                logger.warning(f"[TelegramBot] Unauthorized callback from user_id={user_id}")
                await callback_query.answer("Unauthorized")
                return

        # Route to confirmation manager
        if self.confirmation_manager:
            try:
                handled = await self.confirmation_manager.handle_telegram_callback(
                    callback_query
                )
                if handled:
                    return
            except Exception as e:
                logger.error(f"[TelegramBot] Error handling confirmation callback: {e}")
                await callback_query.answer("Error processing confirmation")
                return

        # No confirmation manager or callback not recognized
        await callback_query.answer("Unknown callback")

    async def start(self):
        """Start the bot."""
        if self._running:
            logger.warning("[TelegramBot] Bot already running")
            return

        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        self._running = True
        logger.info("[TelegramBot] Bot started and polling")

    async def stop(self):
        """Stop the bot."""
        if not self._running:
            return

        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        self._running = False
        logger.info("[TelegramBot] Bot stopped")

    def run_polling(self):
        """
        Run bot with polling (blocking).

        Use this for standalone bot execution.
        """
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()

        logger.info("[TelegramBot] Starting polling...")
        self.application.run_polling()
