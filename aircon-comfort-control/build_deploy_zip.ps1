# aircon-comfort-control の Lambda デプロイパッケージ(zip)を作成する
#
# lambda_function.py と lib/ に加えて、requests(および依存の
# certifi/charset-normalizer/idna/urllib3) を Lambda 実行環境
# (Python 3.12, Linux x86_64) 向けの wheel で vendoring して zip 化する。
#
# 実行方法:
#   powershell -File aircon-comfort-control/build_deploy_zip.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot "dist"
$ZipPath = Join-Path $DistDir "deploy.zip"

if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Path $BuildDir | Out-Null

if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}
New-Item -ItemType Directory -Path $DistDir | Out-Null

Write-Host "Vendoring requests (Lambda: Python 3.12 / linux x86_64) ..."
uv pip install `
    --target $BuildDir `
    --python-platform x86_64-unknown-linux-gnu `
    --python-version 3.12 `
    --only-binary ":all:" `
    requests

# requests/idna/charset-normalizer の CLI エントリポイント(Windows用.exe)は
# Lambda では不要かつ実行環境(Linux)と一致しないため削除する
$BinDir = Join-Path $BuildDir "bin"
if (Test-Path $BinDir) {
    Remove-Item -Recurse -Force $BinDir
}

Write-Host "Copying lambda_function.py and lib/ ..."
Copy-Item (Join-Path $ProjectRoot "lambda_function.py") $BuildDir
Copy-Item (Join-Path $ProjectRoot "lib") $BuildDir -Recurse -Exclude "__pycache__"
Get-ChildItem -Path (Join-Path $BuildDir "lib") -Recurse -Filter "__pycache__" -Directory |
    Remove-Item -Recurse -Force

Write-Host "Creating $ZipPath ..."
Compress-Archive -Path (Join-Path $BuildDir "*") -DestinationPath $ZipPath -Force

Write-Host "Done: $ZipPath"
