# 本地 Sidecar 协议实现

## 1. 启动握手

当前实现入口为 `stt-sidecar`。Tauri 主进程启动子进程时通过仅属于子进程的环境传入：

- `STT_SIDECAR_TOKEN`：至少256位随机会话令牌。
- `STT_SIDECAR_NONCE`：本次启动随机 nonce。
- `STT_WORKSPACE_PATH`：用户选择的工作目录。
- `STT_SERVICES_CONFIG`：服务模式 YAML 路径。

sidecar 读取后立即从自身环境删除令牌、nonce 和工作目录变量，绑定 `127.0.0.1:0`，并在标准输出写入一行紧凑 JSON：

```json
{"event":"ready","port":49152,"pid":1234,"protocolVersion":"1","nonceProof":"<HMAC-SHA256>"}
```

`nonceProof` 使用会话令牌对 nonce 做 HMAC-SHA256。Tauri 必须校验证明、协议版本、进程 ID 和随机端口后才允许转发业务命令。就绪消息不含会话令牌。

## 2. 请求保护

- 只接受回环客户端；监听 socket 不绑定局域网或公网地址。
- 每个请求必须使用 `Authorization: Bearer <session-token>`，采用恒定时间比较。
- 如果请求包含 `Origin`，只允许 `tauri://localhost`、`http://tauri.localhost` 和 `https://tauri.localhost`。
- 缺少或错误令牌返回 `401 SESSION_TOKEN_INVALID`；错误来源返回 `403 ORIGIN_REJECTED`。
- 每个响应包含 `X-Correlation-ID` 和 `Cache-Control: no-store`。
- 错误响应不回显请求数据、密码、JWT、企业密钥或文件内容。

Vue WebView 不获得令牌。后续 Rust 命令层保存令牌并代替前端调用 sidecar，因此正常请求可以不包含浏览器 Origin。

## 3. 已实现接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v1/health` | 协议、schema、服务 real/mock 状态和项目打开状态 |
| GET/POST | `/v1/projects` | 列出、新建并打开本地项目 |
| POST | `/v1/projects/{id}/open` | 打开项目并获得当前 revision |
| GET | `/v1/projects/current` | 当前项目信息 |
| POST | `/v1/projects/current/close` | checkpoint 并关闭当前项目 |
| GET | `/v1/data/{entity_type}` | 查询实体列表和 revision |
| GET | `/v1/data/{entity_type}/{id}` | 查询单个实体 |
| PUT | `/v1/data/{entity_type}` | 新建或更新；必须携带 `expected_revision` |
| DELETE | `/v1/data/{entity_type}/{id}` | 删除；必须携带 `expected_revision` |

长时间排课、备份、导入和导出接口将在对应模块加入。数据库 CRUD 在同一事件循环串行执行；求解器放入独立工作进程，避免阻塞 API 或跨线程共享 SQLite 连接。

## 4. 错误结构

所有已知错误使用统一结构：

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "项目版本冲突：期望 0，当前 1",
    "details": {"expected": 0, "actual": 1},
    "correlationId": "本机随机 ID"
  }
}
```

已区分 revision 冲突、项目锁、schema 过新、请求校验、数据完整性和未预期错误。500 响应只显示固定安全文案，不把异常栈或 SQL 返回给 WebView。

## 5. 验证记录

- 自动测试覆盖回环地址判断、令牌缺失、恶意 Origin、无 Origin 的 Rust 代理请求、项目创建/关闭/重开、实体保存、旧 revision 冲突和错误脱敏。
- 真实子进程冒烟已验证：随机端口、`127.0.0.1` 监听、nonce HMAC、协议版本和带令牌健康检查均通过。
- 冒烟令牌由系统随机数生成，仅存在于测试父/子进程环境，未写入命令参数或标准输出。
