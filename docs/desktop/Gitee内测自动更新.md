# Gitee 内测自动更新

客户端匿名访问公开仓库，不读取或携带 GITEE_ACCESS_TOKEN。令牌只与发布上传有关，维护者也可以在浏览器手动上传。

## 用户流程

检查更新 → 查询公开 Release（包括内测版本）→ 按语义版本比较 → 弹窗展示结果 → 有新版自动下载 → Tauri 内置公钥校验 → 用户保存工作并确认退出安装。

- 网络错误、缺清单、签名失败均显示错误，不能伪装成“已是最新版本”。
- 下载时可以收起弹窗，点击顶部“查看下载”重新打开。不会自动退出或安装。
- 下载包暂存在进程内存中，退出应用后需要重新下载；当前不提供断点续传。
- 安装前先请求安全关闭项目和本地服务；正在排课而拒绝关闭时不安装。
- 不使用 Windows 代码签名替代 Tauri 更新签名，也不跳过签名校验。
- 当前提供 Windows x64 制品；macOS/Linux 必须在清单中提供各自平台的签名制品。

## 发布步骤

1. 使用新的版本号构建。首次包含该功能的版本需要手动安装；旧 mock 更新版本无法自动获取此能力。
2. 使用 `build-windows.ps1` 的 `UpdaterPrivateKeyPath` 和 `UpdaterPasswordCredentialPath` 参数生成成对安装包和 `.sig`。保管并离线备份原签名密钥，不要重新生成替换。
3. 运行以下清单脚本（示例中的版本号替换为本次版本）：

```powershell
.\scripts\New-GiteeUpdateManifest.ps1 `
  -NsisPath '.\apps\desktop\src-tauri\target\release\bundle\nsis\时奕教务排课_0.2.7_x64-setup.exe' `
  -MsiPath '.\apps\desktop\src-tauri\target\release\bundle\msi\时奕教务排课_0.2.7_x64_zh-CN.msi' `
  -NotesPath '.\build\release\v0.2.7\RELEASE-NOTES.md' `
  -OutputDirectory '.\build\gitee-signed\v0.2.7'
```

脚本使用当前公钥验证安装包签名，失败即停止；输出目录必须尚不存在。MSI 参数可选，实际文件名以构建产物为准。复制和重命名不改变文件字节，不能在签名后修改安装包。

4. 在公开仓库创建 `v0.2.7` Release，把输出目录内所有文件上传，包括 `latest-beta.json`。更新清单包含签名文件的完整文本，而不是 `.sig` 地址。仅完成构建不会自动上传附件。
5. 从公网确认附件可匿名下载，再用上一版客户端检查、下载和确认安装。应另外验证断网、缺清单、破坏签名、取消安装、排课中拒绝关闭等分支。

维护者也可在源码提交后运行 `scripts/Publish-GiteeRelease.ps1 -ReleaseDirectory <上面的输出目录>` 自动推送当前分支与版本标签，并发布七个附件（更新清单最后上传）。上传需要本地 `.env` 中的 `GITEE_ACCESS_TOKEN`；脚本不会把凭据写入 Git 配置或客户端。遇到已有不同附件或版本时停止，不强制覆盖。

客户端固定查询 `hangzhou-greos-time/academic-affairs-system-desk` 仓库，使用最新有效语义版本标签对应的 `latest-beta.json`，校验清单版本与标签一致、下载 URL 属于同仓库同标签，不因最新发布缺清单就静默回退旧版。制品完成下载后才声称签名校验成功。

不覆盖已有版本附件：同版本重新构建的文件可能不同，必须使用对应签名。建议始终递增版本，避免用户无法识别同版本修订。
