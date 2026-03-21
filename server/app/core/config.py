import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings, pulling defaults from environment variables.
    Automatically reads from a `.env` file if present in the working directory.
    """
    # Define these with explicit typing for validation
    secret_key: str = "your-super-secret-default-key-please-change-in-prod"
    algorithm: str = "HS256"
    # Database Configuration (MySQL)
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "yolo_generator"

    # API Configuration
    api_v1_str: str = "/api/v1"
    
    # Allowed origins
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Frontend URL (for invites/password resets)
    frontend_url: str = "http://localhost:3000"

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
