from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    idcard = "idcard"
    driver_license = "driver_license"
    vehicle_license = "vehicle_license"
    handwriting = "handwriting"


class ImageJsonRequest(BaseModel):
    imageBase64: str = Field(..., description="Base64 image string, without data URL header.")
    docType: str | None = Field(None, description="Optional, for client-side routing.")
    options: dict[str, Any] | None = None


class RawLine(BaseModel):
    text: str
    bbox: list[list[float]]
    score: float


class FieldValue(BaseModel):
    value: Any = ""
    confidence: float = 0.0
    source: str = "fallback_missing"


class ValidationInfo(BaseModel):
    rules: dict[str, bool | str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class QualityInfo(BaseModel):
    blurScore: float = 0.0
    reflectionScore: float = 0.0
    tiltScore: float = 0.0
    overall: float = 0.0


class OcrPayload(BaseModel):
    docType: str
    fields: dict[str, FieldValue]
    text: str = ""


class OcrResponse(BaseModel):
    success: bool = True
    traceId: str
    elapsedMs: int
    data: OcrPayload

