from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from arrr.db import Base

RESOLUTIONS = (480, 576, 720, 1080, 2160)


class QualityProfile(Base):
    __tablename__ = "quality_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    allowed_resolutions: Mapped[list[int]] = mapped_column(JSON)  # ascending
    cutoff_resolution: Mapped[int | None] = mapped_column(Integer, default=None)
    upgrades_allowed: Mapped[bool] = mapped_column(Boolean, default=True)


class RootFolder(Base):
    __tablename__ = "root_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(500), unique=True)
    media_type: Mapped[str] = mapped_column(String(10))  # movie | tv
