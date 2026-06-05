from __future__ import annotations

from app.extractors.common import field, line_texts, pick_after_anchor
from app.validators import (
    DATE_PATTERN,
    IDCARD_PATTERN,
    date_is_valid,
    normalize_date,
    validate_idcard_number,
)


def extract_driver_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts = line_texts(lines)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    id_no = ""
    for line in texts:
        m = IDCARD_PATTERN.search(line.replace(" ", ""))
        if m:
            id_no = m.group(0).upper()
            break
    fields["证号"] = field(id_no, 0.95 if id_no else 0.0, "regex:idcard" if id_no else "fallback_missing")

    mapping = {
        "姓名": ["姓名"],
        "住址": ["住址", "地址"],
        "国籍": ["国籍"],
        "准驾车型": ["准驾车型"],
        "性别": ["性别"],
        "发证单位": ["发证单位", "签发机关"],
    }
    for k, anchors in mapping.items():
        value, src = pick_after_anchor(texts, anchors)
        fields[k] = field(value, 0.86 if value else 0.0, src)

    date_fields = {
        "出生日期": ["出生日期", "出生"],
        "初次领证日期": ["初次领证日期", "初次领证"],
        "有效期开始": ["有效期限", "有效期起", "起始日期"],
        "有效期结束": ["有效期限", "有效期止", "截止日期"],
    }
    for k, anchors in date_fields.items():
        value, src = pick_after_anchor(texts, anchors)
        dm = DATE_PATTERN.search(value)
        final = normalize_date(dm.group(0)) if dm else ""
        fields[k] = field(final, 0.82 if final else 0.0, src if final else "fallback_missing")

    validation = {
        "rules": {
            "证号格式疑似身份证": bool(id_no),
            "证号校验通过": validate_idcard_number(id_no) if id_no else False,
            "有效期开始合法": date_is_valid(fields["有效期开始"]["value"]) if fields["有效期开始"]["value"] else False,
            "有效期结束合法": date_is_valid(fields["有效期结束"]["value"]) if fields["有效期结束"]["value"] else False,
        },
        "warnings": [],
    }
    if fields["有效期开始"]["value"] and fields["有效期结束"]["value"]:
        if fields["有效期开始"]["value"] > fields["有效期结束"]["value"]:
            validation["warnings"].append("有效期开始晚于结束")

    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text
