[CmdletBinding()]
param(
    [ValidateSet('all', 'nsis', 'msi')]
    [string]$Bundle = 'all',
    [switch]$SkipSync,
    [switch]$SkipSidecar,
    [switch]$SkipNodeInstall,
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [string]$UpdaterPrivateKeyPath,
    [string]$UpdaterPasswordCredentialPath
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$desktopDirectory = Join-Path $repositoryRoot 'apps\desktop'
$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'

if ((Test-Path -LiteralPath $cargoBin -PathType Container) -and
    -not (($env:Path -split ';') -contains $cargoBin)) {
    $env:Path = "$cargoBin;$env:Path"
}

foreach ($command in @('cargo.exe', 'node.exe', 'npm.cmd', 'npx.cmd', 'uv.exe')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "缺少 Windows 构建命令: $command"
    }
}

if (-not $SkipSidecar) {
    & (Join-Path $PSScriptRoot 'build-sidecar.ps1') -SkipSync:$SkipSync
    if ($LASTEXITCODE -ne 0) { throw 'sidecar 构建失败。' }
}

Push-Location $desktopDirectory
try {
    if (-not $SkipNodeInstall) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw '桌面前端依赖安装失败。' }
    }

    $arguments = @('tauri', 'build')
    if ($Bundle -ne 'all') {
        $arguments += @('--bundles', $Bundle)
    }
    $override = @{ bundle = @{ } }
    if ($CertificateThumbprint) {
        $certificate = Get-Item "Cert:\CurrentUser\My\$CertificateThumbprint" -ErrorAction Stop
        if (-not $certificate.HasPrivateKey) {
            throw '指定的 Authenticode 证书没有可用私钥。'
        }
        $override.bundle.windows = @{
            certificateThumbprint = $certificate.Thumbprint
            digestAlgorithm = 'sha256'
            timestampUrl = $TimestampUrl
        }
    }

    $oldPrivateKey = $env:TAURI_SIGNING_PRIVATE_KEY
    $oldPrivateKeyPath = $env:TAURI_SIGNING_PRIVATE_KEY_PATH
    $oldPrivateKeyPassword = $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD
    try {
        if ($UpdaterPrivateKeyPath) {
            if (-not (Test-Path -LiteralPath $UpdaterPrivateKeyPath -PathType Leaf)) {
                throw "Tauri updater 私钥不存在: $UpdaterPrivateKeyPath"
            }
            $env:TAURI_SIGNING_PRIVATE_KEY = (Resolve-Path -LiteralPath $UpdaterPrivateKeyPath).Path
            $env:TAURI_SIGNING_PRIVATE_KEY_PATH = $null
            $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = $null
            if ($UpdaterPasswordCredentialPath) {
                $credential = Import-Clixml -LiteralPath $UpdaterPasswordCredentialPath
                if ($credential -isnot [System.Management.Automation.PSCredential]) {
                    throw 'updater 密码凭据文件格式无效。'
                }
                $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = $credential.GetNetworkCredential().Password
            }
            $override.bundle.createUpdaterArtifacts = $true
        }
        if ($override.bundle.Count -gt 0) {
            # npx.cmd is a batch shim; unescaped JSON quotes are removed by cmd.exe.
            $configurationJson = $override | ConvertTo-Json -Compress -Depth 5
            $arguments += @('--config', ($configurationJson -replace '"', '\"'))
        }
        & npx.cmd @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Tauri Windows 安装包构建失败。' }
    }
    finally {
        $env:TAURI_SIGNING_PRIVATE_KEY = $oldPrivateKey
        $env:TAURI_SIGNING_PRIVATE_KEY_PATH = $oldPrivateKeyPath
        $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = $oldPrivateKeyPassword
    }
}
finally { Pop-Location }

$bundleDirectory = Join-Path $desktopDirectory 'src-tauri\target\release\bundle'
$selectedDirectories = if ($Bundle -eq 'all') {
    @('nsis', 'msi')
} else {
    @($Bundle)
}
$artifacts = $selectedDirectories |
    ForEach-Object { Get-ChildItem -LiteralPath (Join-Path $bundleDirectory $_) -File } |
    Where-Object { $_.Extension -in @('.exe', '.msi') } |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        [pscustomobject]@{
            Path = $_.FullName
            SizeBytes = $_.Length
            SHA256 = $hash.Hash
        }
    }

if (-not $artifacts) {
    throw "没有在 $bundleDirectory 找到本次选择的 Windows 安装包。"
}
$artifacts
