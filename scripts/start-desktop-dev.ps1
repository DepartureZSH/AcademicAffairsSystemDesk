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
        $SupabaseEnvFile = Join-Path $repositoryRoot '.env'
    }
    if (-not (Test-Path -LiteralPath $SupabaseEnvFile -PathType Leaf)) {
        throw '未设置 STT_SUPABASE_PUBLISHABLE_KEY，且找不到可读取的 Supabase 环境文件。'
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $SupabaseEnvFile) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $values[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
        }
    }
    $value = $values['STT_SUPABASE_PUBLISHABLE_KEY']
    if (-not $value) { $value = $values['SUPABASE_PUBLISHABLE_KEY'] }
    if (-not $value) { $value = $values['SUPABASE_ANON_KEY'] }
    if (-not $value) {
        throw '请配置线上 Supabase 的 publishable 或 Legacy anon key，禁止填写服务密钥。'
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
