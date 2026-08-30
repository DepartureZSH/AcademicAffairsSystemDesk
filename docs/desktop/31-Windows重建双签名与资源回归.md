# Windows 重建、双签名与资源回归

## 1. 模块结论

在购买入口、项目另存、年级课表、导出预览和冻结 sidecar 生命周期修复完成后，Windows x64 安装包已从提交 `d01ccc3259da238254555726ceda31a08104df49` 重新构建。NSIS、MSI、内层桌面主程序和 sidecar 均使用测试 Authenticode 证书签名并附带 RFC3161 时间戳；最终安装包另由既有 Tauri updater Ed25519 密钥签名，两个 `.sig` 均通过实际密码学验证。

## 2. 本轮制品证据（2026-08-31）

| 制品 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `时奕教务排课_0.1.0_x64-setup.exe` | 75,844,648 | `086CB767EEC22F3745959AA3E94A47F68DDE8E422A99DBD5A8AD141C087DD326` |
| `时奕教务排课_0.1.0_x64_zh-CN.msi` | 77,504,512 | `368CFB681B9165B4F7B974454B97ECD6F45C8B20163FE25D21581836133770A3` |

验证器确认两种安装包：

- 外层安装包证书指纹匹配测试证书；
- 内层 `karios-stt-desktop.exe` / MSI 主程序和 `stt-sidecar.exe` 使用同一证书；
- 外层与内层签名都存在时间戳；
- `.sig` 能由 `tauri.conf.json` 内置公钥验证最终安装包字节；
- 解包后同时存在 `services.yaml`、冻结 sidecar 和 `mock/purchase.html`。
- 冻结 sidecar 的外层启动器与内部工作进程能通过授权接口同时退出，不留下监听端口的孤儿进程。

本轮依赖清单和 CycloneDX SBOM 共记录 655 个组件，未发现缺少许可证元数据；对应发布清单位于本地 `build/release/windows-release-manifest.json`，其中源码提交、制品哈希、`.sig` 哈希和合规证据哈希保持一致。

测试证书未加入当前机器根信任，因此 Authenticode 状态仍是预期的“不受信任根”，而不是公共 OV 信任；该状态不等同于 SignPath 正式签名。

## 3. 验证器临时目录修复

`Test-WindowsRelease.ps1` 过去会把每次 NSIS/MSI 解包内容留在 `build/signing/verify-*`。现已在 `finally` 中清理，并在删除前同时验证：

- 解析后的父目录必须精确等于仓库 `build/signing`；
- 目录名必须以 `verify-` 开头。

任何校验失败都会拒绝递归删除。验签结果在清理前已经转换为证书元数据对象，因此不会引用已删除文件内容。

## 4. 尚需人工环境验证

本轮证明制品可构建、内容完整且双重签名有效，但没有替代 G2 的干净 Windows 10/11 安装、升级、卸载保留项目数据和 CER 人工信任提示记录。这些动作必须在专用虚拟机或云电脑执行，不能在当前开发机上冒充干净环境证据。
