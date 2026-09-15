# Public client configuration only. Never source/execute a dotenv file or import all its values.
function Get-DesktopPublishableKey {
    [CmdletBinding()]
    param([string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env'))
    $names = @('STT_SUPABASE_PUBLISHABLE_KEY', 'SUPABASE_PUBLISHABLE_KEY', 'SUPABASE_ANON_KEY')
    $value = $null
    foreach ($name in $names) {
        $candidate = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($candidate)) { $value = $candidate.Trim(); break }
    }
    if (-not $value -and (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        $publicValues = @{}
        foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
            if ($line -match '^\s*(?:export\s+)?(STT_SUPABASE_PUBLISHABLE_KEY|SUPABASE_PUBLISHABLE_KEY|SUPABASE_ANON_KEY)\s*=\s*(.*?)\s*$') {
                $publicValues[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
            }
        }
        foreach ($name in $names) {
            if (-not [string]::IsNullOrWhiteSpace($publicValues[$name])) { $value = $publicValues[$name]; break }
        }
    }
    if (-not $value) {
        throw '缺少发行版公开登录配置。请在构建环境或未入库的 .env 中设置 publishable/anon key；已停止打包。'
    }
    $valid = $value -match '^sb_publishable_[A-Za-z0-9_-]+$'
    if (-not $valid -and $value -match '^[A-Za-z0-9_-]+\.([A-Za-z0-9_-]+)\.[A-Za-z0-9_-]+$') {
        try {
            $payload = $matches[1].Replace('-', '+').Replace('_', '/')
            $payload = $payload.PadRight($payload.Length + ((4 - $payload.Length % 4) % 4), '=')
            $claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
            $valid = $claims.role -ceq 'anon'
        } catch { $valid = $false }
    }
    if (-not $valid) {
        throw '发行版只允许 publishable 或 role=anon 的公开 key；拒绝服务端密钥或无效配置。'
    }
    return $value
}
