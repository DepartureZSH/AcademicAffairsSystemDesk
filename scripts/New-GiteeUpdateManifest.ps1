[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$NsisPath,
    [string]$MsiPath,
    [Parameter(Mandatory)][string]$NotesPath,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$crate = Join-Path $repositoryRoot 'apps\desktop\src-tauri'
$configPath = Join-Path $crate 'tauri.conf.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$version = $config.version
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') { throw '版本号格式不支持' }
if (Test-Path -LiteralPath $OutputDirectory) { throw '输出目录已存在，请选择新目录，避免覆盖已发布文件' }
$notes = Get-Content -LiteralPath $NotesPath -Raw -Encoding UTF8
$platforms = [ordered]@{}
$verified = @()
foreach ($item in @(@{ Path = $NsisPath; Kind = 'nsis'; Extension = '.exe' }, @{ Path = $MsiPath; Kind = 'msi'; Extension = '.msi' })) {
    if (-not $item.Path) { continue }
    $artifact = Get-Item -LiteralPath $item.Path
    if ($artifact.Extension -ne $item.Extension -or $artifact.Name -notlike "*_${version}_*") { throw '安装包名称、类型或版本与当前项目不一致' }
    $signaturePath = "$($artifact.FullName).sig"
    if (-not (Test-Path -LiteralPath $signaturePath)) { throw "缺少对应签名：$signaturePath" }
    Push-Location $crate
    try {
        & cargo run --quiet --offline --example verify_updater_signature -- $artifact.FullName $signaturePath $configPath
        if ($LASTEXITCODE -ne 0) { throw '安装包签名与当前公钥不匹配，拒绝生成清单' }
    } finally { Pop-Location }
    $name = if ($item.Kind -eq 'nsis') { "STT_${version}_x64-setup.exe" } else { "STT_${version}_x64_zh-CN.msi" }
    $entry = [ordered]@{
        url = "https://gitee.com/hangzhou-greos-time/academic-affairs-system-desk/releases/download/v$version/$name"
        signature = (Get-Content -LiteralPath $signaturePath -Raw).Trim()
    }
    $platforms["windows-x86_64-$($item.Kind)"] = $entry
    if ($item.Kind -eq 'nsis') { $platforms['windows-x86_64'] = $entry }
    $verified += @{ Source = $artifact.FullName; Signature = $signaturePath; Name = $name }
}
$output = New-Item -ItemType Directory -Path $OutputDirectory
Copy-Item -LiteralPath $NotesPath -Destination (Join-Path $output.FullName 'RELEASE-NOTES.md')
foreach ($item in $verified) {
    Copy-Item -LiteralPath $item.Source -Destination (Join-Path $output.FullName $item.Name)
    Copy-Item -LiteralPath $item.Signature -Destination (Join-Path $output.FullName "$($item.Name).sig")
}
$manifest = [ordered]@{ version = $version; notes = $notes; pub_date = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'); platforms = $platforms }
[System.IO.File]::WriteAllText((Join-Path $output.FullName 'latest-beta.json'), ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
Get-ChildItem -LiteralPath $output.FullName -File | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
} | Set-Content -LiteralPath (Join-Path $output.FullName 'SHA256SUMS.txt') -Encoding utf8
Write-Host "已校验签名并生成发布目录：$($output.FullName)"
Write-Host '将目录内全部附件上传至同名 Gitee Release；不要将新签名配给历史安装包。客户端查询和下载不需要访问令牌。'
