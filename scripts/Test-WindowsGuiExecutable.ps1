[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
$resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
$bytes = [System.IO.File]::ReadAllBytes($resolvedPath)
if ($bytes.Length -lt 256 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
    throw "不是有效的 Windows PE 文件: $resolvedPath"
}

$peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
if ($peOffset -lt 0 -or $peOffset + 96 -ge $bytes.Length) {
    throw "Windows PE 头偏移无效: $resolvedPath"
}
if ($bytes[$peOffset] -ne 0x50 -or $bytes[$peOffset + 1] -ne 0x45 -or
    $bytes[$peOffset + 2] -ne 0 -or $bytes[$peOffset + 3] -ne 0) {
    throw "Windows PE 签名无效: $resolvedPath"
}

# PE32 and PE32+ both store Subsystem at offset 68 in the optional header.
$optionalHeaderOffset = $peOffset + 24
$subsystem = [BitConverter]::ToUInt16($bytes, $optionalHeaderOffset + 68)
if ($subsystem -ne 2) {
    throw "桌面主程序必须使用 Windows GUI 子系统 (2)，实际为 $subsystem：$resolvedPath"
}

[pscustomobject]@{
    Path = $resolvedPath
    Subsystem = $subsystem
    IsWindowsGui = $true
}
