"""Database models for the IMS (see docs/SPEC.md §4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

UNASSIGNED_LOCATION_ID = 0
UNASSIGNED_LOCATION_LABEL = "Sem localização"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "item"

    # Legacy `id` from the workbook; kept so the export lines up with it.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    reference: Mapped[str | None] = mapped_column(String(120))
    ean: Mapped[str | None] = mapped_column(String(32))
    # Legacy S_N column. One per item for now; per-unit serials are a later feature.
    serial_number: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    stock: Mapped[list["Stock"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class Location(Base):
    __tablename__ = "location"
    __table_args__ = (UniqueConstraint("estante", "prateleira", name="uq_location_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    estante: Mapped[int | None] = mapped_column(Integer)
    prateleira: Mapped[str | None] = mapped_column(String(20))
    # Optional display name (e.g. "Corredor A"). When blank, the label comes from rack and shelf.
    name: Mapped[str | None] = mapped_column(String(120))

    @property
    def label(self) -> str:
        if self.id == UNASSIGNED_LOCATION_ID:
            return UNASSIGNED_LOCATION_LABEL
        if self.name:
            return self.name
        if not self.prateleira:  # rack without a shelf, e.g. from the workbook
            return f"E{self.estante}"
        shelf = "Topo" if self.prateleira == "Topo" else f"P{self.prateleira}"
        return f"E{self.estante}-{shelf}"


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = (CheckConstraint("qty >= 0", name="ck_stock_non_negative"),)

    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    item: Mapped[Item] = relationship(back_populates="stock")
    location: Mapped[Location] = relationship()


class Movement(Base):
    """Append-only log of every stock change. Corrections are new rows."""

    __tablename__ = "movement"
    __table_args__ = (
        CheckConstraint("type IN ('IN','OUT','MOVE','ADJUST','VERIFY','IMPORT')", name="ck_movement_type"),
        CheckConstraint("source IN ('local','mobile','import')", name="ck_movement_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"), nullable=False, index=True)
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="local")
    external_ref: Mapped[str | None] = mapped_column(String(120), unique=True)


class SyncRun(Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # export | poll | import
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="running")
    detail: Mapped[str | None] = mapped_column(Text)
