[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$AssetDirectory,
    [Parameter(Mandatory)][ValidateSet('nsis', 'msi')][string]$InstallerKind,
    [Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{40}$')][string]$ExpectedThumbprint,
    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw '此验收脚本只能在 Windows 上运行。' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '干净 Windows 自动安装验收需要管理员上下文；普通用户应通过系统证书对话框人工确认测试证书。'
}
$assetRoot = (Resolve-Path -LiteralPath $AssetDirectory).Path
$manifestPath = Join-Path $assetRoot 'windows-release-manifest.json'
$certificatePath = Join-Path $assetRoot 'Karios-Desktop-TEST-ONLY.cer'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw '缺少 Windows release manifest。' }
if (-not (Test-Path -LiteralPath $certificatePath -PathType Leaf)) { throw '缺少测试签名公开证书。' }

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.format -ne 'tech.karios.windows-release/v1' -or
    $manifest.application.identifier -ne 'tech.karios.stt.desktop' -or
    $manifest.application.target -ne 'windows-x86_64') {
    throw 'release manifest 的格式、应用标识或目标架构无效。'
}
$extension = if ($InstallerKind -eq 'nsis') { '.exe' } else { '.msi' }
$artifact = @($manifest.artifacts | Where-Object { $_.fileName.EndsWith($extension) })
if ($artifact.Count -ne 1) { throw "manifest 中没有唯一的 $InstallerKind 安装包。" }
$installerPath = Join-Path $assetRoot $artifact[0].fileName
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) { throw '下载目录缺少安装包。' }

function Assert-FileEvidence {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][long]$ExpectedSize,
        [Parameter(Mandatory)][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$Label
    )

    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne $ExpectedSize) { throw "$Label 文件大小与 manifest 不符。" }
    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actualHash -ne $ExpectedSha256.ToUpperInvariant()) { throw "$Label SHA-256 与 manifest 不符。" }
    return $actualHash
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
                    RegistryPath = $_.PSPath
                    ProductCode = $_.PSChildName
                    DisplayName = $entry.DisplayName
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

function Test-MachineCertificate {
    param([Parameter(Mandatory)][string]$StoreName, [Parameter(Mandatory)][string]$Thumbprint)

    $store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine
    )
    try {
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
        return $store.Certificates.Find(
            [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
            $Thumbprint,
            $false
        ).Count -gt 0
    }
    finally { $store.Close() }
}

function Add-MachineCertificate {
    param(
        [Parameter(Mandatory)][string]$StoreName,
        [Parameter(Mandatory)][string]$CertificatePath,
        [Parameter(Mandatory)][string]$Thumbprint
    )

    $exitCode = Start-AndWait -FilePath 'certutil.exe' -ArgumentList @('-f', '-addstore', $StoreName, $CertificatePath) -TimeoutSeconds 60 -Phase "导入 LocalMachine/$StoreName 测试证书"
    if ($exitCode -ne 0 -or -not (Test-MachineCertificate -StoreName $StoreName -Thumbprint $Thumbprint)) {
        throw "无法把测试证书导入 LocalMachine/$StoreName。"
    }
}

function Remove-MachineCertificate {
    param([Parameter(Mandatory)][string]$StoreName, [Parameter(Mandatory)][string]$Thumbprint)

    $exitCode = Start-AndWait -FilePath 'certutil.exe' -ArgumentList @('-delstore', $StoreName, $Thumbprint) -TimeoutSeconds 60 -Phase "移除 LocalMachine/$StoreName 测试证书"
    if ($exitCode -ne 0 -or (Test-MachineCertificate -StoreName $StoreName -Thumbprint $Thumbprint)) {
        throw "无法从 LocalMachine/$StoreName 移除测试证书。"
    }
}

