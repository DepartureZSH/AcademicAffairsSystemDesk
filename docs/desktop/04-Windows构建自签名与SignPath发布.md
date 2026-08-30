# Windows 构建、自签名与 SignPath 发布操作文档

> 本文提供发布操作基线，不包含真实密码、token、项目 ID 或私钥。所有命令先在测试证书和测试 channel 演练。

## 1. 两类签名不可混淆

| 签名 | 目的 | 密钥/证书 |
| --- | --- | --- |
| Windows Authenticode | Windows 验证安装包发布者和文件完整性 | 自签名测试证书或 SignPath Foundation 证书 |
| Tauri updater signature | 应用更新器验证下载内容 | Tauri Ed25519 私钥与内置公钥 |

SignPath 或自签名改变安装包字节，因此必须先完成 Authenticode 签名，再对最终文件生成 Tauri updater signature。

## 2. 发布产物

Windows x64 每个版本至少包含：

- NSIS `.exe` 主安装包。
- MSI `.msi` 备用安装包。
- 每个更新文件对应的 Tauri `.sig`。
- 更新 manifest、SHA-256 校验和、SBOM 和版本说明。
- 测试报告、构建 commit 和来源证明。

文件名使用稳定规则，例如：

```text
ShiYi-Scheduler_0.1.0_windows-x86_64-setup.exe
ShiYi-Scheduler_0.1.0_windows-x86_64.msi
```

版本使用 SemVer；正式 channel 禁止覆盖已发布版本号或同名文件。

## 3. 构建机准备

- Windows 10/11 x64。
- Git、Node.js、Rust stable、Python、Visual Studio C++ Build Tools。
- Windows 10/11 SDK（提供 `signtool.exe`）。
- WebView2 Runtime；安装器构建所需 NSIS/WiX 工具。
- 依赖锁文件和干净 checkout。
- 系统时间同步、足够磁盘空间及恶意软件扫描排除规则的人工审核。

检查命令示例：

```powershell
git status --short
node --version
npm --version
rustc --version
cargo --version
python --version
Get-Command signtool.exe
```

正式构建必须从 Git tag 和干净 checkout 产生；开发者工作区构建不能直接成为正式安装包。

## 4. 自签名测试证书

### 4.1 用途和限制

自签名证书仅用于 SignPath 获批前的内部/公开测试。未安装信任证书的用户仍会看到未知发布者或 SmartScreen 提示。不得宣传为公开信任的 OV 签名，不得把 PFX 或密码提供给测试人员。

### 4.2 生成

在隔离的 Windows 签名账户中运行；先创建受限目录并确认路径：

```powershell
$sttCertDir = 'C:\SecureBuild\stt-signing'
New-Item -ItemType Directory -Path $sttCertDir -Force

$sttCert = New-SelfSignedCertificate `
  -Type CodeSigningCert `
  -Subject 'CN=杭州格若时科技有限公司, O=杭州格若时科技有限公司, C=CN' `
  -CertStoreLocation 'Cert:\CurrentUser\My' `
  -KeyAlgorithm RSA `
  -KeyLength 3072 `
  -HashAlgorithm SHA256 `
  -KeyExportPolicy Exportable `
  -NotAfter (Get-Date).AddYears(2)

$sttPfxPassword = Read-Host '输入新的 PFX 强密码' -AsSecureString
Export-PfxCertificate `
  -Cert $sttCert `
  -FilePath (Join-Path $sttCertDir 'stt-test-codesign.pfx') `
  -Password $sttPfxPassword

Export-Certificate `
  -Cert $sttCert `
  -FilePath (Join-Path $sttCertDir 'stt-test-codesign.cer')
```

操作后：

- 将 PFX 移入访问受控且有加密备份的位置。
- 记录证书 thumbprint、有效期、保管人和撤销/轮换日期。
- `.cer` 可以公开给测试者；PFX、密码和导出后的私钥严禁进入 Git、网盘公开链接或聊天。

### 4.3 测试机信任

仅在专用测试虚拟机中导入公开 `.cer`。导入“受信任的根证书颁发机构/受信任的发布者”会信任该证书签署的程序，必须人工核对 SHA-256 和证书指纹。测试结束后删除信任项或还原虚拟机快照。

### 4.4 签署和验证

```powershell
$sttArtifact = 'C:\Build\ShiYi-Scheduler_0.1.0_windows-x86_64-setup.exe'
$sttPfx = 'C:\SecureBuild\stt-signing\stt-test-codesign.pfx'
$sttPfxPassword = Read-Host '输入 PFX 密码' -AsSecureString

signtool.exe sign `
  /fd SHA256 `
  /f $sttPfx `
  /p ([System.Net.NetworkCredential]::new('', $sttPfxPassword).Password) `
  /tr 'http://timestamp.digicert.com' `
  /td SHA256 `
  $sttArtifact

