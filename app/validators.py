from __future__ import annotations

import re
from datetime import datetime


IDCARD_PATTERN = re.compile(r"\d{17}[\dXx]")
DATE_PATTERN = re.compile(r"(19|20)\d{2}[./-]?(0[1-9]|1[0-2])[./-]?(0[1-9]|[12]\d|3[01])")
PLATE_PATTERN = re.compile(r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}")


def normalize_date(value: str) -> str:
    cleaned = re.sub(r"[^\d]", "", value)
    if len(cleaned) != 8:
        return value
    return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"


def parse_date(value: str) -> str | None:
    normalized = normalize_date(value)
    try:
        datetime.strptime(normalized, "%Y-%m-%d")
        return normalized
    except Exception:
        return None


def validate_idcard_number(value: str) -> bool:
    if not value or not IDCARD_PATTERN.fullmatch(value):
        return False
    factors = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    mapping = "10X98765432"
    total = sum(int(value[i]) * factors[i] for i in range(17))
    return mapping[total % 11] == value[-1].upper()


def date_is_valid(value: str) -> bool:
    return parse_date(value) is not None


def plate_is_valid(value: str) -> bool:
    return bool(value and PLATE_PATTERN.fullmatch(value))

