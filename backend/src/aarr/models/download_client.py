from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from aarr.db import Base


class DownloadClientConfig(Base):
    __tablename__ = "download_clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    url: Mapped[str] = mapped_column(String(500))
    username: Mapped[str | None] = mapped_column(String(200), default=None)
    # qBittorrent password or SABnzbd API key, Fernet-encrypted
    secret_encrypted: Mapped[str | None] = mapped_column(String(1000), default=None)
    movie_category: Mapped[str] = mapped_column(String(100), default="aarr-movies")
    tv_category: Mapped[str] = mapped_column(String(100), default="aarr-tv")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
