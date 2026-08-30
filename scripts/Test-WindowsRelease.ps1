[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallerPath,
    [Parameter(Mandatory)]
    [string]$ExpectedThumbprint,
    [string]$UpdaterSignaturePath
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$tauriDirectory = Join-Path $repositoryRoot 'apps\desktop\src-tauri'
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$expected = $ExpectedThumbprint.Replace(' ', '').ToUpperInvariant()

function Assert-AuthenticodeSignature {
    param([string]$Path)
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if (-not $signature.SignerCertificate) {
        throw "文件没有 Authenticode 签名: $Path"
    }
    if ($signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $expected) {
        throw "文件签名证书与预期不符: $Path"
    }
    if ($signature.Status -eq [System.Management.Automation.SignatureStatus]::HashMismatch) {
        throw "文件的 Authenticode 哈希不匹配: $Path"
    }
    $isExpectedUntrustedRoot =
        $signature.Status -eq [System.Management.Automation.SignatureStatus]::UnknownError -and
        $signature.StatusMessage -match '不受信任|not trusted'
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -and -not $isExpectedUntrustedRoot) {
        throw "文件 Authenticode 状态无效 ($($signature.Status)): $Path"
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "文件缺少可信时间戳签名: $Path"
    }
    [pscustomobject]@{
        Path = $Path
        Status = $signature.Status.ToString()
        SignerThumbprint = $signature.SignerCertificate.Thumbprint
        TimestampSubject = $signature.TimeStamperCertificate.Subject
    }
}

$results = @()
$results += Assert-AuthenticodeSignature -Path $resolvedInstaller

if ([IO.Path]::GetExtension($resolvedInstaller) -in @('.exe', '.msi')) {
    if (-not (Get-Command 7z.exe -ErrorAction SilentlyContinue)) {
        throw '验证 NSIS 内部程序需要 7z.exe。'
    }
    $verificationRoot = Join-Path $repositoryRoot 'build\signing'
    New-Item -ItemType Directory -Force -Path $verificationRoot | Out-Null
    $extractDirectory = Join-Path $verificationRoot ("verify-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $extractDirectory | Out-Null
    try {
        & 7z.exe x $resolvedInstaller "-o$extractDirectory" -y | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '无法解包 Windows 安装包。' }
        $innerNames = @('karios-stt-desktop.exe', 'stt-sidecar.exe')
        if ([IO.Path]::GetExtension($resolvedInstaller) -eq '.msi') {
            # 7-Zip 会透明展开 MSI 内嵌的 app.cab。
            $innerNames = @('Path', 'Bin_stt_sidecar.exe')
        }
        foreach ($name in $innerNames) {
            $path = Join-Path $extractDirectory $name
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Windows 安装包缺少 $name"
            }
            $results += Assert-AuthenticodeSignature -Path $path
        }
    }
    finally {
        if (Test-Path -LiteralPath $extractDirectory -PathType Container) {
            $resolvedExtract = (Resolve-Path -LiteralPath $extractDirectory).Path
            $resolvedVerificationRoot = (Resolve-Path -LiteralPath $verificationRoot).Path
            if (
                (Split-Path -Parent $resolvedExtract) -ne $resolvedVerificationRoot -or
                -not (Split-Path -Leaf $resolvedExtract).StartsWith('verify-')
            ) {
                throw "拒绝清理未验证的验签临时目录: $resolvedExtract"
            }
            Remove-Item -LiteralPath $resolvedExtract -Recurse -Force
        }
    }
}

if ($UpdaterSignaturePath) {
    $resolvedUpdaterSignature = (Resolve-Path -LiteralPath $UpdaterSignaturePath).Path
    Push-Location $tauriDirectory
    try {
        $cargo = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
        if (-not (Test-Path -LiteralPath $cargo -PathType Leaf)) {
            $cargo = (Get-Command cargo.exe -ErrorAction Stop).Source
        }
        & $cargo run --quiet --example verify_updater_signature -- $resolvedInstaller $resolvedUpdaterSignature
        if ($LASTEXITCODE -ne 0) { throw 'Tauri updater Ed25519 签名验证失败。' }
    }
    finally { Pop-Location }
}

$results
