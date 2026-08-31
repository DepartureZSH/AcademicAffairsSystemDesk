[CmdletBinding()]
param(
    [switch]$SkipSync
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$tauriDirectory = Join-Path $repositoryRoot 'apps\desktop\src-tauri'
$binaryDirectory = Join-Path $tauriDirectory 'binaries'
$workDirectory = Join-Path $repositoryRoot 'build\sidecar\work'
$specDirectory = Join-Path $repositoryRoot 'build\sidecar\spec'
$distDirectory = Join-Path $repositoryRoot 'build\sidecar\dist'
$fontDirectory = Join-Path $repositoryRoot 'sidecar\stt_desktop\assets\fonts'
$fontPath = Join-Path $fontDirectory 'NotoSansSC-VF.ttf'
$fontLicensePath = Join-Path $fontDirectory 'OFL-1.1.txt'
$versionInfoPath = Join-Path $repositoryRoot 'build\sidecar\version-info.txt'

$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
$rustc = Join-Path $cargoBin 'rustc.exe'
if (-not (Test-Path -LiteralPath $rustc -PathType Leaf)) {
    $rustc = (Get-Command rustc.exe -ErrorAction Stop).Source
}
$targetTriple = (& $rustc --print host-tuple).Trim()
if (-not $targetTriple) {
    throw '无法确定 Rust target triple。'
}

New-Item -ItemType Directory -Force -Path $binaryDirectory, $workDirectory, $specDirectory, $distDirectory | Out-Null
if (-not (Test-Path -LiteralPath $fontPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $fontLicensePath -PathType Leaf)) {
    throw '冻结 Sidecar 前必须存在受审计的 Noto Sans SC 字体及 OFL-1.1 许可证。'
}
if (-not $SkipSync) {
    Push-Location $repositoryRoot
    try {
        & uv sync --frozen --extra build --extra dev
        if ($LASTEXITCODE -ne 0) { throw 'uv build 依赖同步失败。' }
    }
    finally { Pop-Location }
}

$binaryName = "stt-sidecar-$targetTriple"
$fontData = "$fontDirectory$([IO.Path]::PathSeparator)stt_desktop/assets/fonts"
Push-Location $repositoryRoot
try {
    & uv run python scripts/generate_windows_version_info.py --output $versionInfoPath
    if ($LASTEXITCODE -ne 0) { throw 'Sidecar Windows 版本元数据生成失败。' }
    & uv run --extra build --extra dev pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name $binaryName `
        --paths (Join-Path $repositoryRoot 'sidecar') `
        --add-data $fontData `
        --collect-all ortools `
        --version-file $versionInfoPath `
        --workpath $workDirectory `
        --specpath $specDirectory `
        --distpath $distDirectory `
        (Join-Path $repositoryRoot 'sidecar\stt_desktop\sidecar_main.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller sidecar 构建失败。' }
}
finally { Pop-Location }

$source = Join-Path $distDirectory "$binaryName.exe"
$destination = Join-Path $binaryDirectory "$binaryName.exe"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "sidecar 构建产物不存在: $source"
}
Copy-Item -LiteralPath $source -Destination $destination -Force
$hash = Get-FileHash -LiteralPath $destination -Algorithm SHA256
Write-Output ([pscustomobject]@{
    Path = $destination
    TargetTriple = $targetTriple
    SizeBytes = (Get-Item -LiteralPath $destination).Length
    SHA256 = $hash.Hash
})
