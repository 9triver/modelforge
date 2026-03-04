from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ModelForge"
    MODEL_STORE_PATH: Path = Path("./model_store")
    MAX_UPLOAD_SIZE_MB: int = 500
    API_V1_PREFIX: str = "/api/v1"

    model_config = {"env_prefix": "MODELFORGE_"}


settings = Settings()
