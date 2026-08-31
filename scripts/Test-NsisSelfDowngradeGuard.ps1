[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallerPath,
    [version]$SimulatedInstalledVersion = [version]'9.0.0',
    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'NSIS 防降级测试只能在 Windows 上运行。' }

$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\时奕教务排课'
$installDirectory = Join-Path $env:LOCALAPPDATA '时奕教务排课'
$testMarker = [Guid]::NewGuid().ToString('N')
$createdKey = $false

if (Test-Path -LiteralPath $uninstallKey) {
    throw '测试前已存在时奕教务排课 HKCU 卸载注册项，拒绝覆盖。'
}
if (Test-Path -LiteralPath $installDirectory) {
    throw '测试前已存在时奕教务排课安装目录，拒绝运行。'
}

try {
    New-Item -Path $uninstallKey -Force | Out-Null
    $createdKey = $true
    Set-ItemProperty -LiteralPath $uninstallKey -Name DisplayName -Value '时奕教务排课'
    Set-ItemProperty -LiteralPath $uninstallKey -Name DisplayVersion -Value $SimulatedInstalledVersion.ToString()
    Set-ItemProperty -LiteralPath $uninstallKey -Name KariosGuardTestMarker -Value $testMarker

    $process = Start-Process -FilePath $resolvedInstaller -ArgumentList @('/S') -PassThru
    if (-not $process.WaitForExit(60000)) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
        throw 'NSIS 防降级测试超过 60 秒。'
    }
    $process.Refresh()

    $state = Get-ItemProperty -LiteralPath $uninstallKey
    if ($process.ExitCode -ne 10) {
        throw "期望防降级退出码 10，实际 $($process.ExitCode)。"
    }
    if ([string]$state.DisplayVersion -ne $SimulatedInstalledVersion.ToString()) {
        throw 'NSIS 修改了模拟的较新版本注册项。'
    }
    if (Test-Path -LiteralPath $installDirectory) {
        throw 'NSIS 防降级失败：安装目录已被创建。'
    }

    $result = [ordered]@{
        status = 'passed'
        installerPath = $resolvedInstaller
        simulatedInstalledVersion = $SimulatedInstalledVersion.ToString()
        downgradeAttemptExitCode = $process.ExitCode
        registryVersionPreserved = $true
        installDirectoryCreated = $false
    }
    $result | ConvertTo-Json -Depth 3
    if ($EvidencePath) {
        $parent = Split-Path -Parent $EvidencePath
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        [System.IO.File]::WriteAllText(
            $EvidencePath,
            ($result | ConvertTo-Json -Depth 3),
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}
finally {
    if ($createdKey -and (Test-Path -LiteralPath $uninstallKey)) {
        $state = Get-ItemProperty -LiteralPath $uninstallKey -ErrorAction Stop
        if ([string]$state.KariosGuardTestMarker -ne $testMarker) {
            throw '测试注册项标记不匹配，拒绝清理。'
        }
        Remove-Item -LiteralPath $uninstallKey -Recurse -Force
    }
}
