[CmdletBinding()]
param(
    [string]$SupabaseEnvFile = (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'STT\.env'),
    [string]$SupabaseEndpoint = 'http://127.0.0.1:55421',
    [string]$MailpitEndpoint = 'http://127.0.0.1:55424',
    [string]$DatabaseContainer = 'supabase_db_stt-local'
)

$ErrorActionPreference = 'Stop'
$trackedMessageIds = [System.Collections.Generic.List[string]]::new()
$testUserId = $null

function Assert-LoopbackUri {
    param([Parameter(Mandatory)][string]$Value, [Parameter(Mandatory)][string]$Name)

    $uri = [Uri]$Value
    if ($uri.Scheme -notin @('http', 'https') -or
        $uri.Host -notin @('127.0.0.1', 'localhost', '::1') -or
        -not [string]::IsNullOrEmpty($uri.UserInfo)) {
        throw "$Name 必须是不含用户信息的本机回环 HTTP(S) 地址。"
    }
    return $uri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
}

function Invoke-JsonApi {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST', 'PUT', 'DELETE')][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [hashtable]$Headers = @{},
        [AllowNull()][object]$Body = $null,
        [Parameter(Mandatory)][string]$Phase
    )

    try {
        $parameters = @{
            Method = $Method
            Uri = $Uri
            Headers = $Headers
            ErrorAction = 'Stop'
        }
        if ($null -ne $Body) {
            $parameters.ContentType = 'application/json'
            $parameters.Body = $Body | ConvertTo-Json -Compress -Depth 8
        }
        return Invoke-RestMethod @parameters
    }
    catch {
        $status = if ($null -ne $_.Exception.Response) {
            [int]$_.Exception.Response.StatusCode
        }
        else {
            'network-error'
        }
        throw "$Phase 失败（状态：$status）。响应正文已隐藏，避免泄露身份凭据。"
    }
}

function Get-PublishableKey {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "找不到 Supabase 环境文件：$Path"
    }
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match '^SUPABASE_PUBLISHABLE_KEY=' } |
        Select-Object -First 1
    if ($null -eq $line) {
        throw 'Supabase 环境文件缺少 SUPABASE_PUBLISHABLE_KEY。'
    }
    $value = ($line -replace '^SUPABASE_PUBLISHABLE_KEY=', '').Trim().Trim('"').Trim("'")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw 'SUPABASE_PUBLISHABLE_KEY 为空。'
    }
    return $value
}

