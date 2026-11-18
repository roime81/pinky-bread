from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Pinky Bread"
    app_env: str = "development"
    dev_mode: bool = True
    mock_inference: bool = True
    database_url: str = "sqlite:///./data/pinky_bread.db"
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
    reasoning_api_url: str = "http://localhost:8001/v1"
    reasoning_model: str = "local-reasoner"
    multimodal_api_url: str = "http://localhost:8002/v1"
    multimodal_model: str = "local-vision"
    vllm_api_key: str = "local-dev-key"
    model_provider: Literal["vllm", "ollama", "openai-compatible"] = "openai-compatible"
    worker_poll_seconds: float = 1.5
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 20
    worker_max_attempts: int = 5
    mcp_enabled: bool = False
    mcp_server_url: str = "http://localhost:8090/mcp"
    mcp_api_token: str = ""
    mcp_resource_url: str = "http://localhost:8090/mcp"
    mcp_issuer_url: str = "http://localhost:8080/issuer"
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
