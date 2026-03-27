@echo off
setlocal EnableExtensions

cd /d "%~dp0"

if not defined TEST_SITE_HOST set TEST_SITE_HOST=127.0.0.1
if not defined TEST_SITE_PORT set TEST_SITE_PORT=9000

if exist "..\.venv\Scripts\python.exe" (
    set "PYEXE=..\.venv\Scripts\python.exe"
) else (
    set "PYEXE=python"
)

echo [TEST-SITE] Python: %PYEXE%
echo [TEST-SITE] URL:    http://%TEST_SITE_HOST%:%TEST_SITE_PORT%
echo.

"%PYEXE%" -m uvicorn test_site:app --host %TEST_SITE_HOST% --port %TEST_SITE_PORT% --reload

