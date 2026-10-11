import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

API_DIR = Path(__file__).resolve().parent


class Settings(BaseModel):
    FASTAPI_ENV: Literal["development", "production", "test"] = "development"
    PORT: int = Field(default=3000, gt=0, le=65535)
    WEB_DIST: str = "../web/dist"
    MAX_MEGAPIXELS: float = Field(default=50, gt=0, allow_inf_nan=False)
    MAX_QUEUE_DEPTH: int = Field(default=10, gt=0)
    JOB_TIMEOUT_SECONDS: float = Field(default=120, gt=0, allow_inf_nan=False)
    UPLOADS_PER_HOUR: int = Field(default=200, gt=0)
    MAX_UPLOAD_BYTES: int = Field(default=256 * 1024 * 1024, gt=0)

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls.model_validate({key: os.environ[key] for key in cls.model_fields if key in os.environ})

    @property
    def client_dist(self) -> Path:
        return (API_DIR / self.WEB_DIST).resolve()
