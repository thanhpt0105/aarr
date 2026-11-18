from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aarr.db import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)  # value is Fernet-encrypted
