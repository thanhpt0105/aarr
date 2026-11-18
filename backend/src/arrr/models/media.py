from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arrr.db import Base, UTCDateTime, utcnow
from arrr.models.library import RootFolder


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), default=None)
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[str] = mapped_column(String(500), default="")
    year: Mapped[int | None] = mapped_column(Integer, default=None)
    overview: Mapped[str] = mapped_column(Text, default="")
    poster_path: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str | None] = mapped_column(String(50), default=None)
    runtime: Mapped[int | None] = mapped_column(Integer, default=None)
    in_cinemas: Mapped[date | None] = mapped_column(Date, default=None)
    digital_release: Mapped[date | None] = mapped_column(Date, default=None)
    physical_release: Mapped[date | None] = mapped_column(Date, default=None)

    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_profile_id: Mapped[int] = mapped_column(
        ForeignKey("quality_profiles.id", ondelete="RESTRICT")
    )
    root_folder_id: Mapped[int] = mapped_column(ForeignKey("root_folders.id", ondelete="RESTRICT"))
    root_folder: Mapped[RootFolder] = relationship(lazy="joined")
    folder_name: Mapped[str] = mapped_column(String(500))  # inside the root folder

    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
