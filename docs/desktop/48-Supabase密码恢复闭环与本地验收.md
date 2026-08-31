# Supabase 密码恢复闭环与本地验收

## 1. 实现结论

桌面端已补齐此前只有“发送恢复邮件”、没有“消费恢复链接并设置新密码”的缺口。当前流程为：

1. 用户输入邮箱，请求 Supabase Auth 发送恢复邮件；
2. 界面切换到设置新密码页，用户粘贴邮件中的完整链接；
3. Rust 可信层校验链接与当前 Supabase endpoint 严格同源，路径必须为 `/auth/v1/verify`，类型必须为 `recovery`；
4. Rust 将邮件 token 交给 GoTrue 验证，获得一次性恢复会话；
5. 使用该会话更新密码，校验响应用户 ID 与恢复会话一致；
6. 尽力退出恢复会话，删除已有登录会话和许可证授权；
7. 用户使用新密码重新登录并重新激活本机许可证。

恢复链接拒绝跨域、用户信息、错误端口、错误路径、URL fragment、重复 `token`、重复 `type`、非恢复类型及异常 token 长度。新密码限定为 8–1024 个字符。

## 2. 凭据处理边界

- 恢复链接和新密码只在 Vue 输入控件、Tauri IPC 参数与 Rust 进程内存中短暂存在；
- 提交前立即清空 Vue 的恢复链接与两次新密码引用；
- 不把恢复 token、密码或恢复会话写入 localStorage、SQLite、系统凭据库或日志；
- 不向 Python Sidecar 传递任何身份凭据；
- 成功后删除旧 Supabase 会话和本地授权，避免旧授权跨密码变更继续使用；
- 错误只返回按 HTTP 状态归类的安全文案，不回显 GoTrue 响应正文。

这里的“不会保存”不等于“从未进入 WebView”：用户粘贴的链接和密码在提交前必然短暂存在于 WebView 内存，并通过一次 Tauri IPC 调用进入 Rust。安全承诺限定为不持久化、不记录、不返回和尽快清空。

## 3. 可重复的本地真实验收

运行：

```powershell
.\scripts\Test-LocalSupabaseAuth.ps1
```

脚本默认复用同级网页版仓库 `STT\.env` 中的 `SUPABASE_PUBLISHABLE_KEY`，并访问：

- GoTrue：`http://127.0.0.1:55421`；
- Mailpit：`http://127.0.0.1:55424`；
- PostgreSQL 容器：`supabase_db_stt-local`。

两个 HTTP endpoint 必须解析为回环地址；容器名必须通过严格字符白名单。脚本不输出 publishable key、邮箱、密码、token、JWT 或邮件正文。

实际验证链路包括：

- 注册随机合成账号；
- 从 Mailpit 取得 signup 邮件并确认邮箱；
- 旧密码登录与退出；
- 请求 recovery 邮件并验证 token；
- 更新密码并退出恢复会话；
- 断言旧密码已被拒绝；
- 新密码登录与退出；
- 按本次用户 UUID 删除账号；
- 按本次邮件 ID 删除两封邮件，不清空 Mailpit 其他邮件。

2026-08-31 已在本机 Docker Supabase 上真实执行通过，测试用户和两封测试邮件均完成精确清理。

## 4. 与 Mock 服务的关系

本次验证使用真实的本地 Supabase Auth、GoTrue 邮件生成和 Mailpit 收信链路，不是身份服务 Mock。`config/services.yaml` 中许可证、支付、生产 SMTP 和更新服务仍保持 Mock；它们没有被本次结果暗示为已接入。

生产环境仍必须配置企业 SMTP、发件域 SPF/DKIM/DMARC、允许的 redirect URL、邮件模板、速率限制和滥用监控。自托管开发环境的 Mailpit 只用于闭环验证，不可作为生产邮件设施。

## 5. 参考依据

- [Supabase Password-based Auth](https://supabase.com/docs/guides/auth/passwords)
- [Supabase Self-hosting Auth configuration](https://supabase.com/docs/guides/self-hosting/auth/config)

Supabase 的密码恢复是两步流程：先发起恢复邮件，再在恢复会话中更新用户密码。桌面实现与本地真实测试均按这两个阶段执行。
