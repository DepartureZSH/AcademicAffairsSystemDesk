[CmdletBinding()]
param(
    [string]$SidecarPath = 'apps/desktop/src-tauri/binaries/stt-sidecar-x86_64-pc-windows-msvc.exe',
    [int]$StartupTimeoutSeconds = 20,
    [int]$SchedulingTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedSidecar = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot $SidecarPath)).Path
$temporaryRoot = [System.IO.Path]::GetTempPath().TrimEnd('\')
$testRoot = Join-Path $temporaryRoot ('stt-frozen-workflow-' + [Guid]::NewGuid().ToString('N'))
$workspace = Join-Path $testRoot 'workspace'
$outputs = Join-Path $testRoot 'outputs'
$stdout = Join-Path $testRoot 'stdout.log'
$stderr = Join-Path $testRoot 'stderr.log'
New-Item -ItemType Directory -Path $workspace, $outputs -Force | Out-Null

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

function Invoke-SidecarApi {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST', 'PUT', 'DELETE')][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [AllowNull()][object]$Body = $null,
        [int]$TimeoutSec = 15
    )

    if ($Path -notmatch '^/v1/[A-Za-z0-9_./?=&-]+$' -or $Path.Contains('..')) {
        throw "拒绝未通过白名单的 Sidecar API 路径：$Path"
    }
    $parameters = @{
        Uri = "$script:baseUri$Path"
        Headers = $script:headers
        Method = $Method
        TimeoutSec = $TimeoutSec
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = $Body | ConvertTo-Json -Compress -Depth 12
    }
    return Invoke-RestMethod @parameters
}

function Save-Entity {
    param([Parameter(Mandatory)][string]$Type, [Parameter(Mandatory)][hashtable]$Data)

    $saved = Invoke-SidecarApi -Method PUT -Path "/v1/data/$Type" -Body @{
        expected_revision = $script:revision
        data = $Data
    }
    $script:revision = [int]$saved.revision
    return $saved.item
}

