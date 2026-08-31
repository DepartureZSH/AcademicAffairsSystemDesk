# Windows 冻结 Sidecar 与安装包实现

## 1. 模块结论

桌面应用已经形成可重复的 Windows x64 无签名构建链路。Python 3.12、FastAPI、OR-Tools 和本地排课代码由 PyInstaller 冻结为单文件 sidecar；Tauri 将其与 Vue 前端、Rust 主程序和运行时 YAML 配置一起装入 NSIS 与 MSI 安装包。目标机器不需要另外安装 Python、Node、Rust 或 OR-Tools。

本模块只解决“从源码得到可安装制品”。自签名、Tauri updater Ed25519 签名、正式 SignPath 审批与发布属于后续独立模块。

## 2. 可重复构建

在仓库根目录执行：

```powershell
.\scripts\build-windows.ps1
```

脚本按顺序完成以下工作：

1. 将当前用户的 `.cargo\bin` 补入本进程 `PATH`，并检查 Cargo、Node、npm、npx 和 uv；
2. 同步锁定的 Python `build`、`dev` 依赖；
3. 生成符合 Tauri target triple 命名规则的冻结 sidecar；
4. 通过 `npm ci` 安装锁定的前端依赖；
5. 构建简体中文 NSIS 主安装包和 MSI 备用安装包；
6. 输出每个安装包的绝对路径、字节数与 SHA-256。

只构建一种安装包时可传 `-Bundle nsis` 或 `-Bundle msi`。CI 已经同步依赖时可使用 `-SkipSync -SkipNodeInstall`；已有正确 sidecar 时还可使用 `-SkipSidecar`。这些跳过参数仅用于受控流水线，不应在不确定本地制品状态时使用。

## 3. 制品布局

- 冻结 sidecar：`apps/desktop/src-tauri/binaries/stt-sidecar-x86_64-pc-windows-msvc.exe`（构建产物，不进入 Git）；
- NSIS：`apps/desktop/src-tauri/target/release/bundle/nsis/`；
- MSI：`apps/desktop/src-tauri/target/release/bundle/msi/`。

安装后主程序从其相邻目录启动 `stt-sidecar.exe`，从资源目录读取 `config/services.yaml`。开发构建仍从仓库启动 Python 模块，避免每次调试都先冻结。

## 4. 本机验证证据（2026-08-31）

### 4.1 冻结进程与排课

冻结 sidecar 能在 10 秒内输出包含随机环回端口、进程号和一次性会话令牌的 ready 消息。通过该进程完成了健康检查、项目及基础数据创建、异步排课轮次轮询和候选读取：最终状态为 `succeeded`，候选包含 2 条课表记录，事件链完整经过准备、模型编译、求解进程、校验与候选持久化。

### 4.2 安装包

本机成功生成：

- NSIS `时奕教务排课_0.1.0_x64-setup.exe`，74,639,545 字节；
- MSI `时奕教务排课_0.1.0_x64_zh-CN.msi`，75,972,608 字节。

使用 7-Zip 对安装包做内容级检查，两种格式均包含：

- `karios-stt-desktop.exe`；
- `stt-sidecar.exe`（MSI CAB 中为 70,804,923 字节）；
- `config/services.yaml`（1,083 字节）。

MSI 明确配置为 `zh-CN`，避免 WiX 使用西文 1252 代码页而拒绝中文产品名；固定的 `upgradeCode` 保证后续版本被 Windows 识别为同一产品。

## 5. CI 行为

Windows CI 在 Python、Vue 和 Rust 测试通过后构建 NSIS 与 MSI，并上传名为 `windows-unsigned-installers` 的临时制品。该制品名称明确标注 unsigned，不得当作正式发布包。正式发布流水线必须接续代码签名、验签、更新签名和人工审批。

## 6. 安全边界

- PyInstaller 产物只是打包，不是安全沙箱；sidecar 仍只绑定随机 `127.0.0.1` 端口并要求会话令牌。
- 安装包内 YAML 只能包含公开开关、服务 URL 和 publishable 配置，不得包含 Supabase secret/service-role、许可证 pepper、支付密钥、SMTP 密码或任何签名私钥。
- sidecar、主程序和安装包在签名模块完成以前均视为测试制品。
- Windows 卸载器不得删除用户选择的项目目录、`.sttproj` 或 `.sttbackup`。

## 7. 后续门槛

进入公开自签名测试发布前，必须完成代码签名证书生成与隔离、主程序/sidecar/安装包 Authenticode 签名、签名验证、公开 CER 信任操作、Tauri updater 独立 Ed25519 签名以及干净 Windows 10/11 安装和升级测试。