function Resolve-InstallDirectory {
    param([Parameter(Mandatory)][object]$Entry)

    if (-not [string]::IsNullOrWhiteSpace([string]$Entry.InstallLocation) -and
        (Test-Path -LiteralPath $Entry.InstallLocation -PathType Container)) {
        return (Resolve-Path -LiteralPath $Entry.InstallLocation).Path
    }
    $displayIcon = ([string]$Entry.DisplayIcon).Trim().Trim('"') -replace ',\d+$', ''
    if (Test-Path -LiteralPath $displayIcon -PathType Leaf) {
        return (Split-Path -Parent (Resolve-Path -LiteralPath $displayIcon).Path)
    }
    $uninstall = [string]$Entry.UninstallString
    if ($uninstall -match '^"([^"]+)"') { $uninstallExecutable = $Matches[1] }
    else { $uninstallExecutable = ($uninstall -split '\s+')[0] }
    if (Test-Path -LiteralPath $uninstallExecutable -PathType Leaf) {
        return Split-Path -Parent (Resolve-Path -LiteralPath $uninstallExecutable).Path
    }
    throw '无法从卸载注册表项确定安装目录。'
}

function Assert-SignedFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ExpectedThumbprint,
        [Parameter(Mandatory)][bool]$RequireTrusted
    )

    $job = Start-Job -ScriptBlock {
        param($TargetPath)
        $signature = Get-AuthenticodeSignature -LiteralPath $TargetPath
        [pscustomobject]@{
            Status = $signature.Status.ToString()
            SignerThumbprint = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint } else { $null }
            HasTimestamp = [bool]$signature.TimeStamperCertificate
        }
    } -ArgumentList $Path
    try {
        if (-not (Wait-Job -Job $job -Timeout 45)) {
            Stop-Job -Job $job
            throw "Authenticode 验证超过 45 秒：$Path"
        }
        $signature = Receive-Job -Job $job
    }
    finally {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
    if (-not $signature.SignerThumbprint) { throw "文件没有 Authenticode 签名：$Path" }
    if ($signature.SignerThumbprint -ne $ExpectedThumbprint) { throw "文件签名指纹不符：$Path" }
    if (-not $signature.HasTimestamp) { throw "文件缺少时间戳：$Path" }
    if ($signature.Status -eq 'HashMismatch') {
        throw "文件 Authenticode 哈希不匹配：$Path"
    }
    if ($RequireTrusted -and $signature.Status -ne 'Valid') {
        throw "信任证书后签名仍无效（$($signature.Status)）：$Path"
    }
    return $signature.Status
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

function Stop-ExactProcess {
    param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][string]$ExpectedPath)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return }
    $actual = (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").ExecutablePath
    if ($actual -eq $ExpectedPath) { Stop-Process -Id $ProcessId -Force }
}

function Invoke-ProductUninstall {
    param([Parameter(Mandatory)][object]$Entry, [Parameter(Mandatory)][string]$Kind)

    if ($Kind -eq 'msi') {
        $productCode = if ([string]$Entry.ProductCode -match '^\{[0-9A-Fa-f-]{36}\}$') {
            [string]$Entry.ProductCode
        }
        elseif ([string]$Entry.UninstallString -match '\{[0-9A-Fa-f-]{36}\}') {
            $Matches[0]
        }
        else { throw 'MSI 卸载注册表项缺少有效 ProductCode。' }
        $exitCode = Start-AndWait -FilePath 'msiexec.exe' -ArgumentList @('/x', $productCode, '/qn', '/norestart') -Phase 'MSI 卸载'
    }
    else {
        $command = [string]$Entry.UninstallString
        if ($command -match '^"([^"]+)"') { $executable = $Matches[1] }
        else { $executable = ($command -split '\s+')[0] }
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'NSIS 卸载程序不存在。' }
        $exitCode = Start-AndWait -FilePath $executable -ArgumentList @('/S') -Phase 'NSIS 卸载'
    }
    if ($exitCode -notin @(0, 3010)) { throw "卸载失败，退出码：$exitCode" }
}

