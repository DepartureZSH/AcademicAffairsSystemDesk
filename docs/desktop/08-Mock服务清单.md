# Mock 服务清单与切换规则

> 本文是所有未就绪外部服务的唯一登记表。运行模式由根目录 `config/services.yaml` 控制；配置文件只保存公开端点、环境变量名称和确定性测试响应，不保存任何秘密。

## 1. 使用原则

- `mode: real`：调用已准备好的真实服务。
- `mode: mock`：调用本地确定性实现，并在界面持续显示“模拟服务”标识。
- `mode: disabled`：功能入口保留但明确不可用，不静默返回成功。
- `staging` 和 `production` 配置禁止 `allow_mock_services: true`，避免模拟授权或支付进入正式发行版。
- 密码、JWT、许可证原始密钥、service-role、私钥和支付 secret 不得写入 YAML；配置只能引用环境变量名称。
- mock 只替代账号、授权、支付、邮件和更新等外部依赖。教师、班级、课程、约束、课表和算法始终使用本地真实实现，不得 mock 为伪业务结果。

## 2. 当前服务状态

| 服务 | YAML 键 | 当前模式 | 实现/数据源 | 切换为真实服务的条件 |
| --- | --- | --- | --- | --- |
| 身份认证 | `services.identity` | `real` | 本机 Docker `stt-local` Supabase，`http://127.0.0.1:55421` | Sealos 预发布 Auth、HTTPS 与 redirect allowlist 准备后替换 endpoint |
| 旧版数据迁移源 | `services.legacy_data` | `real` | 本机 Docker `stt-local` PostgreSQL，只读重复读事务 | 首批项目迁移并核验后可设为 `disabled` |
| 许可证 | `services.license` | `mock` | 本地确定性 7 天授权、3 台设备上限测试适配器 | 许可证 schema、激活/续签接口、签名密钥和撤销测试完成 |
| 支付 | `services.payment` | `mock` | 1 分测试产品、确定性成功状态，不产生真实资金交易 | Karios Pay 权威定价、鉴权、幂等、webhook 与预发布小额支付完成 |
| SMTP | `services.smtp` | `mock` | 邮件写入 `.local/mock-mail`，不向公网发信 | 企业 SMTP、SPF/DKIM/DMARC 与退信流程完成 |
| 自动更新 | `services.updates` | `mock` | 本地静态 manifest，默认无更新 | updater 公钥、测试发布通道与签名制品完成 |

本地 Supabase 仅承载身份验证和作为旧网页版数据的只读迁移源。迁入 SQLite 后，教务数据不再从 Supabase 读取，也不实现反向同步。

## 3. 当前开发配置

配置入口：`config/services.yaml`。

安全约束由 `sidecar/stt_desktop/service_config.py` 强制执行：

1. 配置版本必须为 `1`。
2. 五类服务必须全部显式声明。
3. `staging/production` 禁止 mock，并要求远端 endpoint 使用 HTTPS。
4. `allow_mock_services: false` 时，任何单项 `mode: mock` 都会导致启动失败。
5. 疑似秘密字段会导致配置拒绝加载；环境变量引用必须使用 `*_env` 语义或 `env` 映射。

## 4. Mock 行为与验收

### 4.1 许可证

- 为本地测试账号返回 7 天有效期和最多 3 台设备。
- 后续设备密钥模块仍必须执行真实签名/验签；mock 不能绕过设备私钥证明。
- 支持通过测试夹具切换有效、过期、撤销、第四台设备和时钟回拨场景。

### 4.2 支付

- 只使用产品代码 `STT_DESKTOP_YEARLY_TEST` 和 1 分测试金额。
- 返回确定性的异步完成状态，便于测试购买页面轮询。
- mock 支付不会签发可用于 production 的授权凭证。

### 4.3 SMTP

- 每封邮件保存为独立的本地结构化文件，正文中的密钥仅用于测试夹具。
- 测试完成后允许整体清理 `.local`，该目录必须保持 Git 忽略。

### 4.4 更新器

- 默认报告无更新。
- 后续可用本地静态 manifest 测试版本比较、签名失败和回滚，不访问公网更新域名。

## 5. 切换记录模板

每次服务模式变化必须在提交中同时更新本表：

| 日期 | 服务 | 原模式 | 新模式 | 环境 | 验证证据 | 提交 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08-31 | identity | 未配置 | real | development | 本机 Supabase 容器和数据表只读核验 | 待本模块提交 |
| 2026-08-31 | license/payment/smtp/updates | 未配置 | mock | development | 配置加载与安全拒绝测试 | 待本模块提交 |
| 2026-08-31 | identity | real | real | development | 桌面端经 Rust 可信层完成本机 Supabase 密码登录 | 切换 Sealos 时只更换 HTTPS endpoint 与 publishable key |
| 2026-08-31 | license | mock | mock | development | 企业密钥、设备 Ed25519 签名、7 天凭证、Sidecar 门禁和退出清理已实测 | 真实激活/续签 Edge Function、服务端 JWS 与撤销接口完成后切换 |
