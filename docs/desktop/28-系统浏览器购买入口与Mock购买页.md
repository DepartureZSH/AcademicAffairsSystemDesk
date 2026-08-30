# 系统浏览器购买入口与 Mock 购买页

## 1. 模块结论

无有效许可证时，已登录用户现在可以从设备激活页进入购买流程。远程页面不加载到 Tauri WebView；Rust 可信层只调用系统默认浏览器。当前 `payment.mode: mock` 打开随应用发布的本地静态页面，明确标记“不支付、不发证、不联网”。

## 2. Mock 行为

- 页面来自只读应用资源 `fixtures/mock/purchase.html`，运行时解析后必须仍位于应用资源目录；
- 页面仅显示测试产品和 1 分占位价格，不调用 Supabase、微信支付、SMTP 或许可证接口；
- Rust 返回明确的 `mode / opened / message`，界面展示“不会产生真实订单或扣款”；
- Mock 页面不能生成订单、企业密钥、许可证或付款凭证。

这使本地桌面主体可以独立验证“从特权应用切换到系统浏览器”的交互，而不把 Karios Pay、生产域名或 Supabase 许可证服务当作开发卡点。

## 3. 真实服务边界

`payment.mode: real` 当前保持失败关闭。生产接入时必须先使用有效 Supabase 会话调用 `create-purchase-session`，取得 5 分钟、单次使用且绑定账号的购买会话，再由可信层打开固定的 `https://dean.karios.site/purchase`。在该服务尚未实现前，应用不会直接打开一个缺少账号绑定会话的公开购买 URL。

生产实现仍必须满足：金额由服务端产品表决定、桌面不能提交金额、支付事件幂等、Karios Pay 是支付状态权威来源、Supabase 事务只能履约一次。

## 4. 安全控制

- WebView CSP 保持 `frame-src 'none'`，没有增加远程页面、脚本或表单权限；
- 前端不能向 opener 传入任意 URL 或路径，只能调用无参数的 `open_purchase_page`；
- Mock 文件路径由 Rust 从应用资源目录固定拼接并做 canonical path 包含校验；
- 真实模式在单次购买会话接入前失败关闭，不降级为裸 URL。

## 5. 验收

- Mock 购买页只能从资源目录解析；
- `services.yaml` 的 payment 服务必须显式为 `mock`，测试金额为 1 分；
- 点击购买入口由系统浏览器打开本地页面，不改变 WebView 地址；
- 页面和桌面提示均明确说明不会真实支付；
- Rust、Vue 和完整 Python 回归测试继续通过。
