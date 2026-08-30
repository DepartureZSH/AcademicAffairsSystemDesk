# 时奕教务排课

时奕教务排课是面向中小学的跨平台本地排课桌面应用。Windows 10/11 x64 为首发平台，桌面壳采用 Tauri 2，排课数据与算法完全保存在本机并在本机运行。

当前仓库处于实施准备阶段。产品范围、架构、授权、测试、签名发布和人工准备要求见 [`docs/desktop`](./docs/desktop/)。

## 当前状态

- 已完成第一阶段需求和架构文档。
- G0 本地开发环境与独立公开仓库已准备完成。
- 已进入 `codex/desktop-local` 实施分支；外部依赖由 `config/services.yaml` 分项切换 real/mock。

## 开发基线

Python 配置层使用 `uv` 管理依赖：

```powershell
uv sync --extra dev
uv run pytest
```

外部服务模拟范围和切换条件见 [`docs/desktop/08-Mock服务清单.md`](./docs/desktop/08-Mock服务清单.md)。本地排课业务数据和算法不使用 mock。

## 开源许可证

源代码采用 [Apache License 2.0](./LICENSE)。项目名称、图标、官方发布渠道和代码签名身份不随该许可证授权；第三方构建不得冒充官方发行版。
