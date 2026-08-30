# Windows 安装器降级保护

## 1. 缺口

`v0.1.0-test.1` 的 Tauri 配置没有显式设置降级策略。Tauri 2 的 Windows bundler 默认 `allowDowngrades: true`，本地生成的 NSIS 脚本也实际包含 `ALLOWDOWNGRADES "true"`；因此不能把“固定 MSI upgradeCode”误当成 NSIS 已阻止降级。

## 2. 修正

`tauri.conf.json` 现在显式配置：

```json
{
  "bundle": {
    "windows": {
      "allowDowngrades": false
    }
  }
}
```

该项使用 Tauri 官方 Windows bundler 的语义版本比较。NSIS 静默安装检测到更高已安装版本时进入 `EarlyChecks` 并中止；交互安装禁用“不卸载直接降级”选择。MSI 继续使用固定 `upgradeCode` 识别同一产品并由 Windows Installer Major Upgrade 规则拒绝降级。

自动测试同时锁定 `allowDowngrades=false` 和既有 `upgradeCode`，防止配置重构后无意恢复默认值或改变产品升级身份。

## 3. 尚需制品验证

配置门禁不替代安装器行为验证。新版本冻结、自签名并发布后，必须在全新 Windows Runner 执行：

1. 安装 `v0.1.0-test.1`；
2. 在用户工作区写入无业务数据的哨兵并记录哈希；
3. 安装新版本，确认产品注册表版本、内层签名和工作区哨兵均正确；
4. 再静默运行旧安装器，断言安装版本仍为新版本、应用文件未被旧字节覆盖、哨兵哈希不变；
5. 卸载新版本并确认用户工作区保留。

NSIS 与 MSI 必须分别通过。完成上述测试前，本模块状态是“配置已修正，制品行为待验证”，不得宣称升级/降级发布门槛已关闭。

参考：Tauri 2 官方 Windows Installer 文档及当前 `@tauri-apps/cli` 配置 schema。