function Get-MailForRecipient {
    param(
        [Parameter(Mandatory)][string]$Recipient,
        [Parameter(Mandatory)][ValidateSet('signup', 'recovery')][string]$ExpectedType,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $listing = Invoke-JsonApi -Method GET -Uri "$script:mailpit/api/v1/messages?limit=100" -Phase '读取 Mailpit 邮件列表'
        foreach ($message in @($listing.messages)) {
            $addresses = @($message.To) | ForEach-Object { $_.Address }
            if ($Recipient -notin $addresses -or $trackedMessageIds.Contains([string]$message.ID)) {
                continue
            }
            $detail = Invoke-JsonApi -Method GET -Uri "$script:mailpit/api/v1/message/$($message.ID)" -Phase '读取 Mailpit 邮件正文'
            $body = [System.Net.WebUtility]::HtmlDecode("$($detail.HTML)`n$($detail.Text)")
            $links = [regex]::Matches($body, 'https?://[^\s"''<>]+') | ForEach-Object { $_.Value.TrimEnd('.', ',', ')') }
            foreach ($candidate in $links) {
                try { $uri = [Uri]$candidate } catch { continue }
                if ($uri.AbsolutePath -ne '/auth/v1/verify') { continue }
                $query = [System.Web.HttpUtility]::ParseQueryString($uri.Query)
                if ($query['type'] -ne $ExpectedType) { continue }
                $token = if ($query['token_hash']) { $query['token_hash'] } else { $query['token'] }
                if ([string]::IsNullOrWhiteSpace($token)) { continue }
                $trackedMessageIds.Add([string]$message.ID)
                return [pscustomobject]@{
                    Token = $token
                    QueryKeys = @($query.AllKeys | Where-Object { $null -ne $_ } | Sort-Object)
                }
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    throw "等待 $ExpectedType 邮件超时。"
}

$supabase = Assert-LoopbackUri -Value $SupabaseEndpoint -Name 'SupabaseEndpoint'
$mailpit = Assert-LoopbackUri -Value $MailpitEndpoint -Name 'MailpitEndpoint'
if ($DatabaseContainer -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') {
    throw 'DatabaseContainer 名称包含不允许的字符。'
}

$publishableKey = Get-PublishableKey -Path $SupabaseEnvFile
$headers = @{ apikey = $publishableKey }
$suffix = [Guid]::NewGuid().ToString('N')
$email = "desktop-auth-$suffix@example.test"
$oldPassword = "Karios-Old-$suffix!"
$newPassword = "Karios-New-$suffix!"

try {
    $signup = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/signup" -Headers $headers -Body @{
        email = $email
        password = $oldPassword
    } -Phase '注册临时账号'
    $signupUserId = if ($null -ne $signup.user) { $signup.user.id } else { $signup.id }
    $parsedUserId = [Guid]::Empty
    if (-not [Guid]::TryParse([string]$signupUserId, [ref]$parsedUserId)) {
        throw '注册响应缺少有效用户 ID。'
    }
    $testUserId = $parsedUserId.ToString('D')
    Write-Output 'PASS 注册临时账号（凭据未输出）'

    $signupMail = Get-MailForRecipient -Recipient $email -ExpectedType signup
    Write-Output "PASS 收到确认邮件（查询参数：$($signupMail.QueryKeys -join ', ')）"
    $confirmed = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/verify" -Headers $headers -Body @{
        token_hash = $signupMail.Token
        type = 'signup'
    } -Phase '确认邮箱'
    if ([string]::IsNullOrWhiteSpace([string]$confirmed.access_token)) { throw '确认邮箱未返回会话。' }
    Write-Output 'PASS 邮箱确认'

    $oldLogin = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/token?grant_type=password" -Headers $headers -Body @{
        email = $email
        password = $oldPassword
    } -Phase '使用旧密码登录'
    if ([string]::IsNullOrWhiteSpace([string]$oldLogin.access_token)) { throw '旧密码登录未返回会话。' }
    Write-Output 'PASS 旧密码登录'
    $null = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/logout" -Headers ($headers + @{ Authorization = "Bearer $($oldLogin.access_token)" }) -Phase '退出旧会话'

    $null = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/recover" -Headers $headers -Body @{
        email = $email
        redirect_to = 'http://localhost:5173/reset-password'
    } -Phase '申请密码恢复'
    $recoveryMail = Get-MailForRecipient -Recipient $email -ExpectedType recovery
    Write-Output "PASS 收到恢复邮件（查询参数：$($recoveryMail.QueryKeys -join ', ')）"

    $recovery = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/verify" -Headers $headers -Body @{
        token_hash = $recoveryMail.Token
        type = 'recovery'
    } -Phase '验证恢复令牌'
    if ([string]::IsNullOrWhiteSpace([string]$recovery.access_token)) { throw '恢复验证未返回会话。' }
    Write-Output 'PASS 恢复令牌验证'

    $updated = Invoke-JsonApi -Method PUT -Uri "$supabase/auth/v1/user" -Headers ($headers + @{ Authorization = "Bearer $($recovery.access_token)" }) -Body @{
        password = $newPassword
    } -Phase '更新密码'
    if ([string]$updated.id -ne $testUserId) { throw '更新密码返回了不匹配的用户。' }
    $null = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/logout" -Headers ($headers + @{ Authorization = "Bearer $($recovery.access_token)" }) -Phase '退出恢复会话'
    Write-Output 'PASS 更新密码并退出恢复会话'

    $oldPasswordRejected = $false
    try {
        $null = Invoke-RestMethod -Method POST -Uri "$supabase/auth/v1/token?grant_type=password" -Headers $headers -ContentType 'application/json' -Body (@{
            email = $email
            password = $oldPassword
        } | ConvertTo-Json -Compress) -ErrorAction Stop
    }
    catch {
        $oldPasswordRejected = $true
    }
    if (-not $oldPasswordRejected) { throw '更新密码后旧密码仍可登录。' }
    Write-Output 'PASS 旧密码已失效'

    $newLogin = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/token?grant_type=password" -Headers $headers -Body @{
        email = $email
        password = $newPassword
    } -Phase '使用新密码登录'
    if ([string]::IsNullOrWhiteSpace([string]$newLogin.access_token)) { throw '新密码登录未返回会话。' }
    $null = Invoke-JsonApi -Method POST -Uri "$supabase/auth/v1/logout" -Headers ($headers + @{ Authorization = "Bearer $($newLogin.access_token)" }) -Phase '退出新会话'
    Write-Output 'PASS 新密码登录'
    Write-Output 'RESULT 本地 Supabase Auth 注册、确认、登录、密码恢复闭环通过。'
}
finally {
    if ($null -ne $testUserId) {
        $runningContainer = docker inspect --format '{{.State.Running}}' $DatabaseContainer 2>$null
        if ($LASTEXITCODE -eq 0 -and $runningContainer -eq 'true') {
            $deleteSql = "delete from auth.users where id = '$testUserId'::uuid;"
            $null = docker exec $DatabaseContainer psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c $deleteSql 2>$null
            if ($LASTEXITCODE -eq 0) { Write-Output 'CLEANUP 已删除本次临时 Supabase 用户。' }
        }
    }
    if ($trackedMessageIds.Count -gt 0) {
        $safeMessageIds = @($trackedMessageIds | Where-Object { $_ -match '^[A-Za-z0-9_.-]+$' })
        try {
            $null = Invoke-JsonApi -Method DELETE -Uri "$mailpit/api/v1/messages" -Body @{
                IDs = $safeMessageIds
            } -Phase '删除本次测试邮件'
            Write-Output "CLEANUP 已删除本次测试邮件：$($safeMessageIds.Count) 封。"
        }
        catch {
            Write-Warning '未能删除本次测试邮件；未执行全量邮箱清理。'
        }
    }
}
