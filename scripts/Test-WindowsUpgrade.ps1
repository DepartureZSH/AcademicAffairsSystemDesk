[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PreviousAssetDirectory,
    [Parameter(Mandatory)][string]$CurrentAssetDirectory,
    [Parameter(Mandatory)][ValidateSet('nsis', 'msi')][string]$InstallerKind,
    [Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{40}$')][string]$ExpectedThumbprint,
    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw '升级验收脚本只能在 Windows 上运行。' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '升级验收需要管理员上下文。'
}

function Start-AndWait {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int]$TimeoutSeconds = 180,
        [Parameter(Mandatory)][string]$Phase
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
        throw "$Phase 超过 $TimeoutSeconds 秒。"
    }
    $process.Refresh()
    return $process.ExitCode
}

function Get-ReleaseEvidence {
    param([Parameter(Mandatory)][string]$Directory)
    $root = (Resolve-Path -LiteralPath $Directory).Path
    $manifestPath = Join-Path $root 'windows-release-manifest.json'
    $certificatePath = Join-Path $root 'Karios-Desktop-TEST-ONLY.cer'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $certificatePath -PathType Leaf)) {
        throw '发布资产缺少 manifest 或测试证书。'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.format -ne 'tech.karios.windows-release/v1' -or
        $manifest.application.identifier -ne 'tech.karios.stt.desktop' -or
        $manifest.application.target -ne 'windows-x86_64') {
        throw '发布 manifest 的格式、应用标识或目标架构无效。'
    }
    if ([string]$manifest.signing.authenticodeThumbprint -ne $ExpectedThumbprint.ToUpperInvariant()) {
        throw '发布 manifest 的签名指纹与独立预期值不符。'
    }
    $extension = if ($InstallerKind -eq 'nsis') { '.exe' } else { '.msi' }
    $artifacts = @($manifest.artifacts | Where-Object { $_.fileName.EndsWith($extension) })
    if ($artifacts.Count -ne 1) { throw "发布 manifest 中没有唯一的 $InstallerKind 安装包。" }
    $installerPath = Join-Path $root $artifacts[0].fileName
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) { throw '发布目录缺少安装包。' }
    $item = Get-Item -LiteralPath $installerPath
    $hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash
    if ($item.Length -ne $artifacts[0].sizeBytes -or $hash -ne [string]$artifacts[0].sha256) {
        throw '安装包大小或 SHA-256 与 manifest 不符。'
    }
    [pscustomobject]@{
        Version = [version]$manifest.application.version
        InstallerPath = $installerPath
        InstallerSha256 = $hash
        CertificatePath = $certificatePath
    }
}

function Get-ProductEntry {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    $matches = foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | ForEach-Object {
            $entry = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
            if ($entry.DisplayName -eq '时奕教务排课') {
                [pscustomobject]@{
                    ProductCode = $_.PSChildName
                    DisplayVersion = $entry.DisplayVersion
                    InstallLocation = $entry.InstallLocation
                    DisplayIcon = $entry.DisplayIcon
                    UninstallString = $entry.UninstallString
                }
            }
        }
    }
    return @($matches)
}

function Resolve-InstallDirectory {
    param([Parameter(Mandatory)][object]$Entry)
    if ($Entry.InstallLocation -and (Test-Path -LiteralPath $Entry.InstallLocation -PathType Container)) {
        return (Resolve-Path -LiteralPath $Entry.InstallLocation).Path
    }
    $displayIcon = ([string]$Entry.DisplayIcon).Trim().Trim('"') -replace ',\d+$', ''
    if (Test-Path -LiteralPath $displayIcon -PathType Leaf) {
        return Split-Path -Parent (Resolve-Path -LiteralPath $displayIcon).Path
    }
    throw '无法确定安装目录。'
}

function Install-Package {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Phase,
        [switch]$Update
    )
    if ($InstallerKind -eq 'nsis') {
        $arguments = if ($Update) { @('/P', '/R') } else { @('/S') }
        return Start-AndWait -FilePath $Path -ArgumentList $arguments -Phase $Phase
    }
    $displayMode = if ($Update) { '/passive' } else { '/qn' }
    return Start-AndWait -FilePath 'msiexec.exe' -ArgumentList @('/i', $Path, $displayMode, '/norestart') -Phase $Phase
}

