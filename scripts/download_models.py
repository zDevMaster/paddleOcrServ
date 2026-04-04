from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


MODEL_URLS = {
    "ch_PP-OCRv4_det_infer": "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar",
    "ch_PP-OCRv4_rec_infer": "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar",
    "ch_ppocr_mobile_v2.0_cls_infer": "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar",
}


def _model_is_complete(target_dir: Path) -> bool:
    """至少包含推理所需的 pdmodel 与 pdiparams（避免仅存在占位文件时误跳过）。"""
    if not target_dir.is_dir():
        return False
    return (target_dir / "inference.pdmodel").is_file() and (target_dir / "inference.pdiparams").is_file()


def download_and_extract(name: str, url: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_dir = output_dir / name
    if _model_is_complete(target_dir):
        print(f"skip existing: {target_dir}")
        return
    if target_dir.exists():
        print(f"incomplete or stale, removing: {target_dir}")
        shutil.rmtree(target_dir)

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / f"{name}.tar"
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, tar_path)
        with tarfile.open(tar_path, "r") as tf:
            tf.extractall(path=tmp)
        extracted = Path(tmp) / name
        if not extracted.exists():
            # 兜底：处理 tar 内目录名不一致情况
            dirs = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if not dirs:
                raise RuntimeError(f"cannot locate extracted directory for {name}")
            extracted = dirs[0]
        shutil.move(str(extracted), str(target_dir))
        print(f"saved: {target_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="models output directory")
    args = parser.parse_args()

    out = Path(args.output).resolve()
    for n, u in MODEL_URLS.items():
        download_and_extract(n, u, out)
    print("all models downloaded")


if __name__ == "__main__":
    main()

