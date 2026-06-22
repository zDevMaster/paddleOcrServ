from __future__ import annotations

import re

from app.extractors.common import field, line_texts, pick_after_anchor, sort_lines_by_layout
from app.validators import (
    DATE_PATTERN,
    PLATE_PATTERN,
    date_is_valid,
    normalize_date,
    plate_is_valid,
)

# --- 品牌型号 ---
_BRAND_MODEL_RE = re.compile(r"[\u4e00-\u9fff]{1,10}牌[A-Z0-9][A-Z0-9a-z\-：:.]{2,}")
_BRAND_MODEL_ANCHORS = ("品牌型号", "做型号", "牌州号", "福牌州号", "CTModel", "Model")
_INVALID_BRAND_VALUES = frozenset(
    {
        "货运",
        "非营运",
        "营运",
        "其它",
        "其他",
        "品牌型号",
        "做型号",
        "牌州号",
        "福牌州号",
        "Mode",
        "Model",
    }
)
_VEHICLE_TYPE_KEYWORDS = ("重型", "半挂", "牵引", "货车", "客车", "微型", "小型", "中型", "轻型", "栏板")
_USE_CHARACTER_KEYWORDS = ("货运", "非营运", "营运", "危化", "教练", "警用")

# --- VIN / 发动机 ---
_VIN_RE_STRICT = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
_VIN_RE_LOOSE = re.compile(r"[A-Z0-9]{17}")
_VIN_LABELS = frozenset({"VIN", "VIN.", "车辆识别代号", "识别代号", "VEHICE", "VEHICLE"})
_ENGINE_SKIP = ("检验", "有效期", "Engine", "发动机", "号码", "No", "柴油", "IND")

# --- 住址 / 所有人 / 发证单位 ---
_ADDRESS_MARKERS = ("省", "市", "区", "县", "镇", "乡", "村", "街", "路", "道", "巷", "号", "弄", "里", "室", "幢", "园", "栋")
_ADDRESS_NOISE = frozenset({"住", "址", "Address", "Add", "255", "333", "Owner", "Use", "Model", "VIN"})
_OWNER_PREFIX_RE = re.compile(r"^(?:所?有人|Owner|所人|人)")
_OWNER_COMPANY_RE = re.compile(r"[\u4e00-\u9fff]{2,50}(?:有限公司|有限责任公司|集团|合作社)")
_OWNER_PERSON_RE = re.compile(r"^[\u4e00-\u9fff·]{2,4}$")
_OWNER_INVALID = ("中华人民共和国", "机动车", "行驶证", "Vehicle", "License", "核定", "检验", "Plate", "档案", "号码")

_VL_STOP_LABELS = (
    "号牌号码",
    "车辆类型",
    "所有人",
    "住址",
    "地址",
    "使用性质",
    "品牌型号",
    "车辆识别代号",
    "发动机号码",
    "注册日期",
    "发证日期",
    "档案编号",
    "Plate",
    "Owner",
    "Address",
    "Model",
    "Engine",
    "VIN",
    "RegisterDate",
    "Issue Date",
    "IssueDate",
)

_DATE_ANCHOR_ISSUE = ("发证日期", "发证扫期", "发证目期", "注明日期", "Issue Date", "IssueDate", "Tssue Date")
_DATE_ANCHOR_REGISTER = ("注册日期", "RegisterDate", "RegisterDale", "RegislerDate")


def _extract_brand_token(line: str) -> str:
    text = line.replace(" ", "").strip()
    for anchor in _BRAND_MODEL_ANCHORS:
        if anchor in text:
            text = text.split(anchor, 1)[-1].strip(" :：")
    m = _BRAND_MODEL_RE.search(text)
    if not m:
        return ""
    return m.group(0).replace("：", "").replace(":", "").strip()


def _is_valid_brand_model(value: str) -> bool:
    if not value or value in _INVALID_BRAND_VALUES:
        return False
    if any(k in value for k in _VEHICLE_TYPE_KEYWORDS):
        return False
    if value in _USE_CHARACTER_KEYWORDS:
        return False
    return bool(_BRAND_MODEL_RE.search(value.replace(" ", "")))


