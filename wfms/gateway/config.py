"""
Gateway Configuration Management

Load configuration from .env file and validate.
Uses pydantic-settings for robust config handling.
"""

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    Gateway configuration loaded from environment variables.
    """
    
    # UART Configuration
    uart_port: str = Field(default="COM13", description="Serial port for Zigbee Coordinator")
    uart_baud: int = Field(default=115200, description="Serial baud rate")
    
    # MQTT Configuration
    mqtt_host: str = Field(default="127.0.0.1", description="MQTT broker host")
    mqtt_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_user: Optional[str] = Field(default="", description="MQTT username (optional)")
    mqtt_pass: Optional[str] = Field(default="", description="MQTT password (optional)")
    
    # Site identifier
    site: str = Field(default="lab1", description="Site identifier for MQTT topics")
    
    # Rules Engine Configuration
    rule_lock: int = Field(default=0, description="Lock mode: 0=disabled, 1=enabled")
    rule_cooldown_user_s: int = Field(default=3, description="Per-user cooldown in seconds")
    rule_cooldown_global_s: int = Field(default=1, description="Global cooldown in seconds")
    rule_dedupe_ttl_s: int = Field(default=60, description="Deduplication TTL in seconds")
    ack_timeout_s: int = Field(default=3, description="ACK timeout in seconds")
    
    # TX Pacing Configuration (Fix UART corruption)
    uart_tx_chunk_size: int = Field(default=8, description="Chunk size for TX pacing (0=disabled)")
    uart_tx_chunk_delay_ms: int = Field(default=10, description="Delay between TX chunks in ms")
    uart_tx_char_delay_ms: int = Field(default=0, description="Per-char delay in ms (0=use chunk mode)")
    
    # Retry Backoff Configuration
    cmd_retry_base_delay_s: float = Field(default=0.3, description="Base delay before retry")
    cmd_retry_max_delay_s: float = Field(default=1.2, description="Max retry delay cap")
    cmd_retry_jitter_s: float = Field(default=0.2, description="Random jitter for retry")
    
    # Admin API Configuration
    api_host: str = Field(default="127.0.0.1", description="Local Admin API host (localhost only!)")
    api_port: int = Field(default=8080, description="Local Admin API port")
    api_token: Optional[str] = Field(default="", description="Admin API token (empty to disable auth)")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Log level")
    log_file: Optional[str] = Field(default="gateway.log", description="Log file path (empty to disable)")
    
    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields in .env
    )
    
    @field_validator("uart_baud")
    @classmethod
    def validate_baud(cls, v: int) -> int:
        """Validate baud rate is positive."""
        if v <= 0:
            raise ValueError("UART_BAUD must be positive")
        return v
    
    @field_validator("mqtt_port", "api_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator("api_host")
    @classmethod
    def validate_api_host(cls, v: str) -> str:
        """Validate API host is localhost for security."""
        allowed = ("127.0.0.1", "localhost", "::1")
        if v not in allowed:
            raise ValueError(f"API_HOST must be one of {allowed} for security")
        return v
    
    @field_validator("rule_lock")
    @classmethod
    def validate_lock(cls, v: int) -> int:
        """Validate lock is 0 or 1."""
        if v not in (0, 1):
            raise ValueError("RULE_LOCK must be 0 or 1")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper
    
    @property
    def is_locked(self) -> bool:
        """Check if gateway is in lock mode."""
        return self.rule_lock == 1
    
    @property
    def mqtt_auth_enabled(self) -> bool:
        """Check if MQTT authentication is configured."""
        return bool(self.mqtt_user and self.mqtt_pass)
    
    @property
    def api_auth_enabled(self) -> bool:
        """Check if Admin API token authentication is configured."""
        return bool(self.api_token)


def load_config(env_path: Optional[str] = None) -> Config:
    """
    Load configuration from .env file.
    
    Args:
        env_path: Path to .env file (default: .env in current directory)
    
    Returns:
        Config: Validated configuration object
    
    Raises:
        ValueError: If configuration validation fails
        FileNotFoundError: If .env file doesn't exist (warning only)
    """
    # Check if .env exists
    env_file = env_path or ".env"
    if not os.path.exists(env_file):
        print(f"Warning: {env_file} not found. Using default values and environment variables.")
    
    # Load and validate config
    config = Config()
    
    # Update contract.py site after loading
    from common.contract import update_site
    update_site(config.site)
    
    return config


# For testing/debugging
if __name__ == "__main__":
    config = load_config()
    print("=== Gateway Configuration ===")
    print(f"UART: {config.uart_port} @ {config.uart_baud} baud")
    print(f"MQTT: {config.mqtt_host}:{config.mqtt_port}")
    print(f"Site: {config.site}")
    print(f"Lock: {'ENABLED' if config.is_locked else 'DISABLED'}")
    print(f"API Port: {config.api_port}")
    print(f"Log Level: {config.log_level}")
