[CmdletBinding()]
param(
    [ValidateSet('all', 'nsis', 'msi')]
    [string]$Bundle = 'all',
    [switch]$SkipSync,
    [switch]$SkipSidecar,
    [switch]$SkipNodeInstall
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
    & npx.cmd @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Tauri Windows 安装包构建失败。' }
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
