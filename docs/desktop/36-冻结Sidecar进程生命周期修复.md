# 冻结 Sidecar 进程生命周期修复

## 1. 问题与结论

PyInstaller `--onefile` 在 Windows 上先运行外层启动器，再启动负责执行 Python 服务的内部工作进程。旧版就绪消息只报告 `os.getpid()`，因此 Tauri 启动的外层 PID 与消息中的内部 PID 不一致；若直接终止外层启动器，内部 Uvicorn 工作进程还可能继续监听随机本机端口。

本模块已把两个进程身份分开，并以授权优雅关闭为主、精确进程校验后的强制终止为兜底。打包实测中，健康接口与关闭接口均成功，关闭后两个 PID 均不存在。

## 2. 协议与退出行为

sidecar 的首行 JSON 现在包含：

- `pid`：Tauri 直接启动并持有的外层启动器 PID；
- `workerPid`：实际运行本地 API 的内部工作进程 PID；
- 原有随机端口、协议版本和 nonce HMAC 证明。

源码开发模式没有 PyInstaller 外层启动器，因此两个 PID 相同。冻结 one-file 模式通过 PyInstaller 设置的 `_PYI_APPLICATION_HOME_DIR` 识别，并把父 PID 作为外层启动器 PID。Tauri 必须验证 `pid == child.id()`，且 `workerPid` 为有效非零值。

新增 `POST /v1/runtime/shutdown`，它与其余本机 API 一样要求随机会话 Bearer token、回环来源和 Origin 白名单。接口响应后触发 Uvicorn 的 `should_exit`，应用 lifespan 负责停止排课任务并关闭当前项目，随后 PyInstaller 外层启动器自然退出并清理解包目录。

若五秒内不能自然退出，Tauri 只会在内部 PID 对应进程的规范化可执行文件路径与本次启动的 sidecar 完全相同时终止它，再终止持有的外层子进程。这避免对复用 PID 的无关进程执行强制终止。

## 3. 自动验证

先构建冻结 sidecar：

```powershell
.\scripts\build-sidecar.ps1
```

再运行生命周期冒烟测试：

```powershell
.\scripts\Test-FrozenSidecarLifecycle.ps1
```

脚本使用随机 token、nonce、随机端口和系统临时工作目录；以隐藏窗口启动冻结程序，断言外层/内部 PID、调用健康与授权关闭接口、等待外层退出，再断言两个 PID 都已消失。清理前会验证进程可执行文件精确路径和临时目录父路径。

源码回归还覆盖：

- 非冻结模式 PID 语义；
- 冻结 one-file 模式父/子 PID 语义；
- 关闭接口必须认证且能触发事件；
- Rust 就绪消息必须包含 `workerPid`。

## 4. 发布门槛

每次修改 sidecar、PyInstaller、Uvicorn、Tauri 启停逻辑或安装包资源布局后，都必须重新执行冻结生命周期测试。该测试通过后才能构建安装包；安装包还需继续完成内部/外层 Authenticode、Tauri updater Ed25519 和干净 Windows 安装验证。
