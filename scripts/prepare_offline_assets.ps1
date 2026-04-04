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
$lockFile = Join-Path $wheelDir "requirements-lock.txt"

New-Item -ItemType Directory -Force -Path $bundle | Out-Null
New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
New-Item -ItemType Directory -Force -Path $paddleDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null

if (-not (Test-Path $lockFile)) {
    throw "缺少锁定清单: $lockFile （请先维护 offline_bundle/wheels/requirements-lock.txt）"
}

Write-Host "1) 按 requirements-lock.txt 下载全部业务依赖 wheels（含 paddlepaddle 及其传递依赖，与内网离线安装一致）..."
& $PythonExe -m pip download -r $lockFile -d $wheelDir

Write-Host "2) 下载 Paddle CPU 栈至 paddle 目录（供「先装 paddle 再装 lock」两步安装；与 1 中 wheel 有重复属正常）..."
& $PythonExe -m pip download "paddlepaddle==$PaddleVersion" -d $paddleDir

Write-Host "3) 下载 PaddleOCR 模型..."
& $PythonExe (Join-Path $root "scripts\download_models.py") --output $modelsDir

Write-Host "4) 校验 offline_bundle（模型 + 离线 pip 解析）..."
& $PythonExe (Join-Path $root "scripts\verify_offline_bundle.py") --python $PythonExe
if ($LASTEXITCODE -ne 0) { throw "verify_offline_bundle.py 失败，请勿拷贝到内网。" }

Write-Host "Done. 将 offline_bundle 整体拷贝到内网后，按 服务器部署.md 用 --no-index 安装即可。"
