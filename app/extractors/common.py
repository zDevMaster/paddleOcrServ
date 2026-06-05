from __future__ import annotations

from collections.abc import Iterable


def line_texts(lines: list[dict]) -> list[str]:
    return [str(x.get("text", "")).strip() for x in lines if str(x.get("text", "")).strip()]


def pick_after_anchor(lines: list[str], anchors: Iterable[str]) -> tuple[str, str]:
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


def field(value: str, confidence: float, source: str) -> dict:
    return {"value": value, "confidence": confidence, "source": source}


def sort_lines_by_layout(lines: list[dict]) -> list[dict]:
    def sort_key(item: dict) -> tuple[float, float]:
        bbox = item.get("bbox") or []
        if bbox:
            ys = [float(p[1]) for p in bbox]
            xs = [float(p[0]) for p in bbox]
            return (min(ys), min(xs))
        return (1e9, 1e9)

    return sorted(lines, key=sort_key)
