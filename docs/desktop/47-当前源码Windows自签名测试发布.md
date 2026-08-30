# 当前源码 Windows 自签名测试发布

## 1. 构建基线

- 源码提交：`bc373242ff09f0d922fcec7481f182a0e7871174`
- 应用版本：`0.1.0`
- 应用标识：`tech.karios.stt.desktop`
- 平台：Windows x86_64
- 签名配置：`self-signed-test`
- 测试证书指纹：`BAC371BF3F9AA7F75F28B0E9BB77DC6AF921FFD5`
- 时间戳：DigiCert SHA256 RSA4096 Timestamp Responder 2025 1

构建前源码提交已推送到 `origin/codex/desktop-local` 且工作区干净。构建执行锁定 Python/Node/Rust 依赖同步、PyInstaller sidecar 冻结、Tauri release 编译、NSIS/MSI 打包、Authenticode 和 updater Ed25519 签名。

## 2. 最终制品

| 制品 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `Karios-STT-Desktop_0.1.0_x64-setup.exe` | 75,867,056 | `0C71BAB83A3054F27535B3CFDA37791FC50392CCAD6A101A6669C29F08CB2777` |
| `Karios-STT-Desktop_0.1.0_x64-setup.exe.sig` | 432 | `4A76F5AD123E2ABEBFC0C98E213EB98D7F70C1B2A7DBA2A66FF8F5F2EC3FD5B4` |
| `Karios-STT-Desktop_0.1.0_x64_zh-CN.msi` | 77,524,992 | `EB588759F007E0B2EE7E0C941C89ADDF715F2825149426F39F254639DE195F70` |
| `Karios-STT-Desktop_0.1.0_x64_zh-CN.msi.sig` | 432 | `750DCA9367B473348944E162E70CC9C6684847F6CF8FD616F2E80162008AA7E7` |
| `Karios-Desktop-TEST-ONLY.cer` | 1,178 | `A8102D0E8BBC5D19DC4A1EB7750A4BB03326A4226CEB46CF98ABE03E675D5D4B` |

本地路径：

- NSIS：`apps/desktop/src-tauri/target/release/bundle/nsis/`
- MSI：`apps/desktop/src-tauri/target/release/bundle/msi/`
- GitHub ASCII 发布副本：`build/release/assets/`
- 公开测试证书：`build/signing/Karios-Desktop-TEST-ONLY.cer`
- 发布清单与校验和：`build/release/`
- 依赖清单与 CycloneDX SBOM：`build/compliance/`

`build/` 和 `target/` 是 Git 忽略的本地制品目录，不提交私钥、密码、PFX 或安装包二进制。

GitHub prerelease：<https://github.com/DepartureZSH/AcademicAffairsSystemDesk/releases/tag/v0.1.0-test.1>。Release tag 精确指向二进制源码提交 `bc37324`。公开下载名使用 ASCII，避免托管平台归一化中文文件名后与 manifest 不一致；安装后的产品名和界面仍为“时奕教务排课”。

## 3. 自动验证结果

- 冻结 sidecar 在 20 秒门槛内启动，返回独立 launcher/worker PID 和健康状态 `ok`。
- 经带 Bearer 令牌和 Tauri Origin 的本地 API 请求关闭后，launcher 与 worker 均退出，无残留端口进程。
- NSIS/MSI 外层安装包、内层 `karios-stt-desktop.exe` 和 `stt-sidecar.exe` 均匹配测试证书指纹并包含时间戳。
- 当前开发机未信任自签名根，因此 Authenticode 状态为预期的 `UnknownError / 不受信任的根`；验证器已排除无签名、哈希不匹配、错误指纹和缺时间戳。
- 两个 `.sig` 均由应用内置 updater 公钥完成真实 minisign/Ed25519 验证。
- 依赖清单和 CycloneDX 1.6 SBOM 共 655 个组件，缺失许可证元数据 0。
- release manifest 的源码提交、制品大小/哈希、签名顺序和合规证据哈希一致。

## 4. 自动测试基线

- Python：82 passed；Ruff 通过。
- Rust：10 passed；`cargo fmt --check` 和 `cargo check --locked` 通过。
- Vue：类型检查与 Vite 生产构建通过。
- 6000 课次：25.762 秒生成 6000 条完整课表，硬约束 0、总分 0。

## 5. 发布标识与限制

这是 SignPath Foundation 获批前的自签名测试版，不是公开受信任的 OV 正式版。许可证、支付、SMTP 和远程更新在开发配置中仍是 Mock；测试版必须保留模拟服务标识，不能用于真实收费或生产授权。

测试者应通过独立可信渠道核对 CER SHA-256、证书指纹和安装包 SHA-256，只在专用测试机中决定是否导入“受信任的根证书颁发机构”和“受信任的发布者”。不得为了消除 SmartScreen 或不受信任提示而关闭系统安全功能。

## 6. 尚需人工验证

- 干净 Windows 10/11 安装、首次启动和卸载；
- 未安装 CER 与安装 CER 后的 Publisher 提示截图；
- 升级、同版本覆盖和降级阻断；
- 卸载后工作区项目、备份和隔离回收目录保持；
- 最低支持硬件重复 6000 课次基准。

这些环境操作不能由当前开发机的自动验签替代，完成前本发布仅可标记为 prerelease。