$installerHash = Assert-FileEvidence -Path $installerPath -ExpectedSize $artifact[0].sizeBytes -ExpectedSha256 $artifact[0].sha256 -Label $InstallerKind
$certificateEvidence = @($manifest.additionalEvidence | Where-Object { $_.fileName -eq 'Karios-Desktop-TEST-ONLY.cer' })
if ($certificateEvidence.Count -ne 1) { throw 'manifest 缺少唯一测试证书证据。' }
$null = Assert-FileEvidence -Path $certificatePath -ExpectedSize $certificateEvidence[0].sizeBytes -ExpectedSha256 $certificateEvidence[0].sha256 -Label '测试证书'
$expectedThumbprint = $ExpectedThumbprint.ToUpperInvariant()
if ([string]$manifest.signing.authenticodeThumbprint -ne $expectedThumbprint) {
    throw 'manifest 签名指纹与独立预期值不符。'
}
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certificatePath)
if ($certificate.Thumbprint -ne $expectedThumbprint) { throw '公开证书指纹与 manifest 不符。' }

Write-Output 'PHASE release manifest、大小与 SHA-256 验证通过'
$preTrustStatus = Assert-SignedFile -Path $installerPath -ExpectedThumbprint $expectedThumbprint -RequireTrusted $false
if ($preTrustStatus -eq 'Valid') { throw '全新 Runner 在导入测试证书前已信任自签名安装包。' }
Write-Output "PHASE 导入前签名状态符合预期：$preTrustStatus"

$trustedStores = @('Root', 'TrustedPublisher')
$storesImportedByTest = [System.Collections.Generic.List[string]]::new()
$installedEntry = $null
$installDirectory = $null
$mainProcess = $null
$sentinelRoot = Join-Path $env:APPDATA 'tech.karios.stt.desktop\Workspace\projects\install-uninstall-sentinel'
$sentinelPath = Join-Path $sentinelRoot 'manifest.json'
$result = $null

