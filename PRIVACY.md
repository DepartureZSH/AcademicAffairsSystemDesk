# 时奕教务排课桌面版隐私说明

更新日期：2026-09-14

**English summary:** Project storage and scheduling remain local. Optional, user-initiated AI features may send task-relevant messages, attachments and academic-affairs context to the user's configured AI provider. AI connection tests send only a fixed test message, not project data. AI credentials stay in the operating system credential store and are excluded from project backups. No analytics, advertising, remote crash reporting or cloud scheduling is added. Provider processing and charges are governed by that provider's policies.

## 本地教务数据

学校、年级、班级、教师、科目、教室、教学任务、约束、课表、算法输入输出、导入文件、项目归档和备份保存在用户选择的本机工作目录。排课算法在本机 Python sidecar 中运行。官方桌面版不会把这些内容上传到 Supabase、支付服务或更新服务。主动使用 AI 时的数据发送例外见下一节；普通排课流程不因此改为云端运行。

项目数据库采用可迁移的明文 SQLite。任何能访问工作目录的本机用户或程序都可能读取这些数据；用户应使用 Windows 账号权限、BitLocker 或等效磁盘加密保护设备和备份介质。

## 自选 AI 服务与数据提示

AI 是可选功能。用户自行配置 API 基础地址、API Key 和模型名称。仅保存配置、打开页面或进入项目不会触发 AI 请求；连接测试需单独确认，只发送固定测试文字，不读取或附带项目资料。

在后续 AI 业务流程中，用户主动发送消息、提交附件或执行 AI 识别与生成时，本次任务所需的消息、附件及相关教务上下文会发送到用户配置的 AI 服务，可能涉及学校、教师、班级、课程及课表信息。界面必须持续显示数据去向提示，发送前应告知本次任务使用的资料；未经用户确认，不得自动发送整库。用户应确认有权提供资料，并尽量先脱敏。AI 结果必须经过用户核对和确认才能修改项目。

AI 服务商可能接收请求来源 IP、模型参数与调用内容；其保存期限、训练用途和费用以该服务商政策为准，本应用不承诺第三方零留存。用户应自行确认供应商符合学校的数据管理要求。配置本机运行的 AI 服务时，处理范围取决于该服务自身的设置。

API Key 由用户在配置表单中输入后存入系统密钥库，不回填到页面、不写入项目或备份、不输出到日志。远程 API 必须使用 HTTPS，仅本机回环地址允许 HTTP；更换 API 地址须重新填写密钥，HTTP 重定向不会被自动跟随。用户可在 AI 设置页清除本机连接配置和密钥；这不会删除已发送给第三方的内容，相关删除请求需向服务商提出。

当前开发代码已接入按场景查询、生成变更清单、确认执行及本地会话保存。对话文本、附件提取文字、工具查询结果和审核记录保存在当前项目的明文 SQLite 中，并随项目归档与备份保留；清空对话会删除本场景消息和模型上下文，但保留变更审核记录，已有备份不会因此被改写。专用课表识别、期望时间向导等流程仍在适配，不应视为完整 AI 功能已上线。正式发布前仍须完成真实服务商兼容测试、网络审计及隐私审核。

## 远程身份与许可证数据

除用户主动使用的 AI 服务外，启用真实服务后，应用为以下目的联网：

- Supabase Auth：邮箱注册、验证、密码登录、密码重置和会话刷新；
- 许可证：账号标识、许可证状态、随机设备 ID、设备公钥/指纹、应用版本和授权结果；
- 支付：由系统浏览器打开外部购买页面，桌面端不收集银行卡或微信支付凭据；
- 更新：应用版本、操作系统和 CPU 架构，用于选择签名更新包。

密码、原始企业密钥、JWT、设备私钥和签名私钥不得进入日志、URL、项目数据库或 WebView。设备私钥、登录会话和授权凭证由系统凭据存储保护。

## IP 与安全日志

真实身份、许可证和支付服务可由可信反向代理记录来源 IP、账号、设备指纹、应用版本、结果码和时间，用于限流、反滥用和安全审计。设计默认保留完整 IP 30 天、HMAC 化风险聚合 180 天；生产启用前仍须完成法律审核并在网站隐私政策中公布最终期限。

## Mock 与开发环境

`config/services.yaml` 会明确标识真实、模拟或停用服务。模拟许可证、支付、SMTP 和更新服务只产生本地确定性测试结果，不应被当作生产交易、正式授权或真实邮件。开发配置不会静默上传教务数据。

## 遥测与崩溃报告

首版不集成第三方行为分析、广告、远程崩溃收集或云端排课。若未来增加任何遥测，必须先更新本文件、界面告知、网络白名单和自动化测试。

## 用户控制

用户可以导出 `.sttproj`、创建 `.sttbackup`、复制或删除自己选择的工作目录。卸载应用默认不删除这些项目数据。退出账号会清除本地会话和授权凭证，但保留设备私钥与项目文件。

## 联系与变更

安全问题请使用 GitHub 仓库的 Private vulnerability reporting 或 Security Advisory，不要在公开 issue 中提交密码、密钥、真实学校资料或可利用漏洞。正式客服、主体信息和权利请求渠道将在远程服务上线前由人工法律审核补充。
