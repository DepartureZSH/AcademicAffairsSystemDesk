# 干净 Windows 安装卸载自动验收

## 1. 结论

GitHub Actions run [33340232106](https://github.com/DepartureZSH/AcademicAffairsSystemDesk/actions/runs/33340232106) 在三个全新 Windows Runner 上验证 `v0.1.0-test.1`：

| 系统 | Runner 架构 | x64 安装包 | 结果 |
| --- | --- | --- | --- |
| Windows Server 2025 Datacenter `10.0.26100` | AMD64 | NSIS | 通过 |
| Windows Server 2025 Datacenter `10.0.26100` | AMD64 | MSI | 通过 |
| Windows 11 Enterprise `10.0.26200` | ARM64 | NSIS | 通过 x64 兼容运行 |

每个 job 均为新的 GitHub 托管虚拟机。自动化结论不是“Windows 11 ARM64 构建已发布”；被测包仍是 manifest 声明的 `windows-x86_64`，第三个 job 只验证 Windows 11 的 x64 应用兼容层可以完成安装和启动。

## 2. 每个 Runner 的强制断言

`.github/workflows/clean-windows-install.yml` 下载指定不可变 prerelease 的安装包、公开 `.cer` 和 `windows-release-manifest.json`，调用：

```powershell
.\scripts\Test-CleanWindowsInstall.ps1 `
  -AssetDirectory .\release-assets `
  -InstallerKind nsis `
  -ExpectedThumbprint BAC371BF3F9AA7F75F28B0E9BB77DC6AF921FFD5
```

脚本执行以下检查：

1. manifest 格式、应用标识、目标架构和版本有效；
2. 安装包和公开证书的字节数、SHA-256 与 manifest 一致；
3. manifest 和证书同时匹配 workflow 独立提供的公开测试证书指纹；
4. 导入测试证书前安装包有正确签名和时间戳，但状态为 `UnknownError`；
5. 在管理员 Runner 临时导入 `LocalMachine/Root` 与 `TrustedPublisher` 后状态为 `Valid`；
6. NSIS 或 MSI 静默安装返回 0/3010，卸载注册表版本与 manifest 一致；
7. 安装后的 `karios-stt-desktop.exe` 和 `stt-sidecar.exe` 签名、指纹、时间戳有效；
8. 桌面主程序启动后至少存活 5 秒；
9. 在应用默认工作区写入不含业务数据的固定哨兵；
10. 静默卸载后产品注册表项和主程序消失，哨兵文件仍存在且 SHA-256 不变；
11. finally 只移除本次新增的同指纹测试证书和固定哨兵目录。

签名、安装和卸载子进程均有明确超时。脚本拒绝非管理员自动信任，不会试图绕过普通用户看到的 Windows 根证书确认对话框。

## 3. 三份 JSON 证据共同结果

- `status=passed`；
- `packageTarget=windows-x86_64`；
- `preTrustStatus=UnknownError`；
- `postTrustStatus=Valid`；
- `installedExecutablesVerified=2`；
- `applicationLaunch=passed`；
- `uninstall=passed`；
- `userWorkspacePreserved=true`。

JSON 原件作为 run artifacts 分别保存在：

- `clean-windows-windows-2025-nsis`；
- `clean-windows-windows-2025-msi`；
- `clean-windows-windows-11-arm-nsis`。

## 4. 尚未由此自动化覆盖

- 原生 x64 硬件上的 Windows 10 客户端；
- 原生 x64 硬件上的干净 Windows 11 客户端；
- 从旧版本升级到新版本以及尝试降级时的阻断；
- 登录、许可证激活和 UI 主流程的真实交互式安装后验收。

因此本结果关闭“干净系统安装/签名信任/卸载数据保留”的大部分自动化风险，但不取消最终 Windows 10/11 x64 人工 VM 验收。

## 5. Runner 能力依据

- [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions runner images](https://github.com/actions/runner-images)

官方列表将 x64 托管标签定义为 Windows Server 2022/2025，将 Windows 11 托管标签定义为 ARM64；因此本项目明确记录架构和系统差异，不把二者拼接成不存在的“GitHub 原生 Windows 11 x64 Runner”。
