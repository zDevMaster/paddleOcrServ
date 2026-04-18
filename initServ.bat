@echo off
setlocal EnableExtensions

REM 内网 / 无网络服务器：拷贝完整项目后，在项目根执行本脚本一次，自动创建 .venv 并从 offline_bundle 离线安装依赖。
REM 依赖：已安装与 wheel 标签一致的 Python x64（见 服务器部署.md）；须含 offline_bundle\wheels 与 offline_bundle\paddle。
REM 可选环境变量 INIT_PYTHON：指定 python.exe 完整路径（未设置则用 PATH 中的 python）。
REM 可选参数 rebuild：删除现有 .venv 后重新创建并安装。

cd /d "%~dp0"

set "LOCK=offline_bundle\wheels\requirements-lock.txt"
if not exist "%LOCK%" (
    echo [initServ] 缺少 %LOCK%，请确认已完整拷贝仓库（含 offline_bundle）。
    pause
    exit /b 2
)

if not exist "offline_bundle\wheels\" (
    echo [initServ] 缺少 offline_bundle\wheels\
    pause
    exit /b 2
)

if not exist "offline_bundle\paddle\" (
    echo [initServ] 缺少 offline_bundle\paddle\（离线安装需要 Paddle CPU 依赖目录）
    pause
    exit /b 2
)

if not defined INIT_PYTHON set "INIT_PYTHON=python"
"%INIT_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [initServ] 未找到 Python。请先安装与 wheel 文件名中 cp3xx 一致的 Python x64，并加入 PATH，或 set INIT_PYTHON=完整路径
    pause
    exit /b 1
)

echo [initServ] 使用 Python:
"%INIT_PYTHON%" --version

if /i "%~1"=="rebuild" (
    if exist ".venv\" (
        echo [initServ] 参数 rebuild：删除现有 .venv ...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [initServ] 创建虚拟环境 .venv ...
    "%INIT_PYTHON%" -m venv .venv
    if errorlevel 1 (
        echo [initServ] python -m venv 失败
        pause
        exit /b 1
    )
) else (
    echo [initServ] 已存在 .venv，将仅在此环境中执行离线 pip 安装。
)

echo [initServ] 离线安装依赖（--no-index，不访问外网）...
".venv\Scripts\python.exe" -m pip install --no-index --find-links "offline_bundle\wheels" --find-links "offline_bundle\paddle" -r "%LOCK%"
if errorlevel 1 (
    echo [initServ] pip 安装失败。请核对 Python 主版本与 wheel 的 cp3xx 一致，并确认外网已用 scripts\prepare_offline_assets.ps1 补全 wheel。
    pause
    exit /b 1
)

echo [initServ] 验证关键包导入...
".venv\Scripts\python.exe" -c "import uvicorn, fastapi, paddle; print('[initServ] import ok')"
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo [initServ] 完成。请运行启动脚本之一：startupV4m.bat、startupv5m.bat、startupv5s.bat
exit /b 0
