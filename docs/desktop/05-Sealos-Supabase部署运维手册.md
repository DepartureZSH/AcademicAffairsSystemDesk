# Sealos 自托管 Supabase 部署与运维手册

> 本文描述目标拓扑、部署检查、秘密管理、备份和日常运维。它不是对当前生产环境执行变更的授权。所有变更先在预发布副本验证。

## 1. 目标拓扑

建议把许可证系统与现有教务 Web 服务分开授权，即使它们部署在同一 Sealos 集群：

```text
公网入口 / WAF / TLS
  ├─ dean.karios.site
  │    └─ web-admin：登录、购买页、许可证运营页
  ├─ auth/API 域名
  │    └─ Supabase Kong / Auth / REST / Edge Runtime
  └─ Karios 签名 webhook

Sealos 私网
  ├─ Supabase Postgres
  ├─ Supabase Auth / Kong / Edge Runtime
  ├─ license-worker（SMTP、对账、清理）
  └─ 监控与加密备份任务
```

生产、预发布必须使用不同数据库、域名、密钥、SMTP 发件人、支付项目凭据和更新 channel。不得用表字段区分环境。

## 2. 人工准备参数

部署前建立一份不入 Git 的参数登记表：

| 类别 | 参数 |
| --- | --- |
| 域名 | Supabase 公网 URL、`dean.karios.site`、Karios webhook URL |
| 数据库 | 主机、端口、数据库、受限应用用户、迁移用户、备份用户 |
| Auth | site URL、允许 redirect URL、JWT issuer/audience、邮件确认策略 |
| SMTP | host、port、TLS 模式、username、password、from、reply-to |
| 许可证 | key pepper、邮件 AES key、entitlement Ed25519 key 与 `kid` |
| 支付 | Karios project ID、请求密钥、webhook 密钥、允许来源 |
| 运维 | 初始 license operator 用户、告警地址、备份目标、保留期 |

真实值只写入密码管理器和 Sealos Secret；文档只记录 Secret 名称、负责人和轮换日期。

## 3. Secret 命名与权限