function Uninstall-Product {
    param([Parameter(Mandatory)][object]$Entry)
    if ($InstallerKind -eq 'msi') {
        $code = if ([string]$Entry.ProductCode -match '^\{[0-9A-Fa-f-]{36}\}$') {
            [string]$Entry.ProductCode
        }
        elseif ([string]$Entry.UninstallString -match '\{[0-9A-Fa-f-]{36}\}') { $Matches[0] }
        else { throw 'MSI 缺少 ProductCode。' }
        $exitCode = Start-AndWait -FilePath 'msiexec.exe' -ArgumentList @('/x', $code, '/qn', '/norestart') -Phase '卸载新版'
    }
    else {
        $command = [string]$Entry.UninstallString
        if ($command -match '^"([^"]+)"') { $executable = $Matches[1] }
        else { $executable = ($command -split '\s+')[0] }
        $exitCode = Start-AndWait -FilePath $executable -ArgumentList @('/S') -Phase '卸载新版'
    }
    if ($exitCode -notin @(0, 3010)) { throw "卸载失败，退出码 $exitCode。" }
}

function Assert-InstalledVersion {
    param(
        [Parameter(Mandatory)][version]$ExpectedVersion,
        [Parameter(Mandatory)][string]$Context
    )
    $entries = @(Get-ProductEntry)
    if ($entries.Count -ne 1) { throw "$Context：期望一个产品注册表项，实际 $($entries.Count) 个。" }
    if ([version]$entries[0].DisplayVersion -ne $ExpectedVersion) {
        throw "$Context：期望版本 $ExpectedVersion，实际 $($entries[0].DisplayVersion)。"
    }
    Write-Host "PASS $Context：$ExpectedVersion"
    return $entries[0]
}

$previous = Get-ReleaseEvidence -Directory $PreviousAssetDirectory
$current = Get-ReleaseEvidence -Directory $CurrentAssetDirectory
if ($previous.Version -ge $current.Version) { throw '旧版版本号必须低于新版。' }
$expectedThumbprint = $ExpectedThumbprint.ToUpperInvariant()
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($current.CertificatePath)
if ($certificate.Thumbprint -ne $expectedThumbprint) { throw '测试证书指纹无效。' }

