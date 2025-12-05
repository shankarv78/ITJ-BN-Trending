"""
Unit tests for config_loader module
"""
import pytest
import json
import os
import tempfile
from pathlib import Path
from core.config_loader import (
    load_config_file,
    apply_env_overrides,
    load_redis_config,
    load_database_config
)


class TestLoadConfigFile:
    """Tests for load_config_file function"""
    
    def test_load_valid_config(self):
        """Test loading a valid config file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {
                    'host': 'localhost',
                    'port': 6379
                },
                'production': {
                    'host': 'prod.example.com',
                    'port': 6379
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = load_config_file(temp_path, 'local')
            assert config is not None
            assert config['host'] == 'localhost'
            assert config['port'] == 6379
        finally:
            os.unlink(temp_path)
    
    def test_load_production_config(self):
        """Test loading production environment config"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {'host': 'localhost'},
                'production': {'host': 'prod.example.com'}
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = load_config_file(temp_path, 'production')
            assert config is not None
            assert config['host'] == 'prod.example.com'
        finally:
            os.unlink(temp_path)
    
    def test_load_nonexistent_file(self):
        """Test loading a non-existent file"""
        config = load_config_file('/nonexistent/file.json')
        assert config is None
    
    def test_load_invalid_json(self):
        """Test loading invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('invalid json {')
            temp_path = f.name
        
        try:
            config = load_config_file(temp_path)
            assert config is None
        finally:
            os.unlink(temp_path)
    
    def test_load_missing_environment(self):
        """Test loading config for missing environment"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {'local': {'host': 'localhost'}}
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = load_config_file(temp_path, 'production')
            # Should fallback to 'local' if 'production' not found
            assert config is not None
            assert config['host'] == 'localhost'
        finally:
            os.unlink(temp_path)


class TestApplyEnvOverrides:
    """Tests for apply_env_overrides function"""
    
    def test_override_string_value(self, monkeypatch):
        """Test overriding a string value"""
        config = {'host': 'localhost', 'port': 6379}
        monkeypatch.setenv('REDIS_HOST', 'override.example.com')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['host'] == 'override.example.com'
        assert overridden['port'] == 6379  # Not overridden
    
    def test_override_integer_value(self, monkeypatch):
        """Test overriding an integer value"""
        config = {'port': 6379}
        monkeypatch.setenv('REDIS_PORT', '6380')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['port'] == 6380
        assert isinstance(overridden['port'], int)
    
    def test_override_boolean_value(self, monkeypatch):
        """Test overriding a boolean value"""
        config = {'ssl': False}
        monkeypatch.setenv('REDIS_SSL', 'true')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['ssl'] is True
    
    def test_override_boolean_false(self, monkeypatch):
        """Test overriding boolean to False"""
        config = {'ssl': True}
        monkeypatch.setenv('REDIS_SSL', 'false')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['ssl'] is False
    
    def test_override_float_value(self, monkeypatch):
        """Test overriding a float value"""
        config = {'socket_timeout': 2.0}
        monkeypatch.setenv('REDIS_SOCKET_TIMEOUT', '5.5')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['socket_timeout'] == 5.5
        assert isinstance(overridden['socket_timeout'], float)
    
    def test_override_none_value(self, monkeypatch):
        """Test overriding with null/empty string"""
        config = {'password': 'secret'}
        monkeypatch.setenv('REDIS_PASSWORD', 'null')
        
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['password'] is None
    
    def test_no_override_when_env_var_missing(self):
        """Test that config remains unchanged when env var is missing"""
        config = {'host': 'localhost'}
        overridden = apply_env_overrides(config, 'REDIS')
        assert overridden['host'] == 'localhost'


class TestLoadRedisConfig:
    """Tests for load_redis_config function"""
    
    def test_load_redis_config_from_file(self):
        """Test loading Redis config from file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {
                    'host': 'localhost',
                    'port': 6379,
                    'db': 0,
                    'password': None,
                    'ssl': False,
                    'socket_timeout': 2.0,
                    'enable_redis': True
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = load_redis_config(temp_path, 'local')
            assert config is not None
            assert config['host'] == 'localhost'
            assert config['port'] == 6379
            assert config['enable_redis'] is True
        finally:
            os.unlink(temp_path)
    
    def test_load_redis_config_with_env_overrides(self, monkeypatch):
        """Test loading Redis config with environment variable overrides"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {
                    'host': 'localhost',
                    'port': 6379,
                    'ssl': False
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            monkeypatch.setenv('REDIS_HOST', 'override.example.com')
            monkeypatch.setenv('REDIS_PORT', '6380')
            monkeypatch.setenv('REDIS_SSL', 'true')
            
            config = load_redis_config(temp_path, 'local')
            assert config is not None
            assert config['host'] == 'override.example.com'
            assert config['port'] == 6380
            assert config['ssl'] is True
        finally:
            os.unlink(temp_path)
    
    def test_load_redis_config_password_placeholder(self, monkeypatch):
        """Test loading Redis config with password placeholder"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'production': {
                    'host': 'redis.example.com',
                    'password': '${REDIS_PASSWORD}'
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            monkeypatch.setenv('REDIS_PASSWORD', 'secret123')
            
            config = load_redis_config(temp_path, 'production')
            assert config is not None
            assert config['password'] == 'secret123'
        finally:
            os.unlink(temp_path)
    
    def test_load_redis_config_missing_password_env(self):
        """Test loading Redis config with missing password env var"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'production': {
                    'host': 'redis.example.com',
                    'password': '${REDIS_PASSWORD}'
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            # Ensure env var is not set
            if 'REDIS_PASSWORD' in os.environ:
                del os.environ['REDIS_PASSWORD']
            
            config = load_redis_config(temp_path, 'production')
            assert config is not None
            assert config['password'] is None
        finally:
            os.unlink(temp_path)


class TestLoadDatabaseConfig:
    """Tests for load_database_config function"""
    
    def test_load_database_config_from_file(self):
        """Test loading database config from file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'portfolio_manager',
                    'user': 'pm_user',
                    'password': 'secret'
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config = load_database_config(temp_path, 'local')
            assert config is not None
            assert config['host'] == 'localhost'
            assert config['database'] == 'portfolio_manager'
        finally:
            os.unlink(temp_path)
    
    def test_load_database_config_with_env_overrides(self, monkeypatch):
        """Test loading database config with environment variable overrides"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'local': {
                    'host': 'localhost',
                    'port': 5432
                }
            }
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            monkeypatch.setenv('DB_HOST', 'override.example.com')
            monkeypatch.setenv('DB_PORT', '5433')
            
            config = load_database_config(temp_path, 'local')
            assert config is not None
            assert config['host'] == 'override.example.com'
            assert config['port'] == 5433
        finally:
            os.unlink(temp_path)

