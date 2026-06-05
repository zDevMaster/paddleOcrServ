"""OCR 结果字段抽取：按证件类型分模块，便于分别维护与优化。"""

from __future__ import annotations

from app.extractors.driver_license import extract_driver_license
from app.extractors.handwriting import extract_handwriting
from app.extractors.id_card import extract_idcard, idcard_result_score
from app.extractors.vehicle_license import extract_vehicle_license
from app.models import DocumentType

__all__ = [
    "extract_by_doc_type",
    "extract_driver_license",
    "extract_handwriting",
    "extract_idcard",
    "extract_vehicle_license",
    "idcard_result_score",
]


def extract_by_doc_type(doc_type: DocumentType, lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    if doc_type == DocumentType.idcard:
        return extract_idcard(lines)
    if doc_type == DocumentType.driver_license:
        return extract_driver_license(lines)
    if doc_type == DocumentType.vehicle_license:
        return extract_vehicle_license(lines)
    return extract_handwriting(lines)