建议名称：

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SECRET_KEY
DATABASE_URL_LICENSE_RUNTIME
DATABASE_URL_LICENSE_MIGRATOR
LICENSE_KEY_PEPPER_V1
LICENSE_EMAIL_AES_KEY_V1
LICENSE_ENTITLEMENT_ED25519_PRIVATE_V1
LICENSE_ENTITLEMENT_ED25519_PUBLIC_V1
KARIOS_PAY_BASE_URL
KARIOS_PAY_PROJECT_ID
KARIOS_PAY_REQUEST_SECRET
KARIOS_PAY_WEBHOOK_SECRET
SMTP_HOST
SMTP_PORT
SMTP_TLS_MODE
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
```

- Vue 构建只允许 Supabase URL 和 publishable key。
- Edge Function/worker 使用专用最小权限数据库连接；避免所有服务共用超级用户。
- 迁移凭据只在部署 job 中短时挂载。
- Secret 变更通过重启滚动生效，旧 pod 退出后确认内存和日志中无旧值。
- 密钥轮换必须记录 `kid/version`，不得直接覆盖导致现有客户端全部失效。

## 4. 部署前只读盘点

在 Sealos 控制台或受控终端记录：

- Supabase Docker 镜像版本、PostgreSQL 主版本和扩展列表。
- Auth、Kong、PostgREST、Realtime、Storage、Edge Runtime 的健康状态。
- 数据库容量、连接数、备份方式和最近一次恢复结果。
- 入口控制器实际传递的客户端 IP header 及可信代理跳数。
- 当前 `site_url`、redirect allowlist、JWT 有效期、注册和邮箱确认配置。
- 自定义 SMTP、DKIM/SPF/DMARC、限流和退信处理状态。
- Cron、Vault/Secret、网络策略和持久卷能力。

不要假定 Supabase Cloud 文档中的托管能力在自托管 Docker 版本中默认启用。缺少的 Cron、Vault 或 Edge 能力必须由 Sealos job、Secret 和内部服务替代并记录。

## 5. 预发布副本

1. 对当前空 Supabase 环境做初始快照，记录恢复方法。
2. 建立独立预发布 namespace、数据库和域名。
3. 使用全新测试密钥，不复制生产 secret。
4. 应用当前仓库 migrations，并运行 schema/RLS 测试。
5. 部署许可证 migrations、Edge Functions、license-worker 和 Web 路由。
6. 连接 Karios Pay 测试项目或 mock，不连接生产产品。
7. 配置仅供测试的 SMTP 发件人和收件人 allowlist。
8. 完成端到端测试和恢复演练后，才编写生产变更单。

## 6. 数据库发布流程

### 6.1 发布前

- 备份并实际验证备份可读。
- 输出当前 migration 版本和 schema 摘要。
- 评估锁表、回填量、索引空间和回滚策略。
- 检查 migration 没有 secret、真实邮箱、产品价格或环境域名。
- 在与生产相同 PostgreSQL 主版本的预发布库计时演练。

### 6.2 执行

1. 进入维护窗口，暂停 license-worker 和对账任务。
2. 保持认证读取可用；涉及不兼容更改时临时关闭相关写接口。
3. 使用迁移专用用户按版本顺序执行。
4. 验证表、约束、索引、函数 owner、grant、RLS 和 schema 暴露列表。
5. 执行匿名、本人、其他用户、运营员 AAL1/AAL2 权限测试。
6. 先发布向后兼容服务，再恢复 worker。
7. 观察错误率和数据库锁；完成变更记录。

### 6.3 数据库安全要求

- `license` schema 不加入 PostgREST `db-schemas`。
- public 中的许可证视图/函数默认撤销 anon/authenticated 权限，再按需要显式授予。
- `SECURITY DEFINER` 函数限定 owner、固定 `search_path`、schema 限定对象，并限制 execute。
- webhook 事务通过唯一键保证幂等，不依赖应用层“先查再写”。
- 审计表拒绝 update/delete；清理任务只处理明确允许过期的数据表。

## 7. Auth 与 SMTP

### 7.1 Auth

- 生产强制邮箱确认。
- redirect allowlist 只包含正式 HTTPS 页面，不使用通配符生产域名。
- 密码最小长度、泄漏密码策略和速率限制按正式安全评审配置。
- 运营员启用 TOTP MFA；运营接口校验 `aal2`，不能只看前端状态。
- 账号锁定、邮件轰炸和密码重置需要独立限流与告警。

### 7.2 SMTP

- Supabase Auth 与 license-worker 可复用同一企业供应商，但使用不同发件地址或子域以隔离声誉。
- 使用 STARTTLS 或 SMTPS；禁止明文认证。
- 完成 SPF、DKIM、DMARC，关闭供应商可能破坏认证链接的一键追踪功能。
- 配置退信和投诉处理；无效地址不得无限重试。
- 先向内部邮箱和不同主流邮箱域发送测试，检查垃圾箱和中文编码。

Supabase 默认 SMTP 仅供开发测试，生产配置依据：<https://supabase.com/docs/guides/auth/auth-smtp>。

## 8. Edge Function 与 license-worker

### 8.1 Edge Function

- 公共 webhook 使用 `verify_jwt=false` 时，函数必须自行验证 Karios HMAC、时间戳、nonce 和 body hash。
- 用户接口要求 publishable `apikey` 与用户 `Authorization: Bearer` JWT，并校验 JWT 签名和 claims。
- 设置请求体上限、执行超时、数据库超时和安全 CORS allowlist。
- 返回稳定错误码，不向客户端返回数据库、SMTP 或支付原始错误。
- 结构化日志默认脱敏；Authorization、Cookie 和请求体不进入日志。

### 8.2 license-worker

- 只接受私网健康检查；无公开业务 API。
- 使用非 root 容器、只读根文件系统和最小 Linux capabilities。
- 邮件和对账队列采用原子领取、租约超时和幂等处理。
- 优雅停机时停止领取新任务并完成/释放当前租约。
- `/healthz` 分别报告进程、数据库和队列状态，但不返回配置值。

## 9. 可信客户端 IP

1. 在预发布发送带伪造 `X-Forwarded-For` 的请求。
2. 观察入口控制器是否覆盖而不是追加不可信 header。
3. 明确唯一可信 header、代理网段和 hop 数。
4. 应用只从可信代理写入的地址取客户端 IP；无法确认时记录为 unknown。
5. 不把 IP 作为许可证唯一绑定标识。

代理配置变更后必须重新执行测试，否则攻击者可能伪造 IP 绕过限流或污染风险记录。

## 10. 备份与恢复

最低策略：

- 每日一次加密逻辑备份，包含 Auth 所需 schema、public 业务身份表和私有 license schema。
- 数据库持久卷使用平台快照作为第二层保护，但快照不能替代逻辑备份。
- 备份密钥与备份文件分开保管。
- 每周自动验证文件哈希和可解密性。
- 每月至少一次恢复到隔离 namespace，执行登录、订单、许可证、RLS 和计数校验。
- 备份成功/失败、大小异常和超过 RPO 未执行都触发告警。

恢复操作见《07-备份恢复与故障处理》。恢复生产前必须先隔离支付 webhook 和邮件 worker，防止旧 outbox 被重复消费。

## 11. 监控与告警

| 指标 | 建议告警 |
| --- | --- |
| Auth 登录/注册错误率 | 5 分钟明显高于基线 |
| Edge Function 5xx/超时 | 连续 5 分钟或单个关键接口异常 |
| webhook 签名失败 | 突增或同来源重复 |
| 支付待处理时长 | 超过订单过期/对账阈值 |
| outbox 队列深度/最老年龄 | 持续增长或超过 10 分钟 |
| 死信数量 | 任意新增均通知运营 |
| 许可证激活失败/限流 | 突增或集中账号/IP |
| 数据库连接、锁、磁盘 | 达到容量规划阈值 |
| 备份 | 24 小时无成功备份 |

日志必须含 correlation ID 和环境，不含任何 secret、原始密钥、JWT、完整 IP 查询结果或教务业务数据。

## 12. 日常运维

### 每日

- 检查备份、支付对账、邮件死信和风险标记。
- 检查证书/域名/磁盘告警和关键服务错误率。

### 每周

- 验证备份哈希及抽样解密。
- 检查管理员、Sealos 和 GitHub 访问权限变更。
- 复核 pending 订单、异常退款和超期 outbox。

### 每月

- 在隔离环境执行恢复演练。
- 复核依赖和 Supabase Docker 安全更新，先预发布升级。
- 审核许可证运营日志、风险规则误报和数据到期清理。
- 检查 Ed25519、HMAC、SMTP、支付密钥和证书的轮换日期。

## 13. 生产发布检查

- [ ] 预发布与生产资源、域名和 secret 完全隔离。
- [ ] 最近备份已在隔离环境恢复成功。
- [ ] RLS 和 AAL2 权限测试通过。
- [ ] 企业 SMTP、SPF、DKIM、DMARC 通过。
- [ ] Karios 服务鉴权、权威定价、幂等和签名回调通过。
- [ ] 可信代理 IP 解析通过伪造 header 测试。
- [ ] worker 死信、重试、停止和恢复行为通过。
- [ ] dashboards、告警接收人和操作手册已就绪。
- [ ] 生产价格、退款政策、隐私政策经人工确认。
