from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# PaddleOCR 3.x / PaddleX 需使用「含 inference.yml」的官方推理包（非旧版仅 pdmodel 的 tar）
# 见：https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/utils/official_models.py
_BOS_BASE = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
)

# 键：解压后目录名（与 tar 内顶层目录一致）；值：文件名
# 含 v4/v5 mobile 与 v5 server，供 startupV4m.bat / startupv5m.bat / startupv5s.bat 选用
MODEL_TARS = {
    "PP-OCRv4_mobile_det_infer": "PP-OCRv4_mobile_det_infer.tar",
    "PP-OCRv4_mobile_rec_infer": "PP-OCRv4_mobile_rec_infer.tar",
    "PP-OCRv5_mobile_det_infer": "PP-OCRv5_mobile_det_infer.tar",
    "PP-OCRv5_mobile_rec_infer": "PP-OCRv5_mobile_rec_infer.tar",
    "PP-OCRv5_server_det_infer": "PP-OCRv5_server_det_infer.tar",
    "PP-OCRv5_server_rec_infer": "PP-OCRv5_server_rec_infer.tar",
}


def _paddlex_model_complete(target_dir: Path) -> bool:
    if not target_dir.is_dir():
        return False
    return (
        (target_dir / "inference.yml").is_file()
        and (target_dir / "inference.pdiparams").is_file()
        and (target_dir / "inference.json").is_file()
    )


def download_and_extract(folder_name: str, tar_filename: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_dir = output_dir / folder_name
    if _paddlex_model_complete(target_dir):
        print(f"skip existing: {target_dir}")
        return
    if target_dir.exists():
        print(f"incomplete or stale, removing: {target_dir}")
        shutil.rmtree(target_dir)

    url = f"{_BOS_BASE}/{tar_filename}"
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / tar_filename
        print(f"downloading {tar_filename} ...")
        urllib.request.urlretrieve(url, tar_path)
        with tarfile.open(tar_path, "r:*") as tf:
            tf.extractall(path=tmp)
        extracted = Path(tmp) / folder_name
        if not extracted.is_dir():
            subdirs = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if not subdirs:
                raise RuntimeError(f"empty archive: {tar_filename}")
            extracted = subdirs[0]
        shutil.move(str(extracted), str(target_dir))
        print(f"saved: {target_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="models output directory")
    args = parser.parse_args()

    out = Path(args.output).resolve()
    for folder, tar_name in MODEL_TARS.items():
        download_and_extract(folder, tar_name, out)
    print("all models downloaded")


if __name__ == "__main__":
    main()
