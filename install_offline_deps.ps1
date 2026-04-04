param(
    [string]$ProjectRoot = $PSScriptRoot,
    [string]$PythonExe = "",
    [string]$VenvDir = ".venv"
)

$ErrorActionPreference = "Stop"

function Require-Dir([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "目录不存在: $path"
    }
}

Require-Dir $ProjectRoot

$wheelsDir = Join-Path $ProjectRoot "offline_bundle\wheels"
$paddleDir = Join-Path $ProjectRoot "offline_bundle\paddle"
$reqLock = Join-Path $wheelsDir "requirements-lock.txt"

Require-Dir $wheelsDir
Require-Dir $paddleDir
if (-not (Test-Path -LiteralPath $reqLock)) {
    throw "找不到: $reqLock"
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $py) {
        throw "未找到 python 命令；请在参数里显式传 -PythonExe 例如：-PythonExe 'C:\Python313\python.exe'"
    }
    $PythonExe = $py.Source
}

$venvPath = Join-Path $ProjectRoot $VenvDir
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "创建虚拟环境: $venvPath"
    & $PythonExe -m venv $venvPath | Out-Host
}

$pipExe = Join-Path $venvPath "Scripts\pip.exe"
if (-not (Test-Path -LiteralPath $pipExe)) {
    throw "找不到 pip: $pipExe"
}

Write-Host "离线安装 Paddle（CPU）..."
$paddleWheel = Get-ChildItem -LiteralPath $paddleDir -Filter "paddlepaddle-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $paddleWheel) {
    throw "离线 Paddle wheel 未找到: $paddleDir"
}

& $pipExe install --no-index --find-links $wheelsDir --find-links $paddleDir $paddleWheel.FullName | Out-Host

Write-Host "离线安装其余依赖（requirements-lock.txt）..."
& $pipExe install --no-index --find-links $wheelsDir -r $reqLock | Out-Host

Write-Host "验证导入..."
& $venvPython -c "import fastapi, paddleocr, paddlex; import paddle; print('offline deps import ok')" | Out-Host

Write-Host "离线依赖安装完成。"

