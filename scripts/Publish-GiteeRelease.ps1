[CmdletBinding()]
param([Parameter(Mandatory)][string]$ReleaseDirectory)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$manifest = Get-Content -LiteralPath (Join-Path $ReleaseDirectory 'latest-beta.json') -Raw | ConvertFrom-Json
$version = $manifest.version
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw '发布版本号无效' }
$tag = "v$version"
$commit = (& git rev-parse HEAD).Trim()
$branch = (& git branch --show-current).Trim()
if (-not $branch -or (& git status --porcelain)) { throw '必须从已提交、干净的工作区发布' }
$config = Get-Content apps/desktop/src-tauri/tauri.conf.json -Raw | ConvertFrom-Json
if ($config.version -ne $version) { throw '发布清单与源码版本不一致' }
$notes = Get-Content -LiteralPath (Join-Path $ReleaseDirectory 'RELEASE-NOTES.md') -Raw -Encoding UTF8
$tokenLine = Get-Content -LiteralPath .env | Where-Object { $_ -match '^\s*GITEE_ACCESS_TOKEN\s*=' } | Select-Object -Last 1
if (-not $tokenLine) { throw '上传需要在 .env 配置 GITEE_ACCESS_TOKEN；客户端无需此令牌' }
$token = ($tokenLine -split '=',2)[1].Trim().Trim('"').Trim("'")
if (-not $token) { throw '发布令牌为空' }
$headers = @{ Authorization = "Bearer $token" }
$api = 'https://gitee.com/api/v5'
$repo = 'hangzhou-greos-time/academic-affairs-system-desk'
try { $user = Invoke-RestMethod "$api/user" -Headers $headers -TimeoutSec 30 }
catch { throw ('发布身份验证失败，HTTP ' + [int]$_.Exception.Response.StatusCode) }
$names = @('GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0','GIT_CONFIG_KEY_1','GIT_CONFIG_VALUE_1','GIT_TERMINAL_PROMPT')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    $env:GIT_CONFIG_COUNT = '2'
    $env:GIT_CONFIG_KEY_0 = 'http.https://gitee.com/.extraheader'
    $env:GIT_CONFIG_VALUE_0 = 'Authorization: Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($user.login):$token"))
    $env:GIT_CONFIG_KEY_1 = 'credential.helper'
    $env:GIT_CONFIG_VALUE_1 = ''
    $env:GIT_TERMINAL_PROMPT = '0'
    & git push gitee "HEAD:refs/heads/$branch" "HEAD:refs/tags/$tag"
    if ($LASTEXITCODE -ne 0) { throw 'Gitee 推送失败；不会强制覆盖远端引用' }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$saved[$name]) }
}
$releases = Invoke-RestMethod "$api/repos/$repo/releases?per_page=100" -TimeoutSec 30
$release = $releases | Where-Object tag_name -eq $tag | Select-Object -First 1
if (-not $release) {
    try {
        $release = Invoke-RestMethod -Method Post -Uri "$api/repos/$repo/releases" -Headers $headers -Body @{
            access_token=$token; tag_name=$tag; name="时奕教务排课 $tag（Gitee 自动更新内测版）"; body=$notes; target_commitish=$commit; prerelease='true'
        } -TimeoutSec 60
    } catch { throw ('创建发行版未确认成功，请先查询后再重试，HTTP ' + [int]$_.Exception.Response.StatusCode) }
}
if ($release.target_commitish -ne $commit) { throw '远端发行版源码版本不同，拒绝覆盖' }
$endpoint = "$api/repos/$repo/releases/$($release.id)/attach_files"
$assets = Invoke-RestMethod $endpoint -TimeoutSec 30
# Publish the manifest last, after every installer and signature is available.
foreach ($name in @("STT_${version}_x64-setup.exe", "STT_${version}_x64-setup.exe.sig", "STT_${version}_x64_zh-CN.msi", "STT_${version}_x64_zh-CN.msi.sig", 'RELEASE-NOTES.md', 'SHA256SUMS.txt', 'latest-beta.json')) {
    $file = Get-Item -LiteralPath (Join-Path $ReleaseDirectory $name)
    $existing = $assets | Where-Object name -eq $name
    if ($existing) {
        if ($existing.size -ne $file.Length) { throw "附件大小冲突：$name；未覆盖" }
        Write-Output "保留已有附件：$name"
        continue
    }
    try {
        Write-Output "开始上传：$name"
        $null = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -Form @{ file=$file; access_token=$token } -TimeoutSec 600
        Write-Output "上传成功：$name"
    } catch { throw ("上传未确认成功：$name，请先查询附件再重试，HTTP " + [int]$_.Exception.Response.StatusCode) }
}
$assets = Invoke-RestMethod $endpoint -TimeoutSec 30
$assets | Select-Object name,size,browser_download_url | ConvertTo-Json -Depth 3
$token = $null
$headers = $null
