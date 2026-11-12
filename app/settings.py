from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Pinky Bread"
    app_env: str = "development"
    dev_mode: bool = True
    mock_inference: bool = True
    database_url: str = "sqlite:///./data/pinky_bread.db"
    redis_url: str = "redis://localhost:6379/0"
    agent_config_dir: Path = Path("./config/agents")
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 12
    reasoning_api_url: str = "http://localhost:8001/v1"
    reasoning_model: str = "local-reasoner"
    multimodal_api_url: str = "http://localhost:8002/v1"
    multimodal_model: str = "local-vision"
    vllm_api_key: str = "local-dev-key"

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
