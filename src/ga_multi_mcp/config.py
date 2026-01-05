"""
Configuration management for GA Multi MCP server.

Handles environment-based configuration with sensible defaults
and validation for required settings.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


@dataclass
class Config:
    """
    Configuration for the GA Multi MCP server.

    All settings are loaded from environment variables to ensure
    the server can be configured without code changes.
    """

    # Path to Google service account JSON credentials
    credentials_path: str

    # Cache TTL for API responses (seconds)
    cache_ttl: int = 300  # 5 minutes

    # Cache TTL for property list (seconds)
    property_cache_ttl: int = 3600  # 1 hour

    # Fuzzy matching threshold (0.0 to 1.0)
    fuzzy_threshold: float = 0.6

    # Custom property aliases (property_name -> [aliases])
    custom_aliases: dict = field(default_factory=dict)

    # Default limit for query results
    default_limit: int = 1000

    # Whether to mask error details in responses
    mask_error_details: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.

        Environment Variables:
            GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON (required)
            GA_CREDENTIALS_PATH: Alternative path to service account JSON
            GA_CACHE_TTL: Cache TTL for API responses in seconds (default: 300)
            GA_PROPERTY_CACHE_TTL: Cache TTL for property list in seconds (default: 3600)
            GA_FUZZY_THRESHOLD: Fuzzy matching threshold 0.0-1.0 (default: 0.6)
            GA_PROPERTY_ALIASES: JSON string of custom aliases
            GA_DEFAULT_LIMIT: Default limit for query results (default: 1000)
            GA_MASK_ERRORS: Whether to mask error details (default: false)

        Returns:
            Config: Validated configuration object

        Raises:
            ConfigError: If required configuration is missing or invalid
        """
        # Find credentials path - try multiple env vars
        credentials_path = (
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
            os.getenv("GA_CREDENTIALS_PATH") or
            os.getenv("GA_SERVICE_ACCOUNT_PATH")
        )

        if not credentials_path:
            raise ConfigError(
                "Google credentials path required. Set GOOGLE_APPLICATION_CREDENTIALS "
                "or GA_CREDENTIALS_PATH environment variable to the path of your "
                "service account JSON file."
            )

        # Validate credentials file exists
        credentials_file = Path(credentials_path)
        if not credentials_file.exists():
            raise ConfigError(
                f"Credentials file not found at: {credentials_path}. "
                "Please ensure the file exists and the path is correct."
            )

        # Parse optional cache TTL
        cache_ttl = 300
        if cache_ttl_str := os.getenv("GA_CACHE_TTL"):
            try:
                cache_ttl = int(cache_ttl_str)
            except ValueError:
                raise ConfigError(f"GA_CACHE_TTL must be an integer, got: {cache_ttl_str}")

        # Parse optional property cache TTL
        property_cache_ttl = 3600
        if property_cache_ttl_str := os.getenv("GA_PROPERTY_CACHE_TTL"):
            try:
                property_cache_ttl = int(property_cache_ttl_str)
            except ValueError:
                raise ConfigError(
                    f"GA_PROPERTY_CACHE_TTL must be an integer, got: {property_cache_ttl_str}"
                )

        # Parse optional fuzzy threshold
        fuzzy_threshold = 0.6
        if fuzzy_threshold_str := os.getenv("GA_FUZZY_THRESHOLD"):
            try:
                fuzzy_threshold = float(fuzzy_threshold_str)
                if not 0.0 <= fuzzy_threshold <= 1.0:
                    raise ValueError("Must be between 0.0 and 1.0")
            except ValueError as e:
                raise ConfigError(
                    f"GA_FUZZY_THRESHOLD must be a float between 0.0 and 1.0, "
                    f"got: {fuzzy_threshold_str}. {e}"
                )

        # Parse optional custom aliases
        custom_aliases = {}
        if aliases_json := os.getenv("GA_PROPERTY_ALIASES"):
            try:
                custom_aliases = json.loads(aliases_json)
                if not isinstance(custom_aliases, dict):
                    raise ValueError("Must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                raise ConfigError(
                    f"GA_PROPERTY_ALIASES must be valid JSON object, got: {aliases_json}. {e}"
                )

        # Parse optional default limit
        default_limit = 1000
        if limit_str := os.getenv("GA_DEFAULT_LIMIT"):
            try:
                default_limit = int(limit_str)
                if default_limit < 1:
                    raise ValueError("Must be positive")
            except ValueError as e:
                raise ConfigError(
                    f"GA_DEFAULT_LIMIT must be a positive integer, got: {limit_str}. {e}"
                )

        # Parse optional mask errors flag
        mask_error_details = os.getenv("GA_MASK_ERRORS", "").lower() in ("true", "1", "yes")

        return cls(
            credentials_path=credentials_path,
            cache_ttl=cache_ttl,
            property_cache_ttl=property_cache_ttl,
            fuzzy_threshold=fuzzy_threshold,
            custom_aliases=custom_aliases,
            default_limit=default_limit,
            mask_error_details=mask_error_details,
        )


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Configuration is loaded from environment variables on first access.

    Returns:
        Config: The configuration instance

    Raises:
        ConfigError: If configuration is invalid
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
