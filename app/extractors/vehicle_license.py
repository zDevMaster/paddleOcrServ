from __future__ import annotations

from app.extractors.common import field, line_texts, pick_after_anchor
from app.validators import (
    DATE_PATTERN,
    PLATE_PATTERN,
    date_is_valid,
    normalize_date,
    plate_is_valid,
)


def extract_vehicle_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts = line_texts(lines)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    plate = ""
    for line in texts:
        m = PLATE_PATTERN.search(line.replace(" ", "").upper())
        if m:
            plate = m.group(0)
            break
    fields["车牌号"] = field(plate, 0.96 if plate else 0.0, "regex:plate" if plate else "fallback_missing")

    mapping = {
        "车辆识别代号": ["车辆识别代号", "VIN", "识别代号"],
        "住址": ["住址", "地址"],
        "发证单位": ["发证单位", "签发机关"],
        "品牌型号": ["品牌型号"],
        "车辆类型": ["车辆类型"],
        "所有人": ["所有人", "车主"],
        "使用性质": ["使用性质"],
        "发动机号码": ["发动机号码", "发动机号"],
    }
    for k, anchors in mapping.items():
        value, src = pick_after_anchor(texts, anchors)
        fields[k] = field(value, 0.84 if value else 0.0, src)

    for date_name, anchors in {"发证日期": ["发证日期"], "注册日期": ["注册日期"]}.items():
        value, src = pick_after_anchor(texts, anchors)
        dm = DATE_PATTERN.search(value)
        final = normalize_date(dm.group(0)) if dm else ""
        fields[date_name] = field(final, 0.82 if final else 0.0, src if final else "fallback_missing")

    validation = {
        "rules": {
            "车牌格式通过": plate_is_valid(plate),
            "发证日期合法": date_is_valid(fields["发证日期"]["value"]) if fields["发证日期"]["value"] else False,
            "注册日期合法": date_is_valid(fields["注册日期"]["value"]) if fields["注册日期"]["value"] else False,
        },
        "warnings": [],
    }
    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text
