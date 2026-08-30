# 时奕教务排课

时奕教务排课是面向中小学的跨平台本地排课桌面应用。Windows 10/11 x64 为首发平台，桌面壳采用 Tauri 2，排课数据与算法完全保存在本机并在本机运行。

当前仓库已进入桌面主体实施阶段。产品范围、架构、授权、测试、签名发布和人工准备要求见 [`docs/desktop`](./docs/desktop/)。

## 当前状态

- 已完成第一阶段需求和架构文档。
- G0 本地开发环境与独立公开仓库已准备完成。
- 已进入 `codex/desktop-local` 实施分支；外部依赖由 `config/services.yaml` 分项切换 real/mock。
- 已建立 Tauri 2 + Vue 3 桌面壳、安全 Sidecar 生命周期和本地项目工作台。

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

## 开源许可证

源代码采用 [Apache License 2.0](./LICENSE)。项目名称、图标、官方发布渠道和代码签名身份不随该许可证授权；第三方构建不得冒充官方发行版。
