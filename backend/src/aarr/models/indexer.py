from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aarr.db import Base


class IndexerConfig(Base):
    __tablename__ = "indexers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    protocol: Mapped[str] = mapped_column(String(10))  # torrent | usenet
    url: Mapped[str] = mapped_column(String(500))  # full Torznab/Newznab API endpoint
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1000), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=25)  # lower wins ties