def _pick_brand_model(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in _BRAND_MODEL_ANCHORS:
            if anchor not in line:
                continue
            same = _extract_brand_token(line)
            if _is_valid_brand_model(same):
                return same, f"anchor:{anchor}"
            for j in range(idx + 1, min(idx + 6, len(lines))):
                nxt = lines[j].strip()
                if nxt in _USE_CHARACTER_KEYWORDS:
                    continue
                cand = _extract_brand_token(nxt)
                if _is_valid_brand_model(cand):
                    return cand, f"anchor_next:{anchor}"
    for line in lines:
        cand = _extract_brand_token(line)
        if _is_valid_brand_model(cand):
            return cand, "heuristic:brand_pattern"
    return "", "fallback_missing"


def _extract_vin_token(line: str) -> str:
    compact = re.sub(r"\s+", "", line.upper())
    if compact in _VIN_LABELS or compact == "VIN":
        return ""
    m = _VIN_RE_STRICT.search(compact)
    if m:
        return m.group(0)
    m = _VIN_RE_LOOSE.search(compact)
    if m and re.search(r"[A-Z]", m.group(0)) and re.search(r"\d", m.group(0)):
        return m.group(0)
    # OCR 偶发 16 位 VIN，仍含字母数字混合时采纳
    m16 = re.search(r"[A-HJ-NPR-Z0-9]{16}", compact)
    if m16 and re.search(r"[A-Z]", m16.group(0)) and re.search(r"\d", m16.group(0)):
        return m16.group(0)
    return ""


def _pick_vin(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in ("车辆识别代号", "VIN", "识别代号"):
            if anchor not in line:
                continue
            same = _extract_vin_token(line)
            if same:
                return same, f"anchor:{anchor}"
            for j in range(idx + 1, min(idx + 5, len(lines))):
                cand = _extract_vin_token(lines[j])
                if cand:
                    return cand, f"anchor_next:{anchor}"
    for line in lines:
        cand = _extract_vin_token(line)
        if cand:
            return cand, "heuristic:vin"
    return "", "fallback_missing"


def _is_vl_stop_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in _ADDRESS_NOISE:
        return True
    for lbl in _VL_STOP_LABELS:
        if stripped == lbl or stripped.startswith(lbl):
            return True
    if PLATE_PATTERN.search(stripped.replace(" ", "").upper()):
        return True
    if _BRAND_MODEL_RE.search(stripped.replace(" ", "")):
        return True
    return False


def _looks_like_address(text: str) -> bool:
    if not text or text in _ADDRESS_NOISE:
        return False
    if "号牌" in text or text in ("号牌号码", "Plate No.", "PlateNo."):
        return False
    if any(k in text for k in ("公安", "交通", "检验", "有效期", "Vehicle", "Plate", "Owner")):
        return False
    if "号" in text and not any(m in text for m in ("省", "市", "县", "区", "路", "街", "村", "镇", "乡", "道", "巷", "室", "幢", "园")):
        return False
    return any(m in text for m in _ADDRESS_MARKERS)


def _pick_vehicle_address(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in ("住址", "地址"):
            if anchor not in line and not (anchor == "地址" and "地址" in line):
                continue
            if anchor in line:
                right = line.split(anchor, 1)[-1].replace(":", "").replace("：", "").strip()
            else:
                right = ""
            parts: list[str] = []
            if right and _looks_like_address(right):
                parts.append(right)
            for j in range(idx + 1, min(idx + 5, len(lines))):
                nxt = lines[j].strip()
                if nxt in _ADDRESS_NOISE:
                    continue
                if nxt.startswith("址") and len(nxt) > 1:
                    nxt = nxt[1:].strip(" :：")
                if _is_vl_stop_line(nxt) and not _looks_like_address(nxt):
                    break
                if _looks_like_address(nxt):
                    parts.append(nxt)
            if parts:
                return "".join(parts), f"anchor:{anchor}"
        if line.startswith("址") and len(line) > 1:
            right = line[1:].strip(" :：")
            if _looks_like_address(right):
                return right, "anchor:址"
    for line in lines:
        t = line.strip()
        if t.startswith("址") and len(t) > 1:
            right = t[1:].strip(" :：")
            if _looks_like_address(right):
                return right, "heuristic:address_line"
        if _looks_like_address(t) and "公司" not in t:
            return t, "heuristic:address_line"
    return "", "fallback_missing"


def _is_authority_part(text: str) -> bool:
    if not text or any(k in text for k in ("检验", "有效期", "柴油", "Register", "Issue", "公司", "有限")):
        return False
    return any(k in text for k in ("公安局", "交通", "警察", "支队", "管理所"))


def _is_authority_prefix(text: str) -> bool:
    return 2 <= len(text) <= 14 and ("省" in text or "市" in text) and "公司" not in text


def _pick_issuing_authority(lines: list[str]) -> tuple[str, str]:
    parts: list[str] = []
    for line in lines:
        t = line.strip()
        if "公司" in t or "检验" in t or "有效期" in t:
            continue
        if _is_authority_prefix(t) or _is_authority_part(t):
            if t not in parts:
                parts.append(t)
    if parts:
        return "".join(parts), "heuristic:authority"
    return "", "fallback_missing"


def _normalize_owner(text: str) -> str:
    t = text.strip()
    t = _OWNER_PREFIX_RE.sub("", t)
    if t.startswith("有人"):
        t = t[2:]
    return t.strip(" :：")


def _is_valid_owner(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    if any(k in value for k in _OWNER_INVALID):
        return False
    if any(k in value for k in ("公安", "交通", "检验", "有效期", "Plate", "Vehicle")):
        return False
    if _OWNER_COMPANY_RE.search(value):
        return True
    if _OWNER_PERSON_RE.match(value):
        return True
    return False


def _pick_owner(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        if "所有人" in line or "车主" in line:
            key = "所有人" if "所有人" in line else "车主"
            right = _normalize_owner(line.split(key, 1)[-1])
            if _is_valid_owner(right):
                return right, f"anchor:{key}"
            for j in range(idx + 1, min(idx + 6, len(lines))):
                cand = _normalize_owner(lines[j])
                if _is_valid_owner(cand):
                    return cand, f"anchor_next:{key}"
        if line.strip() in ("所有", "人", "Owner") and idx + 1 < len(lines):
            cand = _normalize_owner(lines[idx + 1])
            if _is_valid_owner(cand):
                return cand, "anchor_next:所有人"
    for line in lines:
        t = line.strip()
        if t.startswith("人") and len(t) > 1:
            cand = _normalize_owner(t)
            if _is_valid_owner(cand):
                return cand, "heuristic:owner_line"
        if t.startswith("所人") or t.startswith("有人"):
            cand = _normalize_owner(t)
            if _is_valid_owner(cand):
                return cand, "heuristic:owner_line"
        m = _OWNER_COMPANY_RE.search(t)
        if m and _is_valid_owner(m.group(0)):
            return m.group(0), "heuristic:company"
    return "", "fallback_missing"


def _extract_engine_token(line: str) -> str:
    if any(k in line for k in _ENGINE_SKIP):
        if "检验" in line or "有效期" in line:
            return ""
    compact = re.sub(r"\s+", "", line.upper())
    for token in re.findall(r"[A-Z0-9]{6,12}", compact):
        if token in _VIN_LABELS:
            continue
        if re.search(r"[A-Z]", token) and re.search(r"\d", token):
            return token
        if len(token) >= 7 and token.isdigit():
            return token
    return ""


def _pick_engine_number(lines: list[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in ("发动机号码", "发动机号", "Engine No", "Engine"):
            if anchor not in line and anchor.replace(" ", "") not in line.replace(" ", ""):
                continue
            same = _extract_engine_token(line)
            if same:
                return same, f"anchor:{anchor}"
            for j in range(idx + 1, min(idx + 5, len(lines))):
                if "检验" in lines[j] or "有效期" in lines[j]:
                    continue
                cand = _extract_engine_token(lines[j])
                if cand:
                    return cand, f"anchor_next:{anchor}"
    for line in lines:
        cand = _extract_engine_token(line)
        if cand:
            return cand, "heuristic:engine"
    return "", "fallback_missing"


def _is_date_label_line(line: str) -> bool:
    stripped = line.strip()
    labels = _DATE_ANCHOR_ISSUE + _DATE_ANCHOR_REGISTER + ("注册日期", "发证日期", "Issue Date", "RegisterDate")
    return stripped in labels


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


def _pick_date_near_anchor(lines: list[str], anchors: tuple[str, ...]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in anchors:
            if anchor not in line and anchor.lower() not in line.lower():
                continue
            for j in range(idx, min(idx + 5, len(lines))):
                if _is_date_label_line(lines[j]) and j == idx:
                    continue
                d = _extract_valid_date(lines[j])
                if d:
                    return d, f"anchor_near:{anchor}"
    return "", "fallback_missing"


def _pick_vehicle_dates(lines: list[str]) -> tuple[str, str, str, str]:
    register, reg_src = _pick_date_near_anchor(lines, _DATE_ANCHOR_REGISTER)
    issue, issue_src = _pick_date_near_anchor(lines, _DATE_ANCHOR_ISSUE)

    all_dates: list[str] = []
    for line in lines:
        d = _extract_valid_date(line)
        if d and d not in all_dates:
            all_dates.append(d)

    if not register and all_dates:
        register, reg_src = sorted(all_dates)[0], "heuristic:date_earliest"
    if not issue and len(all_dates) >= 2:
        issue, issue_src = sorted(all_dates)[-1], "heuristic:date_latest"
    elif not issue and all_dates:
        issue, issue_src = all_dates[0], "heuristic:date_only"

    return register, reg_src, issue, issue_src


def extract_vehicle_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    ordered = sort_lines_by_layout(lines)
    texts = line_texts(ordered)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    plate = ""
    for line in texts:
        m = PLATE_PATTERN.search(line.replace(" ", "").upper())
        if m:
            plate = m.group(0)
            break
    fields["车牌号"] = field(plate, 0.96 if plate else 0.0, "regex:plate" if plate else "fallback_missing")

    brand, brand_src = _pick_brand_model(texts)
    fields["品牌型号"] = field(brand, 0.9 if brand else 0.0, brand_src)

    vin, vin_src = _pick_vin(texts)
    fields["车辆识别代号"] = field(vin, 0.92 if vin else 0.0, vin_src)

    addr, addr_src = _pick_vehicle_address(texts)
    fields["住址"] = field(addr, 0.88 if addr else 0.0, addr_src)

    authority, auth_src = _pick_issuing_authority(texts)
    fields["发证单位"] = field(authority, 0.86 if authority else 0.0, auth_src)

    owner, owner_src = _pick_owner(texts)
    fields["所有人"] = field(owner, 0.88 if owner else 0.0, owner_src)

    engine, engine_src = _pick_engine_number(texts)
    fields["发动机号码"] = field(engine, 0.9 if engine else 0.0, engine_src)

    register, reg_src, issue, issue_src = _pick_vehicle_dates(texts)
    fields["注册日期"] = field(register, 0.84 if register else 0.0, reg_src)
    fields["发证日期"] = field(issue, 0.84 if issue else 0.0, issue_src)

    for k, anchors in {
        "车辆类型": ["车辆类型"],
        "使用性质": ["使用性质"],
    }.items():
        value, src = pick_after_anchor(texts, anchors)
        fields[k] = field(value, 0.84 if value else 0.0, src)

    validation = {
        "rules": {
            "车牌格式通过": plate_is_valid(plate),
            "品牌型号已识别": bool(brand),
            "VIN已识别": bool(vin),
            "发证日期合法": date_is_valid(issue) if issue else False,
            "注册日期合法": date_is_valid(register) if register else False,
        },
        "warnings": [],
    }
    for label, val in (
        ("品牌型号", brand),
        ("车辆识别代号", vin),
        ("住址", addr),
        ("发证单位", authority),
        ("所有人", owner),
        ("发动机号码", engine),
    ):
        if not val:
            validation["warnings"].append(f"{label}未识别，建议人工核对")

    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text
