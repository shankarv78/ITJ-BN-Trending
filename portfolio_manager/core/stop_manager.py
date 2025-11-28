"""
Tom Basso ATR Trailing Stop Manager

Each position has independent trailing stop:
- Initial Stop = Entry - (Initial_ATR_Mult × ATR)
- Trailing Stop = Highest_Close - (Trailing_ATR_Mult × ATR)
- Current Stop = MAX(Initial_Stop, Trailing_Stop) - only ratchets UP
"""
import logging
from typing import Dict, List
from core.models import Position, InstrumentType
from core.config import get_instrument_config

logger = logging.getLogger(__name__)

class TomBassoStopManager:
    """Manages independent ATR trailing stops for each position"""
    
    def __init__(self):
        """Initialize stop manager"""
        pass
    
    def calculate_initial_stop(
        self,
        entry_price: float,
        atr: float,
        instrument: InstrumentType
    ) -> float:
        """
        Calculate initial stop loss at entry
        
        Args:
            entry_price: Entry price
            atr: Current ATR value
            instrument: Instrument type
            
        Returns:
            Initial stop price
        """
        config = get_instrument_config(instrument)
        initial_stop = entry_price - (config.initial_atr_mult * atr)
        
        logger.debug(f"Initial stop: {entry_price} - ({config.initial_atr_mult} × {atr}) = {initial_stop}")
        
        return initial_stop
    
    def update_trailing_stop(
        self,
        position: Position,
        current_price: float,
        current_atr: float
    ) -> float:
        """
        Update trailing stop for position
        
        Args:
            position: Position to update
            current_price: Current market price
            current_atr: Current ATR value
            
        Returns:
            New stop price (only moves up)
        """
        # Get instrument config
        if position.instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif position.instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        else:
            logger.error(f"Unknown instrument: {position.instrument}")
            return position.current_stop
        
        config = get_instrument_config(inst_type)
        
        # Update highest close
        new_highest = max(position.highest_close, current_price)
        position.highest_close = new_highest
        
        # Calculate trailing stop
        trailing_stop = new_highest - (config.trailing_atr_mult * current_atr)
        
        # Only move stop UP (ratchet effect)
        new_stop = max(position.current_stop, trailing_stop)
        
        if new_stop > position.current_stop:
            logger.debug(f"{position.position_id} stop moved: {position.current_stop:.2f} → {new_stop:.2f}")
            position.current_stop = new_stop
        
        return new_stop
    
    def check_stop_hit(
        self,
        position: Position,
        current_price: float
    ) -> bool:
        """
        Check if position stop has been hit
        
        Args:
            position: Position to check
            current_price: Current market price
            
        Returns:
            True if stop hit, False otherwise
        """
        stop_hit = current_price < position.current_stop
        
        if stop_hit:
            logger.info(f"{position.position_id} STOP HIT: Price={current_price}, Stop={position.current_stop}")
        
        return stop_hit
    
    def update_all_stops(
        self,
        positions: Dict[str, Position],
        prices: Dict[str, float],
        atrs: Dict[str, float]
    ) -> List[str]:
        """
        Update stops for all positions and return list of stop hits
        
        Args:
            positions: Dict of all positions
            prices: Current prices per instrument
            atrs: Current ATR values per instrument
            
        Returns:
            List of position IDs with stops hit
        """
        stops_hit = []
        
        for pos_id, pos in positions.items():
            if pos.status != "open":
                continue
            
            instrument = pos.instrument
            current_price = prices.get(instrument)
            current_atr = atrs.get(instrument)
            
            if current_price is None or current_atr is None:
                logger.warning(f"Missing price/ATR for {instrument}, skipping stop update")
                continue
            
            # Update trailing stop
            self.update_trailing_stop(pos, current_price, current_atr)
            
            # Check if stop hit
            if self.check_stop_hit(pos, current_price):
                stops_hit.append(pos_id)
        
        if stops_hit:
            logger.info(f"Stops hit: {stops_hit}")
        
        return stops_hit

