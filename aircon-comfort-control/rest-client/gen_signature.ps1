# SwitchBot OpenAPI v1.1 の認証ヘッダー(t/nonce/sign)を計算し、devices.http に貼り付ける形式で出力する。
# lib/switchbot_client.py の _build_headers と同じロジック（sign = base64(HMAC-SHA256(secret, token+t+nonce))）。

$envPath = Join-Path $PSScriptRoot "..\.env"

if (-not (Test-Path $envPath)) {
    Write-Error "$envPath が見つかりません。.env.example をコピーして作成してください。"
    exit 1
}

$envVars = @{}
foreach ($line in Get-Content $envPath -Encoding UTF8) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $parts = $line -split '=', 2
    $k = $parts[0].Trim()
    $v = $parts[1].Trim()
    $envVars[$k] = $v
}

$token = $envVars["SWITCHBOT_TOKEN"]
$secret = $envVars["SWITCHBOT_SECRET"]

$tokenLen = 0
$secretLen = 0
if ($token) { $tokenLen = $token.Length }
if ($secret) { $secretLen = $secret.Length }

if ($tokenLen -eq 0 -or $secretLen -eq 0) {
    Write-Error "SWITCHBOT_TOKEN / SWITCHBOT_SECRET が $envPath に設定されていません。"
    exit 1
}

$nonce = [guid]::NewGuid().ToString()
$t = [string][int64](([datetimeoffset]::UtcNow).ToUnixTimeMilliseconds())

$stringToSign = "$token$t$nonce"
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($secret)
$hash = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($stringToSign))
$sign = [Convert]::ToBase64String($hash)

Write-Output "----"
Write-Output "@token = $token"
Write-Output "@t = $t"
Write-Output "@nonce = $nonce"
Write-Output "@sign = $sign"
