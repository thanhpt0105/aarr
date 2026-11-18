from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AARR_")

    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8686
    queue_poll_seconds: int = 15  # 0 disables background polling
    tmdb_api_key: str | None = None  # fallback when no key is saved in settings
