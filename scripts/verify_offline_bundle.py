from __future__ import annotations

"""校验 offline_bundle：锁定清单能否仅靠本地 wheel 离线安装，以及 OCR 模型文件是否齐全。"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "offline_bundle/wheels/requirements-lock.txt"
WHEELS = ROOT / "offline_bundle/wheels"
PADDLE = ROOT / "offline_bundle/paddle"
MODEL_ROOT = ROOT / "offline_bundle/models"

MODEL_DIRS = (
    "ch_PP-OCRv4_det_infer",
    "ch_PP-OCRv4_rec_infer",
    "ch_ppocr_mobile_v2.0_cls_infer",
)


def verify_models() -> list[str]:
    errors: list[str] = []
    for name in MODEL_DIRS:
        d = MODEL_ROOT / name
        for fn in ("inference.pdmodel", "inference.pdiparams"):
            p = d / fn
            if not p.is_file():
                errors.append(f"模型缺失: {p.relative_to(ROOT)}")
    return errors


def verify_wheels(pyexe: Path) -> tuple[int, str]:
    """用 pip --dry-run --ignore-installed 验证仅本地 wheel 即可满足锁定清单。"""
    cmd = [
        str(pyexe),
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(WHEELS),
        "--find-links",
        str(PADDLE),
        "-r",
        str(LOCK),
        "--dry-run",
        "--ignore-installed",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="用于运行 pip 的 Python（默认当前解释器）",
    )
    args = parser.parse_args()
    py = Path(args.python)

    if not LOCK.is_file():
        print(f"缺少锁定文件: {LOCK}", file=sys.stderr)
        return 2

    me = verify_models()
    for e in me:
        print(e, file=sys.stderr)

    code, log = verify_wheels(py)
    if code != 0:
        print("pip 离线解析失败（请在外网执行 scripts/prepare_offline_assets.ps1 补全 wheel）:", file=sys.stderr)
        print(log[-8000:], file=sys.stderr)
        return 1

    if me:
        return 1

    print("offline_bundle 校验通过：模型文件齐全，requirements-lock.txt 可由本地 wheels + paddle 离线满足。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
