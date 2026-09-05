from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ResponseMeta(BaseModel):
    request_id: str = Field(description="Unique correlation ID for tracing")
    timestamp: str = Field(
        default_factory=utc_now_iso,
        description="UTC ISO-8601 timestamp",
    )


class APIResponse(BaseModel, Generic[DataT]):
    data: DataT
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
