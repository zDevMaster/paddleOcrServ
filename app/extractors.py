from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.models import DocumentType
from app.validators import (
    DATE_PATTERN,
    IDCARD_PATTERN,
    PLATE_PATTERN,
    date_is_valid,
    normalize_date,
    plate_is_valid,
    validate_idcard_number,
)


def _line_texts(lines: list[dict]) -> list[str]:
    return [str(x.get("text", "")).strip() for x in lines if str(x.get("text", "")).strip()]


_NOISE_HANDWRITING = re.compile(r"^[?？。，、·…\s]+$")


def _strip_latin_letters_and_symbols(s: str) -> str:
    """手写签名：去掉拉丁字母（含全角英文）及各类标点、符号、空白分隔符；保留汉字（含扩展 B/C 等 Lo 类）、数字等。

    采用「删除拉丁与符号」而非「仅保留 BMP 汉字码段」，避免生僻字、扩展区汉字被误删导致「两字只出一字」。
    """
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        # ASCII 英文
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            continue
        # 全角英文 A-Za-z
        if 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
            continue
        cat = unicodedata.category(ch)
        # 标点、符号、各类空白/换行分隔
        if cat[0] in "PSZ":
            continue
        # Lu/Ll/Lt/Lm：拉丁、西里尔等字母表字母（汉字为 Lo，不会误删）
        if cat in ("Lu", "Ll", "Lt", "Lm"):
            continue
        out.append(ch)
    return "".join(out)


def _is_handwriting_noise(text: str) -> bool:
    """滤掉检测/识别产生的孤立标点或噪声（如单独一行「?」）。"""
    t = text.strip()
    if not t:
        return True
    if len(t) == 1 and t in "?？。，、·+＋*…":
        return True
    if _NOISE_HANDWRITING.fullmatch(t):
        return True
    return False


def _pick_after_anchor(lines: list[str], anchors: Iterable[str]) -> tuple[str, str]:
    for idx, line in enumerate(lines):
        for anchor in anchors:
            if anchor in line:
                right = line.split(anchor, 1)[-1].replace(":", "").replace("：", "").strip()
                if right:
                    return right, f"anchor:{anchor}"
                if idx + 1 < len(lines):
                    nxt = lines[idx + 1].strip()
                    if nxt:
                        return nxt, f"anchor_next:{anchor}"
    return "", "fallback_missing"


def _field(value: str, confidence: float, source: str) -> dict:
    return {"value": value, "confidence": confidence, "source": source}