try {
    foreach ($store in $trustedStores) {
        if (-not (Test-MachineCertificate -StoreName $store -Thumbprint $expectedThumbprint)) {
            Add-MachineCertificate -StoreName $store -CertificatePath $certificatePath -Thumbprint $expectedThumbprint
            $storesImportedByTest.Add($store)
        }
    }
    $postTrustStatus = Assert-SignedFile -Path $installerPath -ExpectedThumbprint $expectedThumbprint -RequireTrusted $true
    Write-Output 'PHASE 临时机器信任后 Authenticode 有效'

    if (@(Get-ProductEntry).Count -ne 0) { throw '全新 Runner 在测试前已有同名产品。' }
    if ($InstallerKind -eq 'nsis') {
        $installExitCode = Start-AndWait -FilePath $installerPath -ArgumentList @('/S') -Phase 'NSIS 安装'
    }
    else {
        $installExitCode = Start-AndWait -FilePath 'msiexec.exe' -ArgumentList @('/i', $installerPath, '/qn', '/norestart') -Phase 'MSI 安装'
    }
    if ($installExitCode -notin @(0, 3010)) { throw "安装失败，退出码：$installExitCode" }
    Start-Sleep -Seconds 2
    Write-Output 'PHASE 静默安装完成'

    $entries = @(Get-ProductEntry)
    if ($entries.Count -ne 1) { throw "安装后发现 $($entries.Count) 个产品注册表项。" }
    $installedEntry = $entries[0]
    if ([string]$installedEntry.DisplayVersion -ne [string]$manifest.application.version) {
        throw '安装后的 DisplayVersion 与 manifest 不符。'
    }
    $installDirectory = Resolve-InstallDirectory -Entry $installedEntry
    $mainExecutable = Get-ChildItem -LiteralPath $installDirectory -Filter 'karios-stt-desktop.exe' -File -Recurse | Select-Object -First 1
    $sidecarExecutable = Get-ChildItem -LiteralPath $installDirectory -Filter 'stt-sidecar.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $mainExecutable -or $null -eq $sidecarExecutable) { throw '安装目录缺少桌面主程序或 Sidecar。' }
    $null = Assert-SignedFile -Path $mainExecutable.FullName -ExpectedThumbprint $expectedThumbprint -RequireTrusted $true
    $null = Assert-SignedFile -Path $sidecarExecutable.FullName -ExpectedThumbprint $expectedThumbprint -RequireTrusted $true
    Write-Output 'PHASE 安装注册表、版本与内层双签名验证通过'

    $mainProcess = Start-Process -FilePath $mainExecutable.FullName -PassThru
    Start-Sleep -Seconds 5
    if ($mainProcess.HasExited) { throw "安装后的桌面主程序提前退出，代码：$($mainProcess.ExitCode)" }
    Stop-ExactProcess -ProcessId $mainProcess.Id -ExpectedPath $mainExecutable.FullName
    $mainProcess.WaitForExit(5000) | Out-Null
    Write-Output 'PHASE 桌面主程序启动存活检查通过'

    if (Test-Path -LiteralPath $sentinelRoot) { throw '测试哨兵目录已存在，拒绝覆盖用户数据。' }
    New-Item -ItemType Directory -Path $sentinelRoot -Force | Out-Null
    $sentinelContent = '{"kind":"uninstall-preservation-sentinel","containsBusinessData":false}'
    [System.IO.File]::WriteAllText($sentinelPath, $sentinelContent, [System.Text.UTF8Encoding]::new($false))
    $sentinelHash = (Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash

    Invoke-ProductUninstall -Entry $installedEntry -Kind $InstallerKind
    $installedEntry = $null
    Start-Sleep -Seconds 2
    if (@(Get-ProductEntry).Count -ne 0) { throw '卸载后产品注册表项仍然存在。' }
    if (Test-Path -LiteralPath $mainExecutable.FullName -PathType Leaf) { throw '卸载后桌面主程序仍然存在。' }
    if (-not (Test-Path -LiteralPath $sentinelPath -PathType Leaf)) { throw '卸载删除了用户工作区数据。' }
    if ((Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $sentinelHash) {
        throw '卸载修改了用户工作区数据。'
    }
    Write-Output 'PHASE 静默卸载与用户工作区保留检查通过'

    $os = Get-CimInstance Win32_OperatingSystem
    $result = [ordered]@{
        status = 'passed'
        osCaption = $os.Caption
        osVersion = $os.Version
        runnerArchitecture = $env:PROCESSOR_ARCHITECTURE
        packageTarget = $manifest.application.target
        installerKind = $InstallerKind
        applicationVersion = $manifest.application.version
        installerSha256 = $installerHash
        signerThumbprint = $expectedThumbprint
        preTrustStatus = $preTrustStatus
        postTrustStatus = $postTrustStatus
        installedExecutablesVerified = 2
        applicationLaunch = 'passed'
        uninstall = 'passed'
        userWorkspacePreserved = $true
    }
    $result | ConvertTo-Json -Depth 5
    if (-not [string]::IsNullOrWhiteSpace($EvidencePath)) {
        $evidenceParent = Split-Path -Parent $EvidencePath
        if ($evidenceParent) { New-Item -ItemType Directory -Path $evidenceParent -Force | Out-Null }
        [System.IO.File]::WriteAllText($EvidencePath, ($result | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    }
}
finally {
    if ($mainProcess -and -not $mainProcess.HasExited) {
        $expectedMainPath = (Get-CimInstance Win32_Process -Filter "ProcessId = $($mainProcess.Id)" -ErrorAction SilentlyContinue).ExecutablePath
        if ($expectedMainPath) { Stop-ExactProcess -ProcessId $mainProcess.Id -ExpectedPath $expectedMainPath }
    }
    if ($installedEntry) {
        try { Invoke-ProductUninstall -Entry $installedEntry -Kind $InstallerKind } catch { Write-Warning '失败清理：测试产品仍可能安装在临时 Runner。' }
    }
    if (Test-Path -LiteralPath $sentinelRoot -PathType Container) {
        $resolvedSentinel = (Resolve-Path -LiteralPath $sentinelRoot).Path
        $expectedParent = (Join-Path $env:APPDATA 'tech.karios.stt.desktop\Workspace\projects')
        if ((Split-Path -Parent $resolvedSentinel) -eq $expectedParent -and (Split-Path -Leaf $resolvedSentinel) -eq 'install-uninstall-sentinel') {
            Remove-Item -LiteralPath $resolvedSentinel -Recurse -Force
        }
    }
    foreach ($store in $storesImportedByTest) {
        Remove-MachineCertificate -StoreName $store -Thumbprint $expectedThumbprint
    }
}
