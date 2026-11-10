from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from app.db.base import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ar: Mapped[str]
    description_ar: Mapped[Optional[str]] = mapped_column(default=None)
    status: Mapped[int] = mapped_column(default=1)