import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LegAlly"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "replace-with-a-long-random-secret"
    database_url: str = (
        "sqlite:////tmp/legalally.db"
        if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        else "sqlite:///./legalally.db"
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:8000"]
    rate_limit_per_minute: int = 120
    google_client_id: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    pico_ws_url: str = "wss://backend.buildpicoapps.com/ask_ai_streaming_v2"
    pico_app_id: str = "even-American"
    pico_lawyer_app_id: str = "garden-hospital"
    pico_companion_app_id: str = "past-short"
    pico_stream_timeout_seconds: int = 25
    pico_max_prompt_chars: int = 4000
    agent_service_url: str | None = None
    agent_service_key: str | None = None
    agent_model: str = "anthropic/claude-sonnet-5-5"
    agent_timeout_seconds: int = 90
    log_level: str = "INFO"


settings = Settings()
