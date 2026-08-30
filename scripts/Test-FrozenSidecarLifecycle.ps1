[CmdletBinding()]
param(
    [string]$SidecarPath = 'apps/desktop/src-tauri/binaries/stt-sidecar-x86_64-pc-windows-msvc.exe'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedSidecar = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot $SidecarPath)).Path
$temporaryRoot = [System.IO.Path]::GetTempPath().TrimEnd('\')
$smokeRoot = Join-Path $temporaryRoot ('stt-sidecar-smoke-' + [guid]::NewGuid().ToString('N'))
$workspace = Join-Path $smokeRoot 'workspace'
$stdout = Join-Path $smokeRoot 'stdout.log'
$stderr = Join-Path $smokeRoot 'stderr.log'
New-Item -ItemType Directory -Path $workspace -Force | Out-Null

function New-RandomHex([int]$ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

function Stop-ExactSidecarProcess([int]$ProcessId) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return }
    $actualPath = (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").ExecutablePath
    if ($actualPath -eq $resolvedSidecar) {
        Stop-Process -Id $ProcessId -Force
    }
}

$token = New-RandomHex 32
$nonce = New-RandomHex 16
$savedEnvironment = @{
    STT_SIDECAR_TOKEN = $env:STT_SIDECAR_TOKEN
    STT_SIDECAR_NONCE = $env:STT_SIDECAR_NONCE
    STT_WORKSPACE_PATH = $env:STT_WORKSPACE_PATH
    STT_SERVICES_CONFIG = $env:STT_SERVICES_CONFIG
}
$process = $null
$ready = $null
$startupTimer = [System.Diagnostics.Stopwatch]::new()

try {
    try {
        $env:STT_SIDECAR_TOKEN = $token
        $env:STT_SIDECAR_NONCE = $nonce
        $env:STT_WORKSPACE_PATH = $workspace
        $env:STT_SERVICES_CONFIG = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot 'config/services.yaml')).Path
        $startupTimer.Start()
        $process = Start-Process `
            -FilePath $resolvedSidecar `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
    }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            Set-Item -Path "Env:$name" -Value $savedEnvironment[$name]
        }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $stdout -PathType Leaf) {
            $line = Get-Content -LiteralPath $stdout -TotalCount 1 -ErrorAction SilentlyContinue
            if ($line) {
                $startupTimer.Stop()
                $ready = $line | ConvertFrom-Json
                break
            }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $ready) {
        $errorText = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
        throw "冻结 sidecar 未在 5 秒内就绪: $errorText"
    }
    if ([int]$ready.pid -ne $process.Id) {
        throw "启动器 PID 不匹配: expected=$($process.Id), actual=$($ready.pid)"
    }
    if ([int]$ready.workerPid -le 0 -or [int]$ready.workerPid -eq $process.Id) {
        throw "冻结 sidecar 工作进程 PID 无效: $($ready.workerPid)"
    }

    $headers = @{ Authorization = "Bearer $token"; Origin = 'tauri://localhost' }
    $health = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/v1/health" `
        -Headers $headers `
        -Method Get `
        -TimeoutSec 5
    if ($health.status -ne 'ok') { throw '冻结 sidecar 健康检查失败。' }

    $shutdown = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/v1/runtime/shutdown" `
        -Headers $headers `
        -Method Post `
        -TimeoutSec 5
    Wait-Process -Id $process.Id -Timeout 15 -ErrorAction Stop
    Start-Sleep -Milliseconds 300
    $launcherAlive = [bool](Get-Process -Id $process.Id -ErrorAction SilentlyContinue)
    $workerAlive = [bool](Get-Process -Id ([int]$ready.workerPid) -ErrorAction SilentlyContinue)
    if ($launcherAlive -or $workerAlive) {
        throw "授权关闭后仍有 sidecar 进程: launcher=$launcherAlive worker=$workerAlive"
    }

    [pscustomobject]@{
        LauncherPid = $process.Id
        WorkerPid = [int]$ready.workerPid
        Port = [int]$ready.port
        StartupMilliseconds = $startupTimer.ElapsedMilliseconds
        Health = $health.status
        Shutdown = $shutdown.status
        LauncherExited = -not $launcherAlive
        WorkerExited = -not $workerAlive
    }
}
finally {
    if ($process) { Stop-ExactSidecarProcess $process.Id }
    if ($ready) { Stop-ExactSidecarProcess ([int]$ready.workerPid) }
    if (Test-Path -LiteralPath $smokeRoot -PathType Container) {
        $resolvedSmokeRoot = (Resolve-Path -LiteralPath $smokeRoot).Path
        if (
            (Split-Path -Parent $resolvedSmokeRoot) -ne $temporaryRoot -or
            -not (Split-Path -Leaf $resolvedSmokeRoot).StartsWith('stt-sidecar-smoke-')
        ) {
            throw "拒绝清理未验证的冻结 sidecar 临时目录: $resolvedSmokeRoot"
        }
        Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force
    }
}
