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

_FIELD_LABELS = ("公民身份号码", "身份证号", "姓名", "性别", "民族", "出生", "住址", "住所")
_NAME_INVALID = re.compile(r"公民|身份|号码|性别|民族|住址|出生|姓名")
_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fff·]{2,8}$")
_GENDER_ETHNICITY = re.compile(r"^(男|女)(?:民族(.+))?$")
_ETHNICITIES = (
    "汉",
    "回",
    "蒙古",
    "藏",
    "维吾尔",
    "苗",
    "彝",
    "壮",
    "布依",
    "朝鲜",
    "满",
    "侗",
    "瑶",
    "白",
    "土家",
    "哈尼",
    "哈萨克",
    "傣",
    "黎",
    "傈僳",
    "佤",
    "畲",
    "高山",
    "拉祜",
    "水",
    "东乡",
    "纳西",
    "景颇",
    "柯尔克孜",
    "土",
    "达斡尔",
    "仫佬",
    "羌",
    "布朗",
    "撒拉",
    "毛南",
    "仡佬",
    "锡伯",
    "阿昌",
    "普米",
    "塔吉克",
    "怒",
    "乌孜别克",
    "俄罗斯",
    "鄂温克",
    "德昂",
    "保安",
    "裕固",
    "京",
    "塔塔尔",
    "独龙",
    "鄂伦春",
    "赫哲",
    "门巴",
    "珞巴",
    "基诺",
)


def _split_gender_ethnicity(raw: str) -> tuple[str, str]:
    text = raw.replace(" ", "").strip()
    m = _GENDER_ETHNICITY.match(text)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    if text in ("男", "女"):
        return text, ""
    return text, ""


def _normalize_ethnicity(raw: str) -> str:
    text = raw.replace("民族", "").strip()
    if not text:
        return ""
    for eth in sorted(_ETHNICITIES, key=len, reverse=True):
        if text == eth or text.endswith(eth):
            return eth
    return text


def _is_stop_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    compact = stripped.replace(" ", "")
    if IDCARD_PATTERN.search(compact):
        return True
    for lbl in _FIELD_LABELS:
        if stripped == lbl or stripped.startswith(lbl):
            return True
    if DATE_PATTERN.search(compact) and any(k in stripped for k in ("出生", "年", "月", "日")):
        return True
    return False


def _is_address_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {"1", "I", "l", "|"}:
        return True
    return False


def _looks_like_address_tail(line: str) -> bool:
    if _is_stop_line(line) or _is_address_noise(line):
        return False
    markers = ("号", "组", "室", "幢", "栋", "村", "街", "路", "弄", "巷", "里", "委", "镇", "区", "县", "市", "省")
    if any(m in line for m in markers):
        return True
    return bool(re.search(r"\d", line))


def _append_address_tail(parts: list[str], lines: list[str]) -> list[str]:
    merged = list(parts)
    addr = "".join(merged)
    for line in lines:
        t = line.strip()
        if not _looks_like_address_tail(t):
            continue
        if t in merged or t in addr:
            continue
        if _NAME_PATTERN.match(t) and not any(m in t for m in ("号", "组", "村", "街", "路", "镇")):
            continue
        merged.append(t)
        addr = "".join(merged)
    return merged


def _pick_address(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in ("住址", "住所"):
            if anchor not in line:
                continue
            right = line.split(anchor, 1)[-1].replace(":", "").replace("：", "").strip()
            parts: list[str] = []
            if right and not _is_address_noise(right):
                parts.append(right)
            for j in range(idx + 1, len(lines)):
                nxt = lines[j].strip()
                if _is_address_noise(nxt):
                    continue
                if _is_stop_line(nxt):
                    break
                parts.append(nxt)
                if len(parts) >= 4:
                    break
            parts = _append_address_tail(parts, lines)
            if parts:
                return "".join(parts), f"anchor:{anchor}"
    return "", "fallback_missing"


def _pick_name(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        if "姓名" not in line:
            continue
        right = line.split("姓名", 1)[-1].replace(":", "").replace("：", "").strip()
        if right and not _NAME_INVALID.search(right) and _NAME_PATTERN.match(right):
            return right, "anchor:姓名"
        for j in range(idx + 1, min(idx + 4, len(lines))):
            nxt = lines[j].strip()
            if _is_stop_line(nxt):
                continue
            if _NAME_PATTERN.match(nxt) and not _NAME_INVALID.search(nxt):
                return nxt, "anchor_next:姓名"
    for line in lines:
        t = line.strip()
        if _NAME_PATTERN.match(t) and not _NAME_INVALID.search(t):
            return t, "heuristic:name_line"
    return "", "fallback_missing"


def idcard_result_score(fields: dict[str, dict]) -> int:
    score = 0
    if fields.get("身份证号", {}).get("value"):
        score += 4
    name = fields.get("姓名", {}).get("value", "")
    if name and not _NAME_INVALID.search(name):
        score += 3
    addr = fields.get("住址", {}).get("value", "")
    if addr:
        score += 2 + (1 if len(addr) >= 12 else 0)
    if fields.get("性别", {}).get("value") in ("男", "女"):
        score += 1
    if fields.get("民族", {}).get("value"):
        score += 1
    if fields.get("出生", {}).get("value"):
        score += 1
    return score


def extract_idcard(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
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
    source = "regex:idcard" if id_no else "fallback_missing"
    fields["身份证号"] = field(id_no, 0.98 if id_no else 0.0, source)

    name, name_src = _pick_name(texts)
    fields["姓名"] = field(name, 0.9 if name else 0.0, name_src)

    gender_raw, gender_src = pick_after_anchor(texts, ["性别"])
    gender, ethnic_from_gender = _split_gender_ethnicity(gender_raw)
    fields["性别"] = field(gender, 0.9 if gender in ("男", "女") else 0.0, gender_src)

    ethnic_raw, ethnic_src = pick_after_anchor(texts, ["民族"])
    ethnic = _normalize_ethnicity(ethnic_raw or ethnic_from_gender)
    if ethnic:
        ethnic_src = ethnic_src if ethnic_raw else "split:性别"
    fields["民族"] = field(ethnic, 0.88 if ethnic else 0.0, ethnic_src if ethnic else "fallback_missing")

    addr, addr_src = _pick_address(texts)
    fields["住址"] = field(addr, 0.88 if addr else 0.0, addr_src)

    birth = ""
    if id_no and len(id_no) == 18:
        birth = f"{id_no[6:10]}-{id_no[10:12]}-{id_no[12:14]}"
    if not birth:
        for line in texts:
            m = DATE_PATTERN.search(line)
            if m:
                birth = normalize_date(m.group(0))
                break
    fields["出生"] = field(birth, 0.9 if birth else 0.0, "idcard_or_regex" if birth else "fallback_missing")

    validation = {
        "rules": {
            "idcard_checksum_pass": validate_idcard_number(id_no),
            "birth_date_valid": date_is_valid(birth) if birth else False,
        },
        "warnings": [],
    }
    if id_no and not validation["rules"]["idcard_checksum_pass"]:
        validation["warnings"].append("身份证校验位未通过")
    if gender_raw and gender not in ("男", "女"):
        validation["warnings"].append("性别字段需人工核对")

    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text
