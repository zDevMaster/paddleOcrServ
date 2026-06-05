from __future__ import annotations

import re
import unicodedata

from app.extractors.common import field

_NOISE_HANDWRITING = re.compile(r"^[?？。，、·…\s]+$")


def _strip_latin_letters_and_symbols(s: str) -> str:
    """手写签名：去掉拉丁字母（含全角英文）、数字、各类标点、符号、空白分隔符；保留汉字（含扩展 B/C 等 Lo 类）。"""
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            continue
        if "0" <= ch <= "9":
            continue
        if 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
            continue
        if 0xFF10 <= o <= 0xFF19:
            continue
        cat = unicodedata.category(ch)
        if cat[0] in "PSZ":
            continue
        if cat[0] == "N":
            continue
        if cat in ("Lu", "Ll", "Lt", "Lm"):
            continue
        out.append(ch)
    return "".join(out)


def _is_handwriting_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if len(t) == 1 and t in "?？。，、·+＋*…":
        return True
    if _NOISE_HANDWRITING.fullmatch(t):
        return True
    return False


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
    full_text = "".join(texts)
    mean_score = float(sum(scores) / len(scores)) if texts else 0.0
    rounded = round(mean_score, 4)
    fields = {
        "全文": field(full_text, mean_score, "ocr_concat"),
        "行文本": field(texts, mean_score, "ocr_lines"),
        "置信度": field(rounded, mean_score, "ocr_mean"),
    }
    validation = {"rules": {"has_text": bool(texts)}, "warnings": []}
    missing = [k for k, v in fields.items() if not v["value"]]
    return fields, validation, missing, full_text
