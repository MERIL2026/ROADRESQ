from typing import Any

from pydantic import BaseModel


class ServiceHealthInfo(BaseModel):
    status: str
    details: dict[str, Any]


class LivenessData(BaseModel):
    status: str
    app_name: str
    environment: str
    version: str = "0.1.0"


class ReadinessData(BaseModel):
    status: str
    database: ServiceHealthInfo
    redis: ServiceHealthInfo
