from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Pinky Bread"
    app_env: str = "development"
    dev_mode: bool = True
    auth_enabled: bool = False
    dev_auth_enabled: bool = True
    dev_admin_username: str = "admin"
    dev_admin_password: str = "admin"
    session_secret: str = "pinky-bread-local-development-session-secret-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    mock_inference: bool = False
    database_url: str = "sqlite:///./data/pinky_bread.db"
    auto_create_schema: bool = True
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = "http://localhost:8333"
    s3_region: str = "us-east-1"
    s3_bucket: str = "pinky-bread"
    s3_access_key: str = "pinky_bread_dev"
    s3_secret_key: str = "pinky_bread_dev_secret_change_me"
    agent_config_dir: Path = Path("./config/agents")
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 12
    reasoning_api_url: str = "http://127.0.0.1:11434/v1"
    reasoning_model: str = "qwen2.5:3b"
    openai_api_key: str = ""
    openai_api_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    openai_compatible_api_key: str = ""
    companion_public_url: str = "http://localhost:3020"
    companion_upload_token: str = ""
    companion_upload_target_base_url: str = "http://api:8080"
    companion_google_key: str = ""
    companion_google_secret: str = ""
    companion_dropbox_key: str = ""
    companion_dropbox_secret: str = ""
    companion_onedrive_key: str = ""
    companion_onedrive_secret: str = ""
    companion_box_key: str = ""
    companion_box_secret: str = ""
    multimodal_api_url: str = "http://localhost:8002/v1"
    multimodal_model: str = "local-vision"
    vllm_api_key: str = "local-dev-key"
    model_provider: Literal["vllm", "ollama", "openai-compatible", "openai", "gemini"] = "ollama"
    worker_poll_seconds: float = 1.5
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 20
    worker_max_attempts: int = 5
    mcp_enabled: bool = False
    mcp_server_url: str = "http://127.0.0.1:8060/mcp"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8060
    mcp_api_token: str = ""
    mcp_read_token: str = ""
    mcp_resource_url: str = "http://127.0.0.1:8060/mcp"
    mcp_issuer_url: str = "http://127.0.0.1:8888/issuer"
    mcp_max_tool_rounds: int = 4

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(parents=True, exist_ok=True)
    return s
