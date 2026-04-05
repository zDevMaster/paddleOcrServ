@echo off

setlocal EnableExtensions



REM PP-OCRv5 server 检测 + 识别（精度高、内存大）；Windows 默认 1 worker（见 OCR_WORKERS 说明）

REM 若日志出现 Child process died，请降低 OCR_WORKERS 或换 startupv5m.bat / startupV4m.bat

REM 用法：直接运行为前台；可加参数 bg / background 后台启动



cd /d "%~dp0"



set OCR_DET_MODEL_NAME=PP-OCRv5_server_det

set OCR_REC_MODEL_NAME=PP-OCRv5_server_rec

REM Windows：uvicorn 多 worker 可能 WinError 10022；未设置时默认 1。大模型多 worker 亦易 OOM。
if not defined OCR_WORKERS set OCR_WORKERS=1



if not defined PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK (

    set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1

)

if not defined FLAGS_use_mkldnn (

    set FLAGS_use_mkldnn=0

)



if not defined OCR_PORT set OCR_PORT=8000

if not defined OCR_HOST set OCR_HOST=0.0.0.0



if exist ".venv\Scripts\python.exe" (

    set "PYEXE=.venv\Scripts\python.exe"

) else (

    set "PYEXE=python"

)



if /i "%~1"=="bg" set "OCR_BACKGROUND=1"

if /i "%~1"=="background" set "OCR_BACKGROUND=1"

if "%OCR_BACKGROUND%"=="1" goto :BACKGROUND



echo [OCR] Profile:  PP-OCRv5 server (det+rec)

echo [OCR] Project:  %CD%

echo [OCR] Python:   %PYEXE%

echo [OCR] Listen:   %OCR_HOST%:%OCR_PORT%  workers=%OCR_WORKERS%

echo.



"%PYEXE%" -m uvicorn app.main:app --host %OCR_HOST% --port %OCR_PORT% --workers %OCR_WORKERS% --log-config "%~dp0uvicorn_log_config.json"



set EXITCODE=%ERRORLEVEL%

if not %EXITCODE%==0 (

    echo.

    echo [OCR] Exited with code %EXITCODE%.

    pause

)

exit /b %EXITCODE%



:BACKGROUND

echo [OCR] Profile: PP-OCRv5 server  (background)

start "PaddleOCR-v5s" /D "%~dp0" /MIN "%PYEXE%" -m uvicorn app.main:app --host %OCR_HOST% --port %OCR_PORT% --workers %OCR_WORKERS% --log-config "%~dp0uvicorn_log_config.json"

echo [OCR] 已后台启动。健康检查: http://127.0.0.1:%OCR_PORT%/health

exit /b 0


