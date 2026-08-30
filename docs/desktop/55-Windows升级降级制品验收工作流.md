# Windows 升级降级制品验收工作流

## 1. 目的

`clean-windows-install.yml` 已验证单版本的签名信任、安装、启动、卸载和用户数据保留，但不能证明真实跨版本升级，也不能证明旧安装器无法覆盖新版本。本模块新增独立的 `windows-upgrade.yml` 和 `Test-WindowsUpgrade.ps1`，只消费两个不可变 GitHub prerelease，不使用工作区中的临时安装包。

## 2. 验收序列

Windows Server 2025 原生 AMD64 Runner 分别对 NSIS、MSI 执行：

1. 下载上一标签与当前标签的安装包、公开测试证书和 release manifest；
2. 使用独立固定指纹验证两个 manifest、证书、安装包大小与 SHA-256；
3. 断言上一版本号严格小于当前版本号；
4. 临时把测试证书加入 Runner 的 LocalMachine Root 与 TrustedPublisher；
5. 安装上一版并核对产品注册表版本；
6. 在应用用户工作区创建无业务数据哨兵并记录哈希；
7. 安装当前版，核对注册表版本，记录新版主程序与 Sidecar SHA-256，并确认哨兵不变；
8. 静默运行上一版安装器尝试降级；
9. 不依赖安装器退出码，直接断言注册表仍为当前版本、两个新版 EXE 哈希不变、哨兵不变；
10. 卸载当前版，确认产品注册表消失而用户工作区仍保留；
11. 严格校验哨兵父目录和固定名称后清理哨兵，并只移除本次导入的证书。

降级验证采用“最终状态与文件字节未变化”作为判据，因为不同安装器对阻断操作的退出码并不一致。

## 3. 触发

发布 `v0.1.1-test.2` 后，在 GitHub Actions 手工触发 **Windows upgrade and downgrade verification**：

- `previous_release_tag`: `v0.1.0-test.1`
- `current_release_tag`: `v0.1.1-test.2`

两个 matrix job（NSIS、MSI）都必须成功，并保存各自 JSON artifact。工作流对 release 只有读取权限，不能修改标签或资产。

## 4. 当前状态

PowerShell 脚本已通过 AST 解析，工作流 YAML 已解析并验证 matrix；实际制品测试尚未执行，因为当前标签在本模块提交时尚未发布。新 release 完成前，该门禁保持待验证状态。
