# 时奕教务排课

时奕教务排课是面向中小学的跨平台本地排课桌面应用。Windows 10/11 x64 为首发平台，桌面壳采用 Tauri 2，排课数据与算法完全保存在本机并在本机运行。

当前仓库已完成本地桌面主体功能闭环，正在刷新 Windows 发布制品并等待外部许可证、支付、SMTP 和正式更新服务。产品范围、架构、授权、测试、签名发布和人工准备要求见 [`docs/desktop`](./docs/desktop/)。

## 当前状态

- Tauri 2 + Vue 3 桌面壳、安全 Sidecar、版本化 SQLite、项目工作区和 Windows Credential Manager 门禁已接通。
- 本地项目支持新建、打开、关闭、另存、归档、隔离回收、完整备份和恢复。
- 学期作息、基础资料、课程计划、教学任务、可视化约束和批量导入已形成完整本地流程。
- 自动排课、运行前预检、取消、Warm start、候选比较、手工调整和冲突诊断均在本机执行。
- 班级/教师/教室/年级课表可导出 CSV、Excel、PDF、Problem XML 和 Solution XML。
- 6000 课次基准在当前验收机 25.762 秒生成硬约束 0 的完整候选。
- `config/services.yaml` 中身份和旧数据迁移源为本机真实 Supabase；许可证、支付、SMTP 和远程更新仍明确为 Mock，不能用于生产发行。
- 最新需求追踪与未完成发布门槛见 [`docs/desktop/46-需求追踪与发布就绪审计.md`](./docs/desktop/46-需求追踪与发布就绪审计.md)。

## 开发基线

Python 配置层使用 `uv` 管理依赖：

```powershell
uv sync --extra dev
uv run pytest
```

外部服务模拟范围和切换条件见 [`docs/desktop/08-Mock服务清单.md`](./docs/desktop/08-Mock服务清单.md)。本地排课业务数据和算法不使用 mock。

已有网页版 Supabase 项目可通过 `scripts/import-local-supabase.ps1` 只读迁入本地 SQLite，操作和字段边界见 [`docs/desktop/09-网页版数据本地迁移.md`](./docs/desktop/09-网页版数据本地迁移.md)。

本地服务通过回环随机端口和一次性令牌向 Tauri 提供项目 API，协议与安全边界见 [`docs/desktop/10-本地Sidecar协议实现.md`](./docs/desktop/10-本地Sidecar协议实现.md)。

## 桌面端开发

Windows 开发模式先准备 Python 环境，再启动 Tauri：

```powershell
uv sync --extra dev
cd apps/desktop
npm ci
npm run tauri:dev
```

如果本机网页版仓库的 `.env` 已配置 `SUPABASE_PUBLISHABLE_KEY`，可从桌面仓库根目录使用安全启动脚本；脚本只把 publishable key 注入当前子进程，不打印或复制到仓库：

```powershell
.\scripts\start-desktop-dev.ps1
```

也可以显式传入环境文件路径：

```powershell
.\scripts\start-desktop-dev.ps1 -SupabaseEnvFile 'D:\path\to\supabase.env'
```

前端静态检查和 Rust 桌面层检查：

```powershell
cd apps/desktop
npm run build
cd src-tauri
cargo fmt --check
cargo check --locked
cargo test --locked
```

桌面壳当前实现范围、进程身份校验和端到端验证记录见 [`docs/desktop/11-Tauri桌面壳实现.md`](./docs/desktop/11-Tauri桌面壳实现.md)。

Supabase 登录、Windows Credential Manager、设备 Ed25519 密钥和 YAML Mock 许可证门禁见 [`docs/desktop/12-身份与许可证门禁实现.md`](./docs/desktop/12-身份与许可证门禁实现.md)。开发环境的 Mock 激活码为 `KARIOS-MOCK-LOCAL-2026`，仅用于本地测试，不是生产企业密钥。

学年、学期、作息表、课节和学校基础资料的桌面流程见 [`docs/desktop/13-学期作息与基础资料实现.md`](./docs/desktop/13-学期作息与基础资料实现.md)。

课程计划、教学任务、原子课次生成和可视化约束配置见 [`docs/desktop/14-课程计划任务与约束实现.md`](./docs/desktop/14-课程计划任务与约束实现.md) 与 [`docs/desktop/44-可视化约束参数与任务范围.md`](./docs/desktop/44-可视化约束参数与任务范围.md)。

## 开源许可证

源代码采用 [Apache License 2.0](./LICENSE)。项目名称、图标、官方发布渠道和代码签名身份不随该许可证授权；第三方构建不得冒充官方发行版。
