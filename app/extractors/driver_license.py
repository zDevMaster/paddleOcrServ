from __future__ import annotations

import re

from app.extractors.common import field, line_texts, pick_after_anchor, sort_lines_by_layout
from app.validators import (
    DATE_PATTERN,
    IDCARD_PATTERN,
    date_is_valid,
    normalize_date,
    validate_idcard_number,
)

_LONG_TERM = "长期"
_VALIDITY_RANGE_RE = re.compile(
    r"(\d{4}[./-]?\d{1,2}[./-]?\d{1,2})\s*[至到\-—~]\s*(\d{4}[./-]?\d{1,2}[./-]?\d{1,2}|长期)"
)
_ADDRESS_MARKERS = ("省", "市", "区", "县", "镇", "乡", "村", "街", "路", "道", "巷", "号", "弄", "里", "室", "幢", "园", "栋")
_DL_STOP_LABELS = (
    "姓名",
    "性别",
    "国籍",
    "住址",
    "地址",
    "出生",
    "初次领证",
    "准驾车型",
    "有效期限",
    "证号",
    "档案编号",
    "记录",
)


def _extract_valid_date(line: str) -> str:
    dm = DATE_PATTERN.search(line)
    if not dm:
        return ""
    nd = normalize_date(dm.group(0))
    if not date_is_valid(nd):
        return ""
    year = int(nd[:4])
    if year < 1990 or year > 2035:
        return ""
    return nd


def _pick_validity_dates(texts: list[str]) -> tuple[str, str, str, str]:
    """解析有效期限：支持 ``YYYY-MM-DD至长期`` 与分行锚点。"""
    for line in texts:
        compact = line.replace(" ", "")
        if _LONG_TERM not in compact and "至" not in compact and "到" not in compact:
            continue
        m = _VALIDITY_RANGE_RE.search(line.replace(" ", ""))
        if m:
            start = normalize_date(m.group(1))
            end_raw = m.group(2)
            if end_raw == _LONG_TERM:
                if date_is_valid(start):
                    return start, _LONG_TERM, "regex:validity_range", "regex:validity_range"
            else:
                end = normalize_date(end_raw)
                if date_is_valid(start) and date_is_valid(end):
                    return start, end, "regex:validity_range", "regex:validity_range"
        if _LONG_TERM in line:
            start = _extract_valid_date(line)
            if start:
                return start, _LONG_TERM, "anchor_near:有效期限", "text:长期"
            for j, other in enumerate(texts):
                if other is line:
                    d = _extract_valid_date(texts[j - 1]) if j > 0 else ""
                    if d:
                        return d, _LONG_TERM, "anchor_near:有效期限", "text:长期"
    for idx, line in enumerate(texts):
        if "有效" not in line:
            continue
        for j in range(idx, min(idx + 4, len(texts))):
            if _LONG_TERM in texts[j]:
                start = _extract_valid_date(texts[j]) or _extract_valid_date(line)
                if not start and j > 0:
                    start = _extract_valid_date(texts[j - 1])
                if start:
                    return start, _LONG_TERM, "anchor_near:有效期限", "text:长期"
            end_d = _extract_valid_date(texts[j])
            if end_d and "有效" in line:
                start_d = _extract_valid_date(line) or ( _extract_valid_date(texts[idx - 1]) if idx > 0 else "")
                if start_d and start_d != end_d:
                    return start_d, end_d, "anchor_near:有效期限", "anchor_near:有效期限"
    return "", "", "fallback_missing", "fallback_missing"


def _looks_like_address(text: str) -> bool:
    if not text or len(text) < 4:
        return False
    if any(k in text for k in ("公安", "交通", "检验", "有效", "驾驶", "Vehicle", "证号")):
        return False
    return any(m in text for m in _ADDRESS_MARKERS)


def _pick_address(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in ("住址", "地址"):
            if anchor not in line and not line.startswith("址"):
                continue
            if anchor in line:
                right = line.split(anchor, 1)[-1].replace(":", "").replace("：", "").strip()
            elif line.startswith("址"):
                right = line[1:].strip(" :：")
            else:
                right = ""
            parts: list[str] = []
            if right and _looks_like_address(right):
                parts.append(right)
            for j in range(idx + 1, min(idx + 4, len(lines))):
                nxt = lines[j].strip()
                if nxt in _DL_STOP_LABELS or any(nxt.startswith(l) for l in _DL_STOP_LABELS):
                    break
                if nxt.startswith("址"):
                    nxt = nxt[1:].strip(" :：")
                if _looks_like_address(nxt):
                    parts.append(nxt)
            if parts:
                return "".join(parts), f"anchor:{anchor}"
    for line in lines:
        if line.startswith("址") and len(line) > 1:
            right = line[1:].strip(" :：")
            if _looks_like_address(right):
                return right, "anchor:址"
    return "", "fallback_missing"


def extract_driver_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    ordered = sort_lines_by_layout(lines)
    texts = line_texts(ordered)
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
        "国籍": ["国籍"],
        "准驾车型": ["准驾车型"],
        "性别": ["性别"],
        "发证单位": ["发证单位", "签发机关"],
    }
    for k, anchors in mapping.items():
        value, src = pick_after_anchor(texts, anchors)
        fields[k] = field(value, 0.86 if value else 0.0, src)

    addr, addr_src = _pick_address(texts)
    fields["住址"] = field(addr, 0.88 if addr else 0.0, addr_src)

    start, end, start_src, end_src = _pick_validity_dates(texts)
    if not start:
        value, src = pick_after_anchor(texts, ["有效期限", "有效期起", "起始日期"])
        start = _extract_valid_date(value)
        start_src = src if start else "fallback_missing"
    if not end:
        for line in texts:
            if _LONG_TERM in line:
                end = _LONG_TERM
                end_src = "text:长期"
                if not start:
                    start = _extract_valid_date(line)
                    if start:
                        start_src = "anchor_near:有效期限"
                break
        if not end:
            value, src = pick_after_anchor(texts, ["有效期止", "截止日期"])
            end = _extract_valid_date(value)
            end_src = src if end else "fallback_missing"

    fields["有效期开始"] = field(start, 0.86 if start else 0.0, start_src)
    fields["有效期结束"] = field(end, 0.86 if end else 0.0, end_src)

    for date_name, anchors in {
        "出生日期": ["出生日期", "出生"],
        "初次领证日期": ["初次领证日期", "初次领证"],
    }.items():
        value, src = pick_after_anchor(texts, anchors)
        dm = DATE_PATTERN.search(value)
        final = normalize_date(dm.group(0)) if dm else _extract_valid_date(value)
        fields[date_name] = field(final, 0.82 if final else 0.0, src if final else "fallback_missing")

    end_val = fields["有效期结束"]["value"]
    end_valid = end_val == _LONG_TERM or (date_is_valid(end_val) if end_val else False)
    validation = {
        "rules": {
            "证号格式疑似身份证": bool(id_no),
            "证号校验通过": validate_idcard_number(id_no) if id_no else False,
            "有效期开始合法": date_is_valid(fields["有效期开始"]["value"]) if fields["有效期开始"]["value"] else False,
            "有效期结束合法": end_valid,
        },
        "warnings": [],
    }
    if fields["有效期开始"]["value"] and fields["有效期结束"]["value"]:
        sv, ev = fields["有效期开始"]["value"], fields["有效期结束"]["value"]
        if ev != _LONG_TERM and sv > ev:
            validation["warnings"].append("有效期开始晚于结束")

    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text
