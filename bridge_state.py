"""
Position state management with persistence
"""
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class StateManager:
    """Manages position state with disk persistence"""
    
    def __init__(self, state_file='position_state.json', duplicate_window=60):
        self.state_file = state_file
        self.duplicate_window = duplicate_window
        self.positions: Dict = {}
        self.recent_signals: List[Dict] = []
        self.load_state()
    
    def load_state(self):
        """Load state from disk"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.positions = data.get('positions', {})
                    self.recent_signals = data.get('recent_signals', [])
                logger.info(f"State loaded: {len(self.positions)} positions")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
                self.positions = {}
                self.recent_signals = []
        else:
            logger.info("No existing state file, starting fresh")
    
    def save_state(self):
        """Persist state to disk"""
        try:
            data = {
                'positions': self.positions,
                'recent_signals': self.recent_signals[-100:],  # Keep last 100
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def add_position(self, position_id: str, position_data: Dict):
        """Add or update a position"""
        self.positions[position_id] = position_data
        self.save_state()
        logger.info(f"Position added/updated: {position_id}")
    
    def remove_position(self, position_id: str):
        """Remove a position"""
        if position_id in self.positions:
            del self.positions[position_id]
            self.save_state()
            logger.info(f"Position removed: {position_id}")
        else:
            logger.warning(f"Attempted to remove non-existent position: {position_id}")
    
    def get_position(self, position_id: str) -> Optional[Dict]:
        """Get position by ID"""
        return self.positions.get(position_id)
    
    def get_all_positions(self) -> Dict:
        """Get all open positions"""
        return {k: v for k, v in self.positions.items() if v.get('status') == 'open'}
    
    def get_position_count(self) -> int:
        """Count open positions"""
        return len(self.get_all_positions())
    
    def is_duplicate_signal(self, signal: Dict) -> bool:
        """
        Check if signal is a duplicate within time window
        
        Args:
            signal: Signal dictionary with type, position, timestamp
            
        Returns:
            True if duplicate, False otherwise
        """
        # Create hash from signal key fields
        signal_hash = hashlib.md5(
            f"{signal.get('type')}_{signal.get('position')}_{signal.get('timestamp')}".encode()
        ).hexdigest()
        
        # Clean old signals beyond window
        cutoff_time = datetime.now() - timedelta(seconds=self.duplicate_window)
        self.recent_signals = [
            s for s in self.recent_signals 
            if datetime.fromisoformat(s['received_at']) > cutoff_time
        ]
        
        # Check for duplicate
        for recent in self.recent_signals:
            if recent['hash'] == signal_hash:
                logger.warning(f"Duplicate signal detected: {signal.get('type')} {signal.get('position')}")
                return True
        
        # Add to recent signals
        self.recent_signals.append({
            'hash': signal_hash,
            'received_at': datetime.now().isoformat(),
            'type': signal.get('type'),
            'position': signal.get('position')
        })
        self.save_state()
        
        return False
    
    def update_position_field(self, position_id: str, field: str, value):
        """Update a single field in position"""
        if position_id in self.positions:
            self.positions[position_id][field] = value
            self.save_state()
        else:
            logger.error(f"Cannot update field for non-existent position: {position_id}")


