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
if (-not $SkipSync) {
    Push-Location $repositoryRoot
    try {
        & uv sync --frozen --extra build --extra dev
        if ($LASTEXITCODE -ne 0) { throw 'uv build 依赖同步失败。' }
    }
    finally { Pop-Location }
}

$binaryName = "stt-sidecar-$targetTriple"
Push-Location $repositoryRoot
try {
    & uv run --extra build --extra dev pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name $binaryName `
        --paths (Join-Path $repositoryRoot 'sidecar') `
        --collect-all ortools `
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