def extract_handwriting(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts: list[str] = []
    scores: list[float] = []
    for x in lines:
        raw = str(x.get("text", "")).strip()
        t = _strip_latin_letters_and_symbols(raw)
        if not t or _is_handwriting_noise(t):
            continue
        texts.append(t)
        scores.append(float(x.get("score", 0.0)))
    if not scores:
        scores = [0.0]
    # 手写签名多为单行连写，用无分隔拼接，避免出现「张\n三」或尾部「\n?」类噪声
    full_text = "".join(texts)
    mean_score = float(sum(scores) / len(scores)) if texts else 0.0
    rounded = round(mean_score, 4)
    fields = {
        "全文": _field(full_text, mean_score, "ocr_concat"),
        "行文本": _field(texts, mean_score, "ocr_lines"),
        "置信度": _field(rounded, mean_score, "ocr_mean"),
    }
    validation = {"rules": {"has_text": bool(texts)}, "warnings": []}
    missing = [k for k, v in fields.items() if not v["value"]]
    return fields, validation, missing, full_text


def extract_idcard(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts = _line_texts(lines)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    id_no = ""
    for line in texts:
        m = IDCARD_PATTERN.search(line.replace(" ", ""))
        if m:
            id_no = m.group(0).upper()
            break
    source = "regex:idcard" if id_no else "fallback_missing"
    fields["身份证号"] = _field(id_no, 0.98 if id_no else 0.0, source)

    for name, anchors in {
        "姓名": ["姓名"],
        "住址": ["住址", "住所"],
        "性别": ["性别"],
        "民族": ["民族"],
    }.items():
        value, src = _pick_after_anchor(texts, anchors)
        fields[name] = _field(value, 0.88 if value else 0.0, src)

    birth = ""
    if id_no and len(id_no) == 18:
        birth = f"{id_no[6:10]}-{id_no[10:12]}-{id_no[12:14]}"
    if not birth:
        for line in texts:
            m = DATE_PATTERN.search(line)
            if m:
                birth = normalize_date(m.group(0))
                break
    fields["出生"] = _field(birth, 0.9 if birth else 0.0, "idcard_or_regex" if birth else "fallback_missing")

    validation = {
        "rules": {
            "idcard_checksum_pass": validate_idcard_number(id_no),
            "birth_date_valid": date_is_valid(birth) if birth else False,
        },
        "warnings": [],
    }
    if id_no and not validation["rules"]["idcard_checksum_pass"]:
        validation["warnings"].append("身份证校验位未通过")

    missing = [k for k, v in fields.items() if v["value"] in ("", None, [])]
    return fields, validation, missing, all_text


def extract_driver_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts = _line_texts(lines)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    id_no = ""
    for line in texts:
        m = IDCARD_PATTERN.search(line.replace(" ", ""))
        if m:
            id_no = m.group(0).upper()
            break
    fields["证号"] = _field(id_no, 0.95 if id_no else 0.0, "regex:idcard" if id_no else "fallback_missing")

    mapping = {
        "姓名": ["姓名"],
        "住址": ["住址", "地址"],
        "国籍": ["国籍"],
        "准驾车型": ["准驾车型"],
        "性别": ["性别"],
        "发证单位": ["发证单位", "签发机关"],
    }
    for k, anchors in mapping.items():
        value, src = _pick_after_anchor(texts, anchors)
        fields[k] = _field(value, 0.86 if value else 0.0, src)

    date_fields = {
        "出生日期": ["出生日期", "出生"],
        "初次领证日期": ["初次领证日期", "初次领证"],
        "有效期开始": ["有效期限", "有效期起", "起始日期"],
        "有效期结束": ["有效期限", "有效期止", "截止日期"],
    }
    for k, anchors in date_fields.items():
        value, src = _pick_after_anchor(texts, anchors)
        dm = DATE_PATTERN.search(value)
        final = normalize_date(dm.group(0)) if dm else ""
        fields[k] = _field(final, 0.82 if final else 0.0, src if final else "fallback_missing")

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


def extract_vehicle_license(lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    texts = _line_texts(lines)
    all_text = "\n".join(texts)
    fields: dict[str, dict] = {}

    plate = ""
    for line in texts:
        m = PLATE_PATTERN.search(line.replace(" ", "").upper())
        if m:
            plate = m.group(0)
            break
    fields["车牌号"] = _field(plate, 0.96 if plate else 0.0, "regex:plate" if plate else "fallback_missing")

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
        value, src = _pick_after_anchor(texts, anchors)
        fields[k] = _field(value, 0.84 if value else 0.0, src)

    for date_name, anchors in {"发证日期": ["发证日期"], "注册日期": ["注册日期"]}.items():
        value, src = _pick_after_anchor(texts, anchors)
        dm = DATE_PATTERN.search(value)
        final = normalize_date(dm.group(0)) if dm else ""
        fields[date_name] = _field(final, 0.82 if final else 0.0, src if final else "fallback_missing")

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


def extract_by_doc_type(doc_type: DocumentType, lines: list[dict]) -> tuple[dict, dict, list[str], str]:
    if doc_type == DocumentType.idcard:
        return extract_idcard(lines)
    if doc_type == DocumentType.driver_license:
        return extract_driver_license(lines)
    if doc_type == DocumentType.vehicle_license:
        return extract_vehicle_license(lines)
    return extract_handwriting(lines)

