# 自签名与 Updater 双签名实现

## 1. 模块结论

Windows 测试发布现已具备两套相互独立的签名：

- Authenticode：自签名 RSA 3072 代码签名证书，覆盖最终安装包及安装包内的桌面主程序和 Python sidecar，并附加 DigiCert RFC3161 时间戳；
- Tauri updater：独立 Ed25519/minisign 密钥对，对 Authenticode 完成后的最终 NSIS/MSI 字节生成 `.sig`。

这满足 SignPath 获批前测试版本的完整性验证需求，但自签名证书不具备公共 OV 信任。正式发布切换 SignPath 后，仍使用同一 updater 公钥和“先 Authenticode、后 updater 签名”的顺序。

## 2. 密钥位置与保护

### 2.1 Authenticode 测试证书

`scripts/New-TestCodeSigningCertificate.ps1` 在 `Cert:\CurrentUser\My` 生成用途限定为 Code Signing 的 RSA 3072 证书。私钥设置为不可导出，不生成 PFX。公开 CER 输出到 Git 忽略的 `build/signing/Karios-Desktop-TEST-ONLY.cer`。

本次本机证书指纹为 `BAC371BF3F9AA7F75F28B0E9BB77DC6AF921FFD5`，有效期至 2029-08-31。该指纹只是本次测试证据，脚本和配置没有硬编码它。

### 2.2 Updater 密钥

`scripts/New-TauriUpdaterSigningKey.ps1` 将私钥与密码凭据创建在仓库外 `%USERPROFILE%\.karios-signing`。私钥由 36 字节 CSPRNG 随机密码保护；密码凭据通过 Windows DPAPI 的 CLIXML 机制绑定当前用户。脚本默认拒绝覆盖已有材料，只有明确的 `-Force` 才允许轮换。

公钥可公开，已经内置到 `tauri.conf.json`。私钥和 DPAPI 凭据仍需另做加密离线备份；丢失任一项会导致已安装版本无法接受后续更新。

## 3. 构建与签名命令

```powershell
$thumbprint = (Get-ChildItem Cert:\CurrentUser\My |
  Where-Object FriendlyName -eq 'Karios Desktop TEST ONLY Code Signing' |
  Sort-Object NotAfter -Descending |
  Select-Object -First 1).Thumbprint

.\scripts\build-windows.ps1 `
  -CertificateThumbprint $thumbprint `
  -UpdaterPrivateKeyPath "$env:USERPROFILE\.karios-signing\karios-stt-updater.key" `
  -UpdaterPasswordCredentialPath "$env:USERPROFILE\.karios-signing\karios-stt-updater.password.clixml"
```

证书指纹和 updater 私钥只通过进程参数/环境传给 Tauri，不写入基础构建配置。脚本结束时恢复调用者原有的 Tauri 签名环境变量。

## 4. 验证命令

```powershell
.\scripts\Test-WindowsRelease.ps1 `
  -InstallerPath '<安装包绝对路径>' `
  -ExpectedThumbprint $thumbprint `
  -UpdaterSignaturePath '<安装包.sig绝对路径>'
```

验证器执行：

1. 最终安装包具有预期证书的 Authenticode，文件哈希未损坏且存在时间戳；
2. 解包 NSIS/MSI，检查主程序和 sidecar 均由同一证书签名且有时间戳；
3. 从应用配置读取内置 updater 公钥，对安装包与 `.sig` 做真实 minisign/Ed25519 验证。

测试证书尚未导入当前用户根信任时，PowerShell 状态为 `UnknownError`，具体原因必须仅是“不受信任的根”；验证器会接受这个符合预期的测试状态，但拒绝无签名、哈希不匹配、错误指纹、缺少时间戳或 Ed25519 验签失败。

## 5. 本机验证证据（2026-08-31）

| 制品 | 字节数 | Authenticode | 内层主程序/sidecar | Updater Ed25519 |
| --- | ---: | --- | --- | --- |
| `时奕教务排课_0.1.0_x64-setup.exe` | 75,785,576 | 指纹匹配，DigiCert 时间戳 | 均通过 | `.sig` 432 字节，通过 |
| `时奕教务排课_0.1.0_x64_zh-CN.msi` | 77,410,304 | 指纹匹配，DigiCert 时间戳 | 均通过 | `.sig` 432 字节，通过 |

未人工信任 CER 是刻意保留的真实测试条件。测试者只应在专用 Windows 虚拟机中，人工核对 CER SHA-256 和上述发行说明中的证书指纹后，将其导入“受信任的根证书颁发机构”和“受信任的发布者”。自动化不得点击或绕过 Windows 安全确认。

## 6. 应用更新行为

- `services.updates.mode: mock`：界面可检查更新，但 Rust 可信层确定性返回“无更新”；即使 mock 配置声明有更新，也禁止安装模拟制品。
- `services.updates.mode: real`：Tauri 只访问配置中的 `https://updates.karios.tech/...`，下载制品必须先通过内置公钥验证；发现更新后仍需用户在界面确认安装。
- Windows 安装模式为 `passive`，提供进度界面；不静默强制更新。
- 正式 manifest 未上线前保持 mock，避免把外部服务准备工作错误地变成桌面主体构建卡点。

## 7. SignPath 切换规则

SignPath 返回的安装包已经改变字节，因此不得复用构建前或提交 SignPath 前的 `.sig`。正式流水线必须：构建未签名制品 → SignPath 人工审批并签名 → 验证 Publisher/时间戳 → 对返回的最终文件生成 updater `.sig` → 生成 manifest 与 SHA-256 → 发布不可变资产。
