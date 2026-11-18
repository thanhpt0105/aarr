from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARRR_")

    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8686