signtool.exe verify /pa /all /v $sttArtifact
Get-FileHash -Algorithm SHA256 $sttArtifact
```

命令行密码可能被进程审计工具观察；正式自动化应使用受保护证书存储或签名服务，而不是 `/p`。自签名流程只作为临时测试方案。

## 5. Tauri updater 签名

1. 在离线或受控环境生成 updater 密钥对。
2. 公钥写入应用配置；私钥和密码写入 GitHub Actions secret，不写仓库。
3. Authenticode 签名完成后，再对最终 `.exe/.msi` 运行 Tauri signer。
4. manifest 中记录最终 URL、版本、发布日期和最终签名。
5. 在断网、篡改、错误 key、降级和镜像缺失场景测试。

密钥生成和签名命令以项目锁定的 Tauri 2 CLI 版本官方输出为准；执行前运行 `tauri signer --help`，不要从旧文档复制参数。Tauri updater 签名是强制安全机制：<https://v2.tauri.app/plugin/updater/>。

## 6. 自签名测试发布流程

1. 从已审核 tag 在干净环境构建 NSIS/MSI。
2. 生成 SBOM、依赖清单和初始 SHA-256。
3. 使用测试证书执行 Authenticode 签名并验证。
4. 对最终文件生成 Tauri updater 签名和 manifest。
5. 在 Windows 10/11 干净虚拟机执行安装、升级、卸载和离线测试。
6. 发布 GitHub pre-release，醒目标注“测试证书，需要人工信任；不代表 SignPath 正式签名”。
7. 同步到测试更新 channel，不进入正式 channel。
8. 保存构建日志、签名结果和发布审批记录。

## 7. SignPath Foundation 准备条件

申请前必须完成：

- GitHub 仓库公开可访问。
- 使用 OSI 批准的 Apache-2.0 许可证。
- 所有被签名组件均为可审计的开源代码，不依赖私有构建步骤产生不可验证二进制。
- 已发布至少一个可下载、可运行并有文档的版本。
- 仓库公开隐私政策、Code Signing Policy、安全渠道和维护者信息。
- 维护者使用 MFA；作者、审阅者和发布批准者职责可区分。
- 使用受支持、可验证的 GitHub 构建来源和人工签名审批。

Foundation 证书属于 SignPath Foundation，因此 Windows Publisher 显示 `SignPath Foundation`，公司名称保留在版权、产品和商标声明中。以申请时的官方条款为最终准则：

- <https://signpath.org/terms.html>
- <https://docs.signpath.io/origin-verification/>
- <https://docs.signpath.io/projects>
- <https://docs.signpath.io/trusted-build-systems/github>

## 8. SignPath 正式流水线

推荐顺序：

1. 受保护 tag 触发 GitHub-hosted Windows runner。
2. checkout 精确 commit，验证 lockfile，执行完整测试。
3. 构建未签名 NSIS/MSI、SBOM 和来源元数据。
4. 将构建产物提交 SignPath；不得在提交后重新打包。
5. 指定批准者人工核对版本、commit、测试、产物名称和哈希。
6. SignPath 返回 Authenticode 签名产物。
7. CI 执行 `signtool verify /pa /all /v` 并确认 Publisher 和时间戳。
8. 对 SignPath 返回的最终字节生成 Tauri updater signature。
9. 生成正式 manifest、SHA-256 和发布说明。
10. 先上传不可变产物，再原子切换正式 manifest。
11. 同步 GitHub Releases、`updates.karios.tech` 和 Zot/对象存储镜像。
12. 在干净虚拟机从上一个正式版本执行真实升级。

SignPath 项目、构件配置和工作流片段应从 SignPath 控制台生成，并将第三方 GitHub Action固定到不可变 commit SHA；不在本文硬编码可能变化的 action 版本。

## 9. 更新服务

- `updates.karios.tech` 作为官方更新入口，返回平台/架构/channel 对应 manifest。
- GitHub Releases 保存不可变正式资产；Zot 或对象存储作为镜像。
- 同一版本各镜像文件必须有相同 SHA-256 和 updater signature。
- 更新入口发生后端故障时返回明确非 2xx，让客户端可尝试备用端点；不得以 200 返回 HTML 错误页。
- manifest 切换前确认所有资产已在各镜像可读。
- 记录 rollout channel：`test`、`stable`；首版不做静默强制更新。

## 10. 发布验证清单

- [ ] tag、版本、commit 和构建日志一致。
- [ ] 仓库在构建时干净，依赖从锁文件安装。
- [ ] NSIS/MSI 均通过 Authenticode 验证。
- [ ] Tauri signature 是针对 Authenticode 后的最终文件生成。
- [ ] SBOM、SHA-256、发布说明和隐私链接齐全。
- [ ] Windows 10/11 干净虚拟机安装与升级通过。
- [ ] 篡改安装包、错误 updater 签名和降级均被拒绝。
- [ ] 安装失败不会删除用户项目目录。
- [ ] GitHub、更新域名和镜像文件哈希一致。
- [ ] 正式构建已由独立批准者审核。

## 11. 回滚与证书事故

- 应用版本不允许通过替换同名资产回滚；发布修复版本并让 manifest 指向新版本。
- manifest 发布错误时可恢复到上一份已签名 manifest，但不能让已升级数据库执行不受支持的降级。
- updater 私钥疑似泄漏时立即停止更新服务、轮换 key、发布带新公钥的可信过渡版本并公告影响。
- 自签名 PFX 泄漏时停止分发、通知测试人员删除信任并生成新证书。
- SignPath 凭据或项目角色异常时暂停审批，按 SignPath/证书机构流程报告，不自行伪造替代签名。
