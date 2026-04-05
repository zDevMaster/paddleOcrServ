@echo off

setlocal EnableExtensions



REM PP-OCRv4 mobile 检测 + 识别；Windows 默认 1 worker（见脚本内 OCR_WORKERS 说明）

REM 用法：直接运行为前台；可加参数 bg / background 后台启动



cd /d "%~dp0"



set OCR_DET_MODEL_NAME=PP-OCRv4_mobile_det

set OCR_REC_MODEL_NAME=PP-OCRv4_mobile_rec

REM Windows：uvicorn --workers>1 时子进程继承监听套接字可能 OSError WinError 10022；未设置环境变量时默认 1。需多进程可先 set OCR_WORKERS=N。
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



echo [OCR] Profile:  PP-OCRv4 mobile (det+rec)

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

echo [OCR] Profile: PP-OCRv4 mobile  (background)

REM start 默认工作目录常为 System32，必须 /D 指定项目根，否则找不到 app 包、/health 无法访问
start "PaddleOCR-v4m" /D "%~dp0" /MIN "%PYEXE%" -m uvicorn app.main:app --host %OCR_HOST% --port %OCR_PORT% --workers %OCR_WORKERS% --log-config "%~dp0uvicorn_log_config.json"

echo [OCR] 已后台启动。健康检查: http://127.0.0.1:%OCR_PORT%/health

exit /b 0


