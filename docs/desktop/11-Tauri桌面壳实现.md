# Tauri 桌面壳实现记录

## 1. 本模块范围

本模块建立 Windows 首发桌面壳和本地项目入口，产品标识符固定为 `tech.karios.stt.desktop`。当前实现包含：

- Tauri 2、Vue 3、TypeScript 与 Vite 工程；
- Windows 主窗口、应用图标、CSP 和最小 Tauri capability；
- Rust 托管 Python Sidecar 的启动、代理、状态查询与退出回收；
- 项目工作台、新建项目、最近项目和 Mock 服务状态提示；
- Windows CI 中的前端构建、Rust 格式、编译和单元测试。

学期、基础资料、课程计划、约束、排课、导出和备份页面仍按后续模块逐项开放，当前导航会明确显示“实施中”，避免把未完成入口误认为可用功能。

## 2. 安全进程链路

桌面窗口不能直接获得 Sidecar 的一次性令牌，也不能直接访问随机端口。调用链如下：

1. Rust 生成 256 位随机会话令牌和独立 nonce；
2. Rust 只通过子进程环境变量传入令牌、nonce、工作目录和服务配置路径；
3. Python 绑定 `127.0.0.1` 随机端口，以 HMAC-SHA256 返回 nonce 证明；
4. Rust 校验就绪消息的协议版本、进程 PID 和 HMAC 证明；
5. Vue 仅能调用 Tauri command；Rust 只代理 `/v1/` 路径及 GET、POST、PUT、DELETE 方法；
6. HTTP 请求由 Rust 添加 Bearer 令牌，令牌不会进入 WebView；
7. Tauri 收到退出请求或退出事件时显式终止并回收 Python 子进程。

Windows 下 `uv` 的虚拟环境 `python.exe` 是进程启动器，会造成启动器 PID 与解释器 PID 不同。开发模式因此读取 `.venv/pyvenv.cfg`，直接启动其 `home` 指向的 CPython，并只加载项目 Sidecar 与虚拟环境 `site-packages`。正式发行仍启动安装包内的独立 Sidecar 可执行文件，保持同一套严格 PID 校验。

## 3. 本地数据入口

应用默认工作区由 Tauri 的应用数据目录确定，其下创建 `Workspace/projects/<project-id>`。新建项目通过以下真实链路写入：

`Vue 表单 → Tauri command → Rust 白名单代理 → Python API → ProjectWorkspace → manifest.json + SQLite`

界面会同时展示：

- Sidecar 是否连接及随机端口；
- 协议版本和 SQLite schema 版本；
- 当前工作目录；
- `config/services.yaml` 中处于 Mock 状态的服务。

项目目录是用户业务数据，卸载应用不得默认删除。桌面端后续会增加用户选择工作目录、归档、完整备份和恢复入口。

## 4. 已执行验证

2026-08-31 在 Windows 开发环境完成以下验证：

- `npm run build`：通过 TypeScript 检查和 Vite 生产构建；
- `cargo fmt --check`：通过；
- `cargo check --locked`：通过；
- `cargo test --locked`：2 个 Rust 代理白名单测试通过；
- Python 测试和 Ruff 检查由仓库基线持续执行；
- 桌面窗口连接随机回环端口成功，进程监听地址仅为 `127.0.0.1`；
- 通过真实 UI 创建“桌面端到端验证项目”，生成 schema 1 的 `manifest.json` 和独立 SQLite；
- 关闭最后一个窗口后，Python 进程与随机端口均被回收，无后台残留。

开发环境的端到端验证项目位于本机应用数据目录，不提交 Git，也不包含网页版导入的教务数据。

## 5. 尚未纳入本模块

- Stronghold/Windows Credential Manager 中的设备私钥与凭证；
- Supabase 登录和许可证门禁；
- Python Sidecar 的独立可执行文件打包；
- NSIS/MSI 安装包、自签名和 Tauri updater 签名；
- 用户可见的工作目录选择器与项目归档。

上述内容分别归入身份许可证、桌面打包发布、备份恢复模块，不作为本桌面壳提交的隐含完成项。
