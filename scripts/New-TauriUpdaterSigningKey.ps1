[CmdletBinding()]
param(
    [string]$KeyDirectory = (Join-Path $env:USERPROFILE '.karios-signing'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$desktopDirectory = Join-Path $repositoryRoot 'apps\desktop'
$privateKeyPath = Join-Path $KeyDirectory 'karios-stt-updater.key'
$publicKeyPath = "$privateKeyPath.pub"
$credentialPath = Join-Path $KeyDirectory 'karios-stt-updater.password.clixml'

if (-not $Force -and (@($privateKeyPath, $publicKeyPath, $credentialPath) | Where-Object { Test-Path -LiteralPath $_ })) {
    throw "updater 签名材料已存在于 $KeyDirectory；拒绝覆盖。需要明确轮换时使用 -Force。"
}

New-Item -ItemType Directory -Force -Path $KeyDirectory | Out-Null
$passwordBytes = New-Object byte[] 36
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$plainPassword = [Convert]::ToBase64String($passwordBytes)
$securePassword = ConvertTo-SecureString -String $plainPassword -AsPlainText -Force
$credential = [System.Management.Automation.PSCredential]::new('tauri-updater', $securePassword)

Push-Location $desktopDirectory
try {
    $arguments = @('tauri', 'signer', 'generate', '--ci', '--write-keys', $privateKeyPath, '--password', $plainPassword)
    if ($Force) { $arguments += '--force' }
    & npx.cmd @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Tauri updater Ed25519 密钥生成失败。' }
}
finally {
    $plainPassword = $null
    Pop-Location
}

$credential | Export-Clixml -LiteralPath $credentialPath -Force
if (-not (Test-Path -LiteralPath $publicKeyPath -PathType Leaf)) {
    throw "Tauri updater 公钥不存在: $publicKeyPath"
}

[pscustomobject]@{
    PrivateKeyPath = $privateKeyPath
    PublicKeyPath = $publicKeyPath
    PasswordCredentialPath = $credentialPath
    PublicKey = (Get-Content -LiteralPath $publicKeyPath -Raw).Trim()
    Note = '私钥与 DPAPI 密码凭据均在仓库外；请制作加密离线备份。'
}
