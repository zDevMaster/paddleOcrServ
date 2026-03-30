from __future__ import annotations

import argparse
from pathlib import Path

from paddlex.utils.download import download_and_extract


PADDLEX_VERSION = "paddle3.0.0"
PADDLEX_BASE = (
    f"https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model"
    f"/{PADDLEX_VERSION}"
)

# 与 app/ocr_engine.py 默认目录一致；包内包含 inference.yml，适配 PaddleOCR 3.x / PaddleX
MODEL_PACKS: list[tuple[str, str]] = [
    ("PP-OCRv4_mobile_det_infer", f"{PADDLEX_BASE}/PP-OCRv4_mobile_det_infer.tar"),
    ("PP-OCRv4_mobile_rec_infer", f"{PADDLEX_BASE}/PP-OCRv4_mobile_rec_infer.tar"),
]


def download_pack(name: str, url: str, output_dir: Path, *, overwrite: bool) -> None:
    target_dir = output_dir / name
    if target_dir.exists() and not overwrite:
        print(f"skip existing: {target_dir}")
        return
    print(f"downloading {name} ...")
    download_and_extract(url, str(output_dir), name, overwrite=overwrite)


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 PaddleX 推理包（含 inference.yml）到 offline_bundle/models")
    parser.add_argument("--output", required=True, help="models 输出目录，例如 offline_bundle/models")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的模型目录",
    )
    args = parser.parse_args()

    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_PACKS:
        download_pack(name, url, out, overwrite=args.overwrite)
    print("all model packs ready")


if __name__ == "__main__":
    main()
