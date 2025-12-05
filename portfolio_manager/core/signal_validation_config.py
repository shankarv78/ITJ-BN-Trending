"""
Signal Validation Configuration

Extracted from signal_validator.py to avoid circular import with core.config
"""
from dataclasses import dataclass


@dataclass
class SignalValidationConfig:
    """Configuration for signal validation logic"""
    
    # === Divergence Thresholds ===
    max_divergence_base_entry: float = 0.02  # 2%
    """Maximum acceptable price divergence for BASE_ENTRY signals"""
    
    max_divergence_pyramid: float = 0.01  # 1%
    """Maximum acceptable price divergence for PYRAMID signals (stricter!)"""
    
    max_divergence_exit: float = 0.01  # 1%
    """Maximum acceptable unfavorable divergence for EXIT signals"""
    
    divergence_warning_threshold: float = 0.005  # 0.5%
    """Log warning if divergence exceeds this (but still accept)"""
    
    # === Risk Thresholds ===
    max_risk_increase_pyramid: float = 0.20  # 20%
    """Maximum acceptable risk increase for pyramids"""
    
    max_risk_increase_base: float = 0.50  # 50%
    """Maximum acceptable risk increase for base entries"""
    
    # === Signal Age Thresholds ===
    max_signal_age_normal: int = 10  # seconds
    """Normal signal age - no warnings"""
    
    max_signal_age_warning: int = 30  # seconds
    """Signal age triggers warning"""
    
    max_signal_age_elevated: int = 60  # seconds
    """Signal age requires stricter divergence check"""
    
    max_signal_age_stale: int = 60  # seconds
    """Signal considered stale - reject if divergence also high"""
    
    # === Execution Strategy ===
    default_execution_strategy: str = "progressive"
    """Options: 'simple_limit', 'progressive'"""
    
    # === Edge Case Handling ===
    accept_valid_signal_despite_pullback: bool = True
    """Accept signals that were valid at generation even if market pulled back"""
    
    reject_chase_for_pyramids: bool = True
    """Reject pyramids if market surged ahead significantly"""
    
    # === Position Size Adjustment ===
    adjust_size_on_risk_increase: bool = True
    """Automatically reduce position size when risk increases"""
    
    min_lots_after_adjustment: int = 1
    """Minimum lots after size adjustment (never reduce to 0)"""

