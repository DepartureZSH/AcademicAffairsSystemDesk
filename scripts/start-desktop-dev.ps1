[CmdletBinding()]
param(
    [string]$SupabaseEnvFile
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$desktopDirectory = Join-Path $repositoryRoot 'apps\desktop'
$hadPublishableKey = Test-Path Env:STT_SUPABASE_PUBLISHABLE_KEY

if (-not $hadPublishableKey) {
    if (-not $SupabaseEnvFile) {
        $parentDirectory = Split-Path -Parent $repositoryRoot
        $SupabaseEnvFile = Join-Path $parentDirectory 'STT\.env'
    }
    if (-not (Test-Path -LiteralPath $SupabaseEnvFile -PathType Leaf)) {
        throw '未设置 STT_SUPABASE_PUBLISHABLE_KEY，且找不到可读取的 Supabase 环境文件。'
    }
    $line = Get-Content -LiteralPath $SupabaseEnvFile |
        Where-Object { $_ -match '^SUPABASE_PUBLISHABLE_KEY=' } |
        Select-Object -First 1
    if (-not $line) {
        throw 'Supabase 环境文件缺少 SUPABASE_PUBLISHABLE_KEY。'
    }
    $value = $line.Substring($line.IndexOf('=') + 1).Trim('"').Trim()
    if (-not $value) {
        throw 'SUPABASE_PUBLISHABLE_KEY 为空。'
    }
    $env:STT_SUPABASE_PUBLISHABLE_KEY = $value
}

Push-Location $desktopDirectory
try {
    npm run tauri:dev
}
finally {
    Pop-Location
    if (-not $hadPublishableKey) {
        Remove-Item Env:STT_SUPABASE_PUBLISHABLE_KEY -ErrorAction SilentlyContinue
    }
}
