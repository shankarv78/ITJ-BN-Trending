"""
Configuration Loader Utility

Loads configuration from JSON files with environment variable overrides.
Supports both database and Redis configurations.
"""
import json
import os
import logging
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config_file(config_path: str, env: str = 'local') -> Optional[Dict[str, Any]]:
    """
    Load configuration from JSON file for a specific environment
    
    Args:
        config_path: Path to the configuration JSON file
        env: Environment name ('local' or 'production')
        
    Returns:
        Configuration dictionary for the specified environment, or None if not found
    """
    try:
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}")
            return None
            
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Get environment-specific config
        env_config = config.get(env, config.get('local', {}))
        
        if not env_config:
            logger.warning(f"No configuration found for environment '{env}' in {config_path}")
            return None
            
        return env_config
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file {config_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading config file {config_path}: {e}")
        return None


def apply_env_overrides(config: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """
    Apply environment variable overrides to configuration
    
    Environment variables take precedence over file values.
    Format: {PREFIX}_{KEY} (e.g., REDIS_HOST, REDIS_PORT)
    
    Args:
        config: Configuration dictionary to override
        prefix: Prefix for environment variables (e.g., 'REDIS', 'DB')
        
    Returns:
        Configuration dictionary with environment variable overrides applied
    """
    if not config:
        return {}
    
    # Create a copy to avoid modifying the original
    overridden_config = config.copy()
    
    # Map of config keys to environment variable names
    env_var_mapping = {
        'host': f'{prefix}_HOST',
        'port': f'{prefix}_PORT',
        'database': f'{prefix}_DATABASE',
        'db': f'{prefix}_DB',
        'user': f'{prefix}_USER',
        'password': f'{prefix}_PASSWORD',
        'ssl': f'{prefix}_SSL',
        'socket_timeout': f'{prefix}_SOCKET_TIMEOUT',
        'enable_redis': f'{prefix}_ENABLE',
        'minconn': f'{prefix}_MINCONN',
        'maxconn': f'{prefix}_MAXCONN',
    }
    
    for key, env_var in env_var_mapping.items():
        if key in overridden_config and env_var in os.environ:
            env_value = os.environ[env_var]
            
            # Type conversion based on original value type
            original_value = overridden_config[key]
            
            if isinstance(original_value, bool):
                # Boolean: accept 'true', 'false', '1', '0'
                overridden_config[key] = env_value.lower() in ('true', '1', 'yes')
            elif isinstance(original_value, int):
                # Integer
                try:
                    overridden_config[key] = int(env_value)
                except ValueError:
                    logger.warning(f"Invalid integer value for {env_var}: {env_value}")
            elif isinstance(original_value, float):
                # Float
                try:
                    overridden_config[key] = float(env_value)
                except ValueError:
                    logger.warning(f"Invalid float value for {env_var}: {env_value}")
            else:
                # String or None
                if env_value.lower() == 'null' or env_value == '':
                    overridden_config[key] = None
                else:
                    overridden_config[key] = env_value
            
            logger.debug(f"Overridden {key} from environment variable {env_var}")
    
    return overridden_config


def load_redis_config(config_path: Optional[str] = None, env: str = 'local') -> Optional[Dict[str, Any]]:
    """
    Load Redis configuration with environment variable overrides
    
    Args:
        config_path: Path to redis_config.json (default: 'redis_config.json' in current directory)
        env: Environment name ('local' or 'production')
        
    Returns:
        Redis configuration dictionary with environment overrides applied, or None if not found
    """
    if config_path is None:
        # Default to redis_config.json in the portfolio_manager directory
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'redis_config.json'
        )
    
    config = load_config_file(config_path, env)
    
    if config is None:
        return None
    
    # Apply environment variable overrides
    overridden_config = apply_env_overrides(config, 'REDIS')
    
    # Handle password placeholder (${REDIS_PASSWORD})
    if isinstance(overridden_config.get('password'), str):
        password = overridden_config['password']
        if password.startswith('${') and password.endswith('}'):
            # Extract environment variable name
            env_var = password[2:-1]
            if env_var in os.environ:
                overridden_config['password'] = os.environ[env_var]
            else:
                logger.warning(f"Environment variable {env_var} not set, using None for password")
                overridden_config['password'] = None
    
    return overridden_config


def load_database_config(config_path: Optional[str] = None, env: str = 'local') -> Optional[Dict[str, Any]]:
    """
    Load database configuration with environment variable overrides
    
    Args:
        config_path: Path to database_config.json (default: 'database_config.json' in current directory)
        env: Environment name ('local' or 'production')
        
    Returns:
        Database configuration dictionary with environment overrides applied, or None if not found
    """
    if config_path is None:
        # Default to database_config.json in the portfolio_manager directory
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'database_config.json'
        )
    
    config = load_config_file(config_path, env)
    
    if config is None:
        return None
    
    # Apply environment variable overrides
    overridden_config = apply_env_overrides(config, 'DB')
    
    # Handle password placeholder (${DB_PASSWORD})
    if isinstance(overridden_config.get('password'), str):
        password = overridden_config['password']
        if password.startswith('${') and password.endswith('}'):
            # Extract environment variable name
            env_var = password[2:-1]
            if env_var in os.environ:
                overridden_config['password'] = os.environ[env_var]
            else:
                logger.warning(f"Environment variable {env_var} not set, using None for password")
                overridden_config['password'] = None
    
    return overridden_config

