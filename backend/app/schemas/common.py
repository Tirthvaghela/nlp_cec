from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

T = TypeVar("T")


def _strip_text(v: str) -> str:
    return v.strip()


def _half_step(v: float) -> float:
    if abs(v * 2 - round(v * 2)) > 1e-9:
        raise ValueError("must be a multiple of 0.5")
    return round(v, 2)


def _to_utc(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
HalfMarks = Annotated[float, AfterValidator(_half_step)]
UtcDatetime = Annotated[datetime, AfterValidator(_to_utc)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int


class Message(BaseModel):
    detail: str
