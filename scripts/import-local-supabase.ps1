param(
    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Workspace = '.local\workspace',

    [Parameter(Mandatory = $false)]
    [string]$LegacyRepository = '..\STT'
)

$ErrorActionPreference = 'Stop'
$sttPreviousDatabaseUrl = $env:STT_LEGACY_DATABASE_URL
$sttPreviousPythonUtf8 = $env:PYTHONUTF8
$sttLegacyRoot = (Resolve-Path -LiteralPath $LegacyRepository).Path
$sttStatus = supabase --workdir $sttLegacyRoot status -o env
if ($LASTEXITCODE -ne 0) {
    throw '无法读取本地 Supabase 状态。'
}
$sttDbLine = $sttStatus | Where-Object { $_ -match '^DB_URL=' } | Select-Object -First 1
if (-not $sttDbLine) {
    throw 'Supabase status 未返回 DB_URL。'
}

try {
    $env:STT_LEGACY_DATABASE_URL = ($sttDbLine -replace '^DB_URL=', '').Trim('"')
    $env:PYTHONUTF8 = '1'
    if ($ProjectId) {
        uv run stt-desktop legacy import --project-id $ProjectId --workspace $Workspace
    }
    else {
        uv run stt-desktop legacy discover
    }
    if ($LASTEXITCODE -ne 0) {
        throw "旧版数据迁移命令失败，退出码 $LASTEXITCODE。"
    }
}
finally {
    $env:STT_LEGACY_DATABASE_URL = $sttPreviousDatabaseUrl
    $env:PYTHONUTF8 = $sttPreviousPythonUtf8
}
