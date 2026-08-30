[CmdletBinding()]
param(
    [string]$Subject = 'CN=Karios Desktop Test Signing, O=Hangzhou Geruoshi Technology Co. Ltd., C=CN',
    [string]$FriendlyName = 'Karios Desktop TEST ONLY Code Signing',
    [int]$ValidYears = 3
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $repositoryRoot 'build\signing'
$certificatePath = Join-Path $outputDirectory 'Karios-Desktop-TEST-ONLY.cer'

$certificate = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object {
        $_.FriendlyName -eq $FriendlyName -and
        $_.HasPrivateKey -and
        $_.NotAfter -gt (Get-Date).AddDays(30)
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $certificate) {
    $certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -FriendlyName $FriendlyName `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyExportPolicy NonExportable `
        -NotAfter (Get-Date).AddYears($ValidYears)
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
Export-Certificate -Cert $certificate -FilePath $certificatePath -Force | Out-Null

[pscustomobject]@{
    Thumbprint = $certificate.Thumbprint
    Subject = $certificate.Subject
    NotAfter = $certificate.NotAfter
    PublicCertificate = $certificatePath
    PrivateKeyExportable = $false
    TrustedForCurrentUser = $false
    TrustInstruction = '仅在专用测试虚拟机中人工核对并导入公开 CER。'
}
