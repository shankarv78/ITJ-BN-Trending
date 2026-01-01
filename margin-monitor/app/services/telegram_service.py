"""
Auto-Hedge System - Telegram Notification Service

Sends alerts for hedge actions to Telegram.
Provides real-time notifications for:
- Hedge buys/sells
- Order failures
- System status updates
"""

import logging
from typing import Optional
from datetime import datetime

import httpx
import pytz

from app.config import settings

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')


class TelegramService:
    """
    Telegram notification service for hedge alerts.

    Uses Telegram Bot API to send formatted messages.
    All messages are sent to a configured chat ID.
    """

    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None
    ):
        """
        Initialize Telegram service.

        Args:
            bot_token: Telegram bot token (uses settings if not provided)
            chat_id: Target chat ID (uses settings if not provided)
        """
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            logger.warning(
                "[TELEGRAM] Service disabled - missing bot_token or chat_id"
            )

    @property
    def base_url(self) -> str:
        """Get Telegram API base URL."""
        return f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False
    ) -> Optional[str]:
        """
        Send a message to the configured chat.

        Args:
            text: Message text (supports Markdown)
            parse_mode: 'Markdown' or 'HTML'
            disable_notification: True to send silently

        Returns:
            Message ID if successful, None otherwise
        """
        if not self.enabled:
            logger.debug(f"[TELEGRAM] (disabled) Would send: {text[:100]}...")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_notification": disable_notification
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                result = response.json()

                if result.get("ok"):
                    message_id = result.get("result", {}).get("message_id")
                    logger.debug(f"[TELEGRAM] Sent message {message_id}")
                    return str(message_id)
                else:
                    logger.error(f"[TELEGRAM] Send failed: {result}")
                    return None

        except Exception as e:
            logger.error(f"[TELEGRAM] Error sending message: {e}")
            return None

    def _now_ist(self) -> str:
        """Get current time in IST as formatted string."""
        return datetime.now(IST).strftime('%H:%M:%S')

    async def send_hedge_buy_alert(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        quantity: int,
        price: float,
        total_cost: float,
        trigger_reason: str,
        utilization_before: float,
        otm_distance: int
    ) -> Optional[str]:
        """
        Send alert for hedge buy.

        Args:
            symbol: Trading symbol
            strike: Strike price
            option_type: CE or PE
            quantity: Total quantity
            price: Order price
            total_cost: Total cost of hedge
            trigger_reason: Why hedge was triggered
            utilization_before: Utilization % before hedge
            otm_distance: OTM distance in points

        Returns:
            Message ID if successful
        """
        message = f"""🛡️ *HEDGE BOUGHT*

*Symbol:* `{symbol}`
*Strike:* {strike} {option_type}
*Quantity:* {quantity}
*Price:* ₹{price}
*Total Cost:* ₹{total_cost:,.0f}

*Trigger:* {trigger_reason}
*Utilization Before:* {utilization_before:.1f}%
*OTM Distance:* {otm_distance} points

*Time:* {self._now_ist()}"""

        return await self.send_message(message)

    async def send_hedge_sell_alert(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        quantity: int,
        entry_price: float,
        exit_price: float,
        pnl: float,
        trigger_reason: str,
        utilization_before: float
    ) -> Optional[str]:
        """
        Send alert for hedge sell/exit.

        Args:
            symbol: Trading symbol
            strike: Strike price
            option_type: CE or PE
            quantity: Total quantity
            entry_price: Original entry price
            exit_price: Exit price
            pnl: P&L on hedge
            trigger_reason: Why exit was triggered
            utilization_before: Utilization % before exit

        Returns:
            Message ID if successful
        """
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        message = f"""📤 *HEDGE EXITED*

*Symbol:* `{symbol}`
*Strike:* {strike} {option_type}
*Quantity:* {quantity}
*Entry:* ₹{entry_price} → *Exit:* ₹{exit_price}
*P&L:* {pnl_emoji} ₹{pnl:,.0f}

*Trigger:* {trigger_reason}
*Utilization Before:* {utilization_before:.1f}%

*Time:* {self._now_ist()}"""

        return await self.send_message(message)

    async def send_hedge_failure_alert(
        self,
        symbol: str,
        action: str,
        error: str,
        trigger_reason: str
    ) -> Optional[str]:
        """
        Send alert for failed hedge order.

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            error: Error message
            trigger_reason: Why hedge was triggered

        Returns:
            Message ID if successful
        """
        message = f"""❌ *HEDGE ORDER FAILED*

*Symbol:* `{symbol}`
*Action:* {action}
*Trigger:* {trigger_reason}
*Error:* {error}

*Time:* {self._now_ist()}

⚠️ Manual intervention may be required!"""

        return await self.send_message(message)

    async def send_entry_imminent_alert(
        self,
        portfolio_name: str,
        seconds_until: int,
        current_util: float,
        projected_util: float,
        hedge_required: bool
    ) -> Optional[str]:
        """
        Send alert for imminent strategy entry.

        Args:
            portfolio_name: Name of the portfolio
            seconds_until: Seconds until entry
            current_util: Current utilization %
            projected_util: Projected utilization after entry %
            hedge_required: Whether hedge is required

        Returns:
            Message ID if successful
        """
        hedge_status = "⚠️ *Required*" if hedge_required else "✓ Not required"

        message = f"""ℹ️ *Entry in {seconds_until}s*

*Portfolio:* {portfolio_name}
*Current:* {current_util:.1f}%
*Projected:* {projected_util:.1f}%
*Hedge:* {hedge_status}

*Time:* {self._now_ist()}"""

        return await self.send_message(message, disable_notification=not hedge_required)

    async def send_system_status(
        self,
        status: str,
        index_name: str = None,
        num_baskets: int = None,
        total_budget: float = None,
        extra_info: str = None
    ) -> Optional[str]:
        """
        Send system status update.

        Args:
            status: Status message (e.g., "Started", "Stopped")
            index_name: Trading index
            num_baskets: Number of baskets
            total_budget: Total budget
            extra_info: Additional information

        Returns:
            Message ID if successful
        """
        emoji = "🚀" if "start" in status.lower() else "🛑" if "stop" in status.lower() else "ℹ️"

        lines = [f"{emoji} *Auto-Hedge {status}*", ""]

        if index_name:
            lines.append(f"*Index:* {index_name}")
        if num_baskets:
            lines.append(f"*Baskets:* {num_baskets}")
        if total_budget:
            lines.append(f"*Budget:* ₹{total_budget:,.0f}")
        if extra_info:
            lines.append("")
            lines.append(extra_info)

        lines.append("")
        lines.append(f"*Time:* {self._now_ist()}")

        return await self.send_message("\n".join(lines))

    async def send_daily_summary(
        self,
        date_str: str,
        hedges_bought: int,
        total_cost: float,
        total_recovered: float,
        net_cost: float,
        peak_utilization: float,
        strategies_executed: int
    ) -> Optional[str]:
        """
        Send end-of-day summary.

        Args:
            date_str: Date string
            hedges_bought: Number of hedges bought
            total_cost: Total cost of hedges
            total_recovered: Amount recovered from exits
            net_cost: Net hedge cost
            peak_utilization: Peak utilization %
            strategies_executed: Number of strategies executed

        Returns:
            Message ID if successful
        """
        message = f"""📊 *Auto-Hedge Daily Summary*

*Date:* {date_str}

*Hedges:* {hedges_bought} bought
*Total Cost:* ₹{total_cost:,.0f}
*Recovered:* ₹{total_recovered:,.0f}
*Net Cost:* ₹{net_cost:,.0f}

*Peak Utilization:* {peak_utilization:.1f}%
*Strategies Executed:* {strategies_executed}

*Time:* {self._now_ist()}"""

        return await self.send_message(message)


# Global service instance
telegram_service = TelegramService()
