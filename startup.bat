@echo off
setlocal EnableExtensions

REM 切换到项目根目录（与 startup.bat 同目录）
cd /d "%~dp0"

REM 离线/内网建议关闭 Paddle 组件联网检查，避免启动卡住
if not defined PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK (
    set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1
)

REM 工作进程数（CPU 模式）；可按服务器核数调整，例如 set OCR_WORKERS=4
if not defined OCR_WORKERS (
    for /f %%i in ('powershell -NoProfile -Command "[Math]::Max(1, [int]([Environment]::ProcessorCount / 2))" 2^>nul') do set OCR_WORKERS=%%i
)
if not defined OCR_WORKERS set OCR_WORKERS=2

REM 监听端口；需要改端口时： set OCR_PORT=8080 后再运行本脚本
if not defined OCR_PORT set OCR_PORT=8000

REM 监听地址；内网访问可使用 0.0.0.0
if not defined OCR_HOST set OCR_HOST=0.0.0.0

if exist ".venv\Scripts\python.exe" (
    set "PYEXE=.venv\Scripts\python.exe"
) else (
    set "PYEXE=python"
)

echo [OCR] Project: %CD%
echo [OCR] Python:  %PYEXE%
echo [OCR] Listen:  %OCR_HOST%:%OCR_PORT%  workers=%OCR_WORKERS%
echo.

"%PYEXE%" -m uvicorn app.main:app --host %OCR_HOST% --port %OCR_PORT% --workers %OCR_WORKERS%

set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
    echo.
    echo [OCR] Exited with code %EXITCODE%. Check that dependencies are installed in .venv (see 服务器部署.md).
    pause
)
exit /b %EXITCODE%
