[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ExecutablePath,
    [string]$SupabaseEnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env')
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'DesktopClientConfig.ps1')
$key = Get-DesktopPublishableKey -EnvFile $SupabaseEnvFile
$binary = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ExecutablePath).Path))
if (-not $binary.Contains($key)) {
    throw '发行版主程序没有嵌入预期的公开登录配置；禁止发布此安装包。'
}
if (Test-Path -LiteralPath $SupabaseEnvFile -PathType Leaf) {
    foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $SupabaseEnvFile).Path)) {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*(?:PASSWORD|SECRET|SERVICE_ROLE|PRIVATE_KEY)[A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
            $sensitive = $matches[2].Trim().Trim('"').Trim("'")
            if ($sensitive.Length -ge 8 -and $binary.Contains($sensitive)) {
                throw '发行版疑似包含服务端凭据；禁止发布。具体值不会输出。'
            }
        }
    }
}
Write-Output 'PASS 发行版主程序已包含公开登录配置，未检出环境文件中的服务端凭据。'
