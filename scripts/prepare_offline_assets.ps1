param(
    [string]$PythonExe = "python",
    [string]$ProjectRoot = ".",
    [string]$PaddleVersion = "3.3.1"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $ProjectRoot).Path
$bundle = Join-Path $root "offline_bundle"
$wheelDir = Join-Path $bundle "wheels"
$paddleDir = Join-Path $bundle "paddle"
$modelsDir = Join-Path $bundle "models"
$pythonDir = Join-Path $bundle "python"

New-Item -ItemType Directory -Force -Path $bundle | Out-Null
New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
New-Item -ItemType Directory -Force -Path $paddleDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null

Write-Host "1) 下载项目依赖 wheels..."
& $PythonExe -m pip download -r (Join-Path $root "requirements.txt") -d $wheelDir

Write-Host "2) 下载 Paddle CPU wheel..."
& $PythonExe -m pip download "paddlepaddle==$PaddleVersion" -d $paddleDir

Write-Host "3) 下载 PaddleOCR 模型..."
& $PythonExe (Join-Path $root "scripts\download_models.py") --output $modelsDir

Write-Host "Done. Copy offline_bundle to intranet server."

