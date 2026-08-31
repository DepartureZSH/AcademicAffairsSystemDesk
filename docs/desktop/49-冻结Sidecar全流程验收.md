# 冻结 Sidecar 全流程验收

## 1. 验收目的

源码态单元测试不能证明 PyInstaller 冻结制品实际包含 OR-Tools、PDF/XLSX/XML 导出、SQLite 迁移和多进程排课所需的全部模块。本验收直接启动随 Windows 安装包分发的 `stt-sidecar-x86_64-pc-windows-msvc.exe`，通过与 Tauri 相同的随机 Bearer token、nonce、回环端口和 Origin 约束调用本地 API。

可重复命令：

```powershell
.\scripts\Test-FrozenDesktopWorkflow.ps1
```

## 2. 覆盖流程

脚本在系统临时目录创建独立工作区并执行：

1. 启动冻结 launcher/worker，检查协议版本、健康状态与 `config/services.yaml` 服务模式；
2. 新建本地项目，逐 Revision 写入学期、作息、课节、教师、科目、年级和班级；
3. 保存教学任务并原子生成 2 条课次；
4. 执行只读排课预检，确认不存在阻断错误；
5. 发起第一轮异步排课，轮询到成功候选并确认 2 条课表项、硬约束 0；
6. 以第一候选为 parent、同一 session 执行第二轮 warm start，确认两轮和候选父子关系均保留；
7. 导出 CSV、XLSX、PDF、Problem XML、Solution XML；
8. 分别校验 UTF-8 BOM、ZIP、PDF 魔数和 XML 本地根节点；
9. 创建 `.sttbackup`、校验备份并恢复为独立项目；
10. 导出 `.sttproj` 并导入为第三个独立项目，确认候选数据保留；
11. 关闭项目和运行时，确认 launcher/worker 均退出；
12. 校验临时目录父路径和固定前缀后精确清理。

所有调用只访问 Sidecar 声明的 `127.0.0.1` 随机端口。脚本不输出会话 token，也不会复用用户项目工作区。

## 3. 2026-08-31 实际结果

测试对象 SHA-256：

```text
187D8E8FEF71A92D11F0C6C14BC1A3E57215CE4E75FE745137C24AE965C62C48
```

结果：

| 指标 | 结果 |
| --- | ---: |
| 协议版本 | 1 |
| 独立项目数 | 3 |
| 排课轮次 | 2 |
| 候选课表项 | 2 |
| 硬约束违例 | 0 |
| 导出类型 | 5 |
| 备份校验 | 通过 |
| 项目归档校验 | 通过 |
| launcher 残留 | 0 |
| worker 残留 | 0 |
| `stt-frozen-workflow-*` 临时目录残留 | 0 |

两次脚本调试失败均发生在验收代码读取响应字段/XML namespace 的断言层，业务流程已返回成功；修正验收脚本后完整链路通过，没有为迎合测试修改 Sidecar 业务实现。

## 4. 证据边界

当前哈希对应 `v0.1.0-test.1` 基线使用的冻结 Sidecar。它验证该历史冻结制品的本地业务完整性；密码恢复属于 Tauri/Rust 身份层，不在 Sidecar 中。当前分支最终重建 `test.2` 后必须再次运行本脚本，并把新哈希写入新的发布证据，不能用本记录替代新制品验收。

本脚本没有替代干净 Windows 10/11 虚拟机中的安装、卸载、证书信任、升级/降级和用户数据保留测试；这些仍是独立发布门槛。
