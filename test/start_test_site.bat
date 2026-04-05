@echo off
setlocal EnableExtensions

cd /d "%~dp0"

REM uvicorn 在导入应用之前就会加载 --log-config；其中自定义 Handler 需能 import app.*，故将仓库根加入 PYTHONPATH
set "PYTHONPATH=%~dp0..;%PYTHONPATH%"

REM 默认 0.0.0.0：本机可用 127.0.0.1，局域网其它电脑可用本机 IP（如 192.168.x.x）。仅本机可设 TEST_SITE_HOST=127.0.0.1
if not defined TEST_SITE_HOST set TEST_SITE_HOST=0.0.0.0
if not defined TEST_SITE_PORT set TEST_SITE_PORT=9000

if exist "..\.venv\Scripts\python.exe" (
    set "PYEXE=..\.venv\Scripts\python.exe"
) else (
    set "PYEXE=python"
)

echo [TEST-SITE] Python: %PYEXE%
echo [TEST-SITE] URL:    http://%TEST_SITE_HOST%:%TEST_SITE_PORT%
echo.

"%PYEXE%" -m uvicorn test_site:app --host %TEST_SITE_HOST% --port %TEST_SITE_PORT% --reload --log-config "%~dp0..\uvicorn_log_config.json"

