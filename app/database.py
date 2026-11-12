from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, Text, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .settings import get_settings


class Base(DeclarativeBase):
    pass


class WorkflowRecord(Base):
    __tablename__ = "workflows"
    thread_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    user_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    state_json: Mapped[str] = mapped_column(Text)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


_settings = get_settings()
if _settings.database_url.startswith("sqlite"):
    Path("./data").mkdir(exist_ok=True)
    _engine = create_engine(_settings.database_url, connect_args={"check_same_thread": False})
else:
    _engine = create_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=_engine)


def serialize_state(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, default=str)


def deserialize_state(value: str) -> dict:
    return json.loads(value)
