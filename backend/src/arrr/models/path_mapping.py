from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from arrr.db import Base


class RemotePathMapping(Base):
    __tablename__ = "remote_path_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("download_clients.id", ondelete="CASCADE"))
    remote_path: Mapped[str] = mapped_column(String(500))  # as the download client reports it
    local_path: Mapped[str] = mapped_column(String(500))  # as arrr sees it
