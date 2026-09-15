# 启动超时与冻结 Sidecar 性能门禁

## 1. 目标

应用主窗口应立即可交互；本地排课服务若提前退出则立即返回错误。PyInstaller 单文件在首次运行、磁盘繁忙或安全软件扫描时需要先解包，不能把正常的冷启动误判为故障，因此另设 30 秒冷启动上限。

## 2. 实现

- Supabase Auth 客户端统一使用 3 秒连接超时和 5 秒整请求超时；登录、注册、密码恢复、会话刷新和退出均复用该客户端。
- 已保存会话刷新失败时继续进入既有离线授权判断，不把暂时断网误判为账号注销。
- Tauri 等待 Sidecar 首行 `ready` 消息的上限为 30 秒；进程提前退出会立即返回，达到上限后清理启动器及其冻结工作进程，并显示不包含内部实现名称的可操作提示。
- 两组时限均由 Rust 单元测试锁定，防止后续无意放宽。
- `Test-FrozenSidecarLifecycle.ps1` 使用同一 30 秒门槛，并输出从 `Start-Process` 到解析首行就绪消息的毫秒数。

主窗口由 Tauri/Vue 直接创建，身份和许可证状态在窗口内异步加载；远程身份请求不会阻塞操作系统窗口创建。未登录状态不发身份网络请求，有本地会话但网络不可用时最多 5 秒进入离线提示。

## 3. 实测证据

2026-09-11 在当前 Windows 11 x64 开发机直接启动 v0.1.7 的 PyInstaller one-file Sidecar：

| 检查项 | 结果 |
| --- | ---: |
| Ready 耗时 | 16,387 ms |
| 门槛 | 30,000 ms |
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

16,387 ms 是当前机器对 v0.1.7 已签名冻结 Sidecar 的直接实测，已经证明原 5 秒门槛会误报失败。该数值不替代最低支持硬件、杀毒软件实时扫描开启状态及最终安装目录下的复测。冻结完整业务流以 `-StartupTimeoutSeconds 30` 验收；发布记录仍须保存实际启动耗时，若持续变慢应优化打包与导入路径，而不能继续放宽上限。

“10 秒内可交互主界面”仍需在干净 Windows 10/11 原生 x64 环境以窗口可交互探针复测；现有 Windows Server 2025 AMD64 与 Windows 11 ARM64 干净 Runner 证明主程序可启动并持续运行，但不等价于交互就绪计时。