$trustedStores = @('Root', 'TrustedPublisher')
$importedStores = [System.Collections.Generic.List[string]]::new()
$installedEntry = $null
$sentinelRoot = Join-Path $env:APPDATA 'tech.karios.stt.desktop\Workspace\projects\upgrade-sentinel'
$sentinelPath = Join-Path $sentinelRoot 'manifest.json'
try {
    foreach ($store in $trustedStores) {
        $certificatePath = "Cert:\LocalMachine\$store\$expectedThumbprint"
        if (-not (Test-Path -LiteralPath $certificatePath)) {
            $exitCode = Start-AndWait -FilePath 'certutil.exe' -ArgumentList @('-f', '-addstore', $store, $current.CertificatePath) -TimeoutSeconds 60 -Phase "导入 $store 测试证书"
            if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $certificatePath)) { throw "导入 $store 测试证书失败。" }
            $importedStores.Add($store)
        }
    }
    if (@(Get-ProductEntry).Count -ne 0) { throw '测试前已有同名产品。' }
    if (Test-Path -LiteralPath $sentinelRoot) { throw '测试前已有升级哨兵。' }

    $oldExitCode = Install-Package -Path $previous.InstallerPath -Phase '安装旧版'
    if ($oldExitCode -notin @(0, 3010)) { throw "旧版安装失败，退出码 $oldExitCode。" }
    $installedEntry = Assert-InstalledVersion -ExpectedVersion $previous.Version -Context '旧版安装后检查'

    New-Item -ItemType Directory -Path $sentinelRoot -Force | Out-Null
    [System.IO.File]::WriteAllText($sentinelPath, '{"kind":"upgrade-sentinel","containsBusinessData":false}', [System.Text.UTF8Encoding]::new($false))
    $sentinelHash = (Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash

    $upgradeExitCode = Install-Package -Path $current.InstallerPath -Phase '升级新版' -Update
    if ($upgradeExitCode -notin @(0, 3010)) { throw "升级失败，退出码 $upgradeExitCode。" }
    $installedEntry = Assert-InstalledVersion -ExpectedVersion $current.Version -Context '升级后检查'
    $installDirectory = Resolve-InstallDirectory -Entry $installedEntry
    $mainExecutable = Get-ChildItem -LiteralPath $installDirectory -Filter 'karios-stt-desktop.exe' -File -Recurse | Select-Object -First 1
    $sidecarExecutable = Get-ChildItem -LiteralPath $installDirectory -Filter 'stt-sidecar.exe' -File -Recurse | Select-Object -First 1
    if (-not $mainExecutable -or -not $sidecarExecutable) { throw '升级后缺少主程序或 Sidecar。' }
    $mainHash = (Get-FileHash -LiteralPath $mainExecutable.FullName -Algorithm SHA256).Hash
    $sidecarHash = (Get-FileHash -LiteralPath $sidecarExecutable.FullName -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $sentinelHash) { throw '升级修改了用户工作区。' }

    $downgradeExitCode = Install-Package -Path $previous.InstallerPath -Phase '尝试降级旧版' -Update
    Start-Sleep -Seconds 2
    $installedEntry = Assert-InstalledVersion -ExpectedVersion $current.Version -Context '降级尝试后检查'
    if ((Get-FileHash -LiteralPath $mainExecutable.FullName -Algorithm SHA256).Hash -ne $mainHash -or
        (Get-FileHash -LiteralPath $sidecarExecutable.FullName -Algorithm SHA256).Hash -ne $sidecarHash) {
        throw '降级尝试覆盖了新版应用文件。'
    }
    if ((Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $sentinelHash) { throw '降级尝试修改了用户工作区。' }

    Uninstall-Product -Entry $installedEntry
    $installedEntry = $null
    Start-Sleep -Seconds 2
    if (@(Get-ProductEntry).Count -ne 0) { throw '卸载后产品注册表项仍存在。' }
    if ((Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $sentinelHash) { throw '卸载没有保留用户工作区。' }

    $os = Get-CimInstance Win32_OperatingSystem
    $result = [ordered]@{
        status = 'passed'
        osCaption = $os.Caption
        osVersion = $os.Version
        installerKind = $InstallerKind
        previousVersion = $previous.Version.ToString()
        currentVersion = $current.Version.ToString()
        upgradeExitCode = $upgradeExitCode
        downgradeAttemptExitCode = $downgradeExitCode
        currentFilesPreservedAfterDowngradeAttempt = $true
        userWorkspacePreserved = $true
    }
    $result | ConvertTo-Json -Depth 4
    if ($EvidencePath) {
        $parent = Split-Path -Parent $EvidencePath
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        [System.IO.File]::WriteAllText($EvidencePath, ($result | ConvertTo-Json -Depth 4), [System.Text.UTF8Encoding]::new($false))
    }
}
finally {
    if ($installedEntry) {
        try { Uninstall-Product -Entry $installedEntry } catch { Write-Warning '失败清理：测试产品可能仍已安装。' }
    }
    if (Test-Path -LiteralPath $sentinelRoot -PathType Container) {
        $resolved = (Resolve-Path -LiteralPath $sentinelRoot).Path
        $expectedParent = Join-Path $env:APPDATA 'tech.karios.stt.desktop\Workspace\projects'
        if ((Split-Path -Parent $resolved) -eq $expectedParent -and (Split-Path -Leaf $resolved) -eq 'upgrade-sentinel') {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
    foreach ($store in $importedStores) {
        $exitCode = Start-AndWait -FilePath 'certutil.exe' -ArgumentList @('-delstore', $store, $expectedThumbprint) -TimeoutSeconds 60 -Phase "移除 $store 测试证书"
        if ($exitCode -ne 0) { Write-Warning "未能移除 $store 测试证书。" }
    }
}
