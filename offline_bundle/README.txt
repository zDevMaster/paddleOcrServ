offline_bundle 目录说明（与 服务器部署.md 一致）

- models/     PaddleOCR 检测/识别推理包（含 inference.yml 等）
- paddle/     Paddle CPU 栈及传递依赖的离线 wheel（内网 pip 双 --find-links 之一）
- wheels/     业务依赖离线 wheel + requirements-lock.txt 锁定清单

内网服务器首次部署：在项目根目录执行 initServ.bat，可自动创建 .venv 并完成离线 pip 安装（无需联网）。

外网打包前：运行 scripts\prepare_offline_assets.ps1，收尾会执行 scripts\verify_offline_bundle.py 自检。
