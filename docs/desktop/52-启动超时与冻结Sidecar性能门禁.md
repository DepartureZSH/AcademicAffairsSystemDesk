# 启动超时与冻结 Sidecar 性能门禁

## 1. 目标

产品需求要求应用启动后 10 秒内出现可交互主界面，Sidecar 启动失败在 5 秒内给出诊断。本模块把此前分散、偏宽松的等待策略收口为显式门禁，避免本机身份服务失联或冻结程序故障时无限等待。

## 2. 实现

- Supabase Auth 客户端统一使用 3 秒连接超时和 5 秒整请求超时；登录、注册、密码恢复、会话刷新和退出均复用该客户端。
- 已保存会话刷新失败时继续进入既有离线授权判断，不把暂时断网误判为账号注销。
- Tauri 等待 Sidecar 首行 `ready` 消息的上限从 10 秒收紧为 5 秒；超时后终止本次持有的子进程并返回“sidecar 5 秒内未就绪”。
- 两组时限均由 Rust 单元测试锁定，防止后续无意放宽。
- `Test-FrozenSidecarLifecycle.ps1` 使用同一 5 秒门槛，并输出从 `Start-Process` 到解析首行就绪消息的毫秒数。

主窗口由 Tauri/Vue 直接创建，身份和许可证状态在窗口内异步加载；远程身份请求不会阻塞操作系统窗口创建。未登录状态不发身份网络请求，有本地会话但网络不可用时最多 5 秒进入离线提示。

## 3. 实测证据

2026-08-31 在当前 Windows 11 x64 开发机直接启动 v0.1.5 的 PyInstaller one-file Sidecar：

| 检查项 | 结果 |
| --- | ---: |
| Ready 耗时 | 3,756 ms |
| 门槛 | 5,000 ms |
| 健康检查 | `ok` |
| 授权关闭 | `shutting_down` |
| launcher / worker 残留 | 0 / 0 |

同轮验证还包括 Vue 类型检查与生产构建，以及 `cargo fmt --check`、`cargo check --locked`、14 项 Rust 测试，均通过。

重复命令：

```powershell
.\scripts\Test-FrozenSidecarLifecycle.ps1
cd apps\desktop\src-tauri
cargo fmt --check
cargo check --locked
cargo test --locked
```

## 4. 证据边界

3,756 ms 只代表当前机器上、由 v0.1.5 已签名安装包使用的同一冻结 Sidecar 字节，不替代最低支持硬件、杀毒软件实时扫描开启状态及最终安装目录下的复测。冻结完整业务流也以 `-StartupTimeoutSeconds 5` 通过并在授权关闭后确认 launcher/worker 零残留；超过 5 秒仍阻止发布，不能通过扩大脚本超时掩盖回归。

“10 秒内可交互主界面”仍需在干净 Windows 10/11 原生 x64 环境以窗口可交互探针复测；现有 Windows Server 2025 AMD64 与 Windows 11 ARM64 干净 Runner 证明主程序可启动并持续运行，但不等价于交互就绪计时。
