import os
import logging
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Application settings, pulling defaults from environment variables.
    Automatically reads from a `.env` file if present in the working directory.
    """
    # Define these with explicit typing for validation
    # No known-value fallback here: a hardcoded default is a publicly
    # readable forgeable secret. See the fail-closed (random, process-local)
    # fallback applied below when SECRET_KEY is unset.
    secret_key: str = ""
    algorithm: str = "HS256"
    # Database Configuration (MySQL)
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "yolo_generator"
    # Pooled connections held open per process. MySQL's connector caps a pool at
    # 32; keep this at or below the server's max_connections divided by the
    # number of API processes.
    db_pool_size: int = 10

    # API Configuration
    api_v1_str: str = "/api/v1"
    
    # Allowed origins
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Frontend URL (for invites/password resets)
    frontend_url: str = "http://localhost:3000"

    # Send Strict-Transport-Security. Off by default: over plain HTTP in local
    # development it pins the browser to https://localhost, which then refuses
    # to connect. Turn it on wherever the API is served over TLS.
    enable_hsts: bool = False

    # Will look for .env in the /server dir
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # ignore extra variables in the env file that aren't defined here
    )

    @property
    def get_cors_origins(self) -> list[str]:
        return [orig.strip() for orig in self.cors_origins.split(",") if orig.strip()]

settings = Settings()
if not settings.secret_key:
    settings.secret_key = secrets.token_urlsafe(32)
    logger.warning(
        "SECRET_KEY is not set in the environment. Using a randomly generated "
        "key for this process only; tokens signed with it (e.g. invite links) "
        "will stop validating on restart. Set SECRET_KEY before deploying to production."
    )