function Wait-SchedulingRound {
    param([Parameter(Mandatory)][string]$RoundId)

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($SchedulingTimeoutSeconds)
    do {
        $current = (Invoke-SidecarApi -Method GET -Path "/v1/scheduling/rounds/$RoundId").round
        if ($current.status -in @('succeeded', 'infeasible', 'cancelled', 'failed', 'failed_recoverable')) {
            return $current
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "排课轮次未在 $SchedulingTimeoutSeconds 秒内结束。"
}

function Assert-FileMagic {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][byte[]]$Expected,
        [Parameter(Mandatory)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label 文件不存在。" }
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $actual = New-Object byte[] $Expected.Length
        if ($stream.Read($actual, 0, $actual.Length) -ne $Expected.Length) { throw "$Label 文件过短。" }
        for ($index = 0; $index -lt $Expected.Length; $index++) {
            if ($actual[$index] -ne $Expected[$index]) { throw "$Label 文件头无效。" }
        }
    }
    finally {
        $stream.Dispose()
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
$baseUri = $null
$headers = $null
$revision = 0

try {
    try {
        $env:STT_SIDECAR_TOKEN = $token
        $env:STT_SIDECAR_NONCE = $nonce
        $env:STT_WORKSPACE_PATH = $workspace
        $env:STT_SERVICES_CONFIG = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot 'config/services.yaml')).Path
        $process = Start-Process `
            -FilePath $resolvedSidecar `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
    }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            if ($null -eq $savedEnvironment[$name]) {
                Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
            }
            else {
                Set-Item -Path "Env:$name" -Value $savedEnvironment[$name]
            }
        }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $stdout -PathType Leaf) {
            $line = Get-Content -LiteralPath $stdout -TotalCount 1 -ErrorAction SilentlyContinue
            if ($line) {
                $ready = $line | ConvertFrom-Json
                break
            }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $ready) {
        $errorText = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
        throw "冻结 Sidecar 未在 $StartupTimeoutSeconds 秒内就绪：$errorText"
    }
    if ([int]$ready.pid -ne $process.Id) { throw '启动器 PID 与就绪消息不匹配。' }
    if ([int]$ready.workerPid -le 0 -or [int]$ready.workerPid -eq $process.Id) {
        throw 'Sidecar 工作进程 PID 无效。'
    }

    $baseUri = "http://127.0.0.1:$($ready.port)"
    $headers = @{ Authorization = "Bearer $token"; Origin = 'tauri://localhost' }
    $health = Invoke-SidecarApi -Method GET -Path '/v1/health'
    if ($health.status -ne 'ok' -or $health.protocolVersion -ne '1') {
        throw '冻结 Sidecar 健康或协议版本检查失败。'
    }
    if ($health.serviceModes.identity -ne 'real' -or $health.serviceModes.license -ne 'mock') {
        throw '冻结 Sidecar 未加载预期的服务模式配置。'
    }
    Write-Output 'PASS 冻结 Sidecar 启动、鉴权与服务模式'

    $created = Invoke-SidecarApi -Method POST -Path '/v1/projects' -Body @{ name = '冻结制品全流程项目' }
    $sourceProjectId = [string]$created.project.id
    $revision = [int]$created.revision
    if ([string]::IsNullOrWhiteSpace($sourceProjectId) -or $revision -ne 0) { throw '创建项目响应无效。' }

    $null = Save-Entity -Type term -Data @{
        id = 'term-1'; name = '第一学期'; week_count = 20; day_count = 5; active = 1
    }
    $null = Save-Entity -Type bell_schedule -Data @{
        id = 'schedule-1'; term_id = 'term-1'; name = '默认作息'; day_count = 5
        slot_duration_minutes = 40; is_default = 1
    }
    foreach ($index in 0..1) {
        $null = Save-Entity -Type time_slot -Data @{
            id = "slot-$index"; bell_schedule_id = 'schedule-1'; weekday = 1
            period_index = $index; label = "第 $($index + 1) 节"; start_slot = $index
            length_slots = 1; start_time_minutes = 480 + $index * 50
            end_time_minutes = 520 + $index * 50
        }
    }
    $null = Save-Entity -Type teacher -Data @{ id = 'teacher-1'; name = '张老师' }
    $null = Save-Entity -Type subject -Data @{ id = 'subject-1'; name = '数学' }
    $null = Save-Entity -Type grade -Data @{ id = 'grade-1'; name = '一年级' }
    $null = Save-Entity -Type homeroom -Data @{
        id = 'homeroom-1'; grade_id = 'grade-1'; term_id = 'term-1'; name = '一年级一班'
    }
    $taskSaved = Invoke-SidecarApi -Method PUT -Path '/v1/planning/tasks' -Body @{
        expected_revision = $revision
        data = @{
            id = 'task-1'; term_id = 'term-1'; homeroom_id = 'homeroom-1'
            subject_id = 'subject-1'; primary_teacher_id = 'teacher-1'
            weekly_slots = 2; duration_slots = 1; status = 'active'
            week_bits = '11111111111111111111'; day_bits = '11111'
        }
    }
    $revision = [int]$taskSaved.revision
    if (@($taskSaved.lessons).Count -ne 2) { throw '教学任务没有原子生成两条课次。' }
    Write-Output 'PASS 项目、基础数据与课程计划持久化'

    $preflight = Invoke-SidecarApi -Method POST -Path '/v1/validation/preflight'
    if (-not $preflight.ready -or $preflight.summary.activeLessonCount -ne 2 -or @($preflight.errors).Count -ne 0) {
        throw '排课预检未通过。'
    }
    Write-Output 'PASS 排课前只读预检'

    $firstStarted = (Invoke-SidecarApi -Method POST -Path '/v1/scheduling/rounds' -Body @{
        time_budget_seconds = 10; random_seed = 7; name = '冻结首轮'
    }).round
    $first = Wait-SchedulingRound -RoundId ([string]$firstStarted.id)
    if ($first.status -ne 'succeeded' -or [string]::IsNullOrWhiteSpace([string]$first.candidate_id) -or $first.hard_violations -ne 0) {
        throw "首轮排课失败，状态：$($first.status)"
    }
    $firstCandidateId = [string]$first.candidate_id
    $firstSessionId = [string]$first.session_id
    $timetable = Invoke-SidecarApi -Method GET -Path "/v1/timetables/$firstCandidateId"
    if (@($timetable.items).Count -ne 2 -or $timetable.candidate.hard_violations -ne 0) {
        throw '首轮候选课表数量或硬约束结果无效。'
    }

    $secondStarted = (Invoke-SidecarApi -Method POST -Path '/v1/scheduling/rounds' -Body @{
        time_budget_seconds = 10; random_seed = 8; name = '冻结续轮'
        session_id = $firstSessionId; parent_candidate_id = $firstCandidateId
    }).round
    $second = Wait-SchedulingRound -RoundId ([string]$secondStarted.id)
    if ($second.status -ne 'succeeded' -or $second.parent_candidate_id -ne $firstCandidateId -or $second.hard_violations -ne 0) {
        throw '基于指定候选的 warm start 续轮失败。'
    }
    $candidateId = [string]$second.candidate_id
    if (@((Invoke-SidecarApi -Method GET -Path "/v1/scheduling/rounds?session_id=$firstSessionId").items).Count -ne 2) {
        throw '同一排课会话没有保留两轮记录。'
    }
    Write-Output 'PASS 本地异步排课、零硬违例候选与 warm start'

    $exportDefinitions = @(
        @{ Type = 'csv'; Name = '课表.csv'; Magic = [byte[]](0xEF, 0xBB, 0xBF) },
        @{ Type = 'xlsx'; Name = '课表.xlsx'; Magic = [byte[]](0x50, 0x4B) },
        @{ Type = 'pdf'; Name = '课表.pdf'; Magic = [byte[]](0x25, 0x50, 0x44, 0x46) },
        @{ Type = 'problem_xml'; Name = '排课问题.xml'; Root = 'problem' },
        @{ Type = 'solution_xml'; Name = '排课结果.xml'; Root = 'solution' }
    )
    foreach ($definition in $exportDefinitions) {
        $destination = Join-Path $outputs $definition.Name
        $exported = (Invoke-SidecarApi -Method POST -Path '/v1/exports' -Body @{
            candidate_id = $candidateId; export_type = $definition.Type
            destination_path = $destination; overwrite = $false
        }).export
        if ([string]$exported.status -ne 'succeeded' -or -not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            throw "$($definition.Type) 导出失败。"
        }
        if ($null -ne $definition.Magic) {
            Assert-FileMagic -Path $destination -Expected $definition.Magic -Label $definition.Type
        }
        else {
            [xml]$xml = Get-Content -LiteralPath $destination -Raw -Encoding UTF8
            if ($xml.DocumentElement.LocalName -ne $definition.Root) { throw "$($definition.Type) XML 根节点无效。" }
        }
    }
    if (@((Invoke-SidecarApi -Method GET -Path '/v1/exports').items).Count -ne 5) {
        throw '导出记录数量不是 5。'
    }
    Write-Output 'PASS CSV、XLSX、PDF、Problem XML 与 Solution XML 导出'

    $backupPath = Join-Path $outputs '完整备份.sttbackup'
    $backup = (Invoke-SidecarApi -Method POST -Path '/v1/backups' -Body @{
        reason = 'frozen-workflow'; retained = $true; destination_path = $backupPath
    }).backup
    Assert-FileMagic -Path $backupPath -Expected ([byte[]](0x50, 0x4B)) -Label 'sttbackup'
    $verified = Invoke-SidecarApi -Method POST -Path "/v1/backups/$($backup.id)/verify"
    if (-not $backup.verified -or -not $verified.valid) { throw '备份创建后校验失败。' }

    $archivePath = Join-Path $outputs '完整项目.sttproj'
    $archive = (Invoke-SidecarApi -Method POST -Path '/v1/project-archives/export' -Body @{
        destination_path = $archivePath; overwrite = $false
    }).package
    Assert-FileMagic -Path $archivePath -Expected ([byte[]](0x50, 0x4B)) -Label 'sttproj'
    if (-not $archive.verified) { throw '项目归档自校验失败。' }

    $restored = Invoke-SidecarApi -Method POST -Path '/v1/backups/restore' -Body @{
        backup_id = $backup.id; restored_name = '冻结恢复副本'; confirmed = $true
    }
    if ($restored.project.id -eq $sourceProjectId -or @((Invoke-SidecarApi -Method GET -Path '/v1/data/teacher').items).Count -ne 1) {
        throw '备份恢复未创建独立且完整的项目。'
    }
    $null = Invoke-SidecarApi -Method POST -Path '/v1/projects/current/close'

    $imported = Invoke-SidecarApi -Method POST -Path '/v1/project-archives/import' -Body @{
        archive_path = $archivePath; imported_name = '冻结归档副本'; confirmed = $true
    }
    if ($imported.project.id -eq $sourceProjectId -or @((Invoke-SidecarApi -Method GET -Path '/v1/scheduling/candidates').items).Count -lt 2) {
        throw '项目归档导入未保留候选数据。'
    }
    if (@((Invoke-SidecarApi -Method GET -Path '/v1/projects').projects).Count -ne 3) {
        throw '源项目、恢复副本和归档副本数量不正确。'
    }
    Write-Output 'PASS .sttbackup 校验/恢复与 .sttproj 导出/导入'

    $null = Invoke-SidecarApi -Method POST -Path '/v1/projects/current/close'
    $shutdown = Invoke-SidecarApi -Method POST -Path '/v1/runtime/shutdown'
    if ($shutdown.status -ne 'shutting_down') { throw 'Sidecar 拒绝授权关闭。' }
    $shutdownDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $launcherAlive = [bool](Get-Process -Id $process.Id -ErrorAction SilentlyContinue)
        $workerAlive = [bool](Get-Process -Id ([int]$ready.workerPid) -ErrorAction SilentlyContinue)
        if (-not $launcherAlive -and -not $workerAlive) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $shutdownDeadline)
    if ($launcherAlive -or $workerAlive) { throw '授权关闭后仍有 Sidecar 进程。' }
    Write-Output 'PASS 授权关闭与 launcher/worker 零残留'

    [pscustomobject]@{
        Status = 'passed'
        ProtocolVersion = $health.protocolVersion
        ProjectCount = 3
        SchedulingRounds = 2
        CandidateEntries = 2
        HardViolations = 0
        ExportCount = 5
        BackupVerified = [bool]$verified.valid
        ArchiveVerified = [bool]$archive.verified
        LauncherExited = -not $launcherAlive
        WorkerExited = -not $workerAlive
    }
}
finally {
    if ($process) { Stop-ExactSidecarProcess $process.Id }
    if ($ready) { Stop-ExactSidecarProcess ([int]$ready.workerPid) }
    Start-Sleep -Milliseconds 300
    if (Test-Path -LiteralPath $testRoot -PathType Container) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        if (
            (Split-Path -Parent $resolvedTestRoot) -ne $temporaryRoot -or
            -not (Split-Path -Leaf $resolvedTestRoot).StartsWith('stt-frozen-workflow-')
        ) {
            throw "拒绝清理未验证的冻结全流程临时目录：$resolvedTestRoot"
        }
        $cleanupError = $null
        foreach ($attempt in 1..10) {
            try {
                Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force -ErrorAction Stop
                $cleanupError = $null
                break
            }
            catch {
                $cleanupError = $_
                Start-Sleep -Milliseconds 200
            }
        }
        if ($cleanupError) { throw $cleanupError }
    }
}
