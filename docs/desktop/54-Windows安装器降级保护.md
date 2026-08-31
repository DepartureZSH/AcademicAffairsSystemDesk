# Windows 安装器降级保护

## 1. 缺口

`v0.1.0-test.1` 的 Tauri 配置没有显式设置降级策略。Tauri 2 的 Windows bundler 默认 `allowDowngrades: true`，本地生成的 NSIS 脚本也实际包含 `ALLOWDOWNGRADES "true"`；因此不能把“固定 MSI upgradeCode”误当成 NSIS 已阻止降级。

## 2. 第一层修正与实际缺陷

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

该项使用 Tauri 官方 Windows bundler 的语义版本比较。MSI 继续使用固定 `upgradeCode` 识别同一产品并由 Windows Installer Major Upgrade 规则拒绝降级。

但 `v0.1.2-test.3 → v0.1.3-test.4 → 再运行旧 v0.1.2 NSIS` 的真实测试证明，仅设置 `allowDowngrades=false` 仍不足：旧 NSIS 在静默页面流中把已安装 0.1.3 覆盖回 0.1.2。这个失败被保留在 [历史运行 33345920400](https://github.com/DepartureZSH/AcademicAffairsSystemDesk/actions/runs/33345920400) 中，不能用配置推断替代真实制品行为。

自动测试同时锁定 `allowDowngrades=false` 和既有 `upgradeCode`，防止配置重构后无意恢复默认值或改变产品升级身份。

## 3. 安装器级修复

项目固定 Tauri 2.11.5 官方 NSIS 模板 `apps/desktop/src-tauri/nsis/installer.nsi`，并记录上游 Git blob `d372e3c391770cf231db974422a1e4f8adaac3a6`。新增 `KariosAbortDowngrade`，在 `.onInit` 设置安装上下文后、创建安装器页面和执行卸载/覆盖之前：

1. 读取当前用户 NSIS 卸载注册项；
2. 对相同名称和 Publisher 的机器级 MSI 注册项作兼容检查；
3. 用 `nsis_tauri_utils::SemverCompare` 比较已安装版本与待安装版本；
4. 若待安装版本更旧，静默和交互模式都以退出码 10 立即终止。

`Test-NsisSelfDowngradeGuard.ps1` 还会在不存在真实安装的前提下创建带随机标记的 9.0.0 测试注册项，运行 0.1.5 安装器并断言退出码 10、注册项未变、安装目录未创建，最后只删除标记匹配的测试项。

## 4. 制品验证结果

[`v0.1.4-test.5 → v0.1.5-test.6` 真实运行](https://github.com/DepartureZSH/AcademicAffairsSystemDesk/actions/runs/33352330535) 已在 Windows Server 2025 AMD64 分别验证：

- NSIS 升级退出码 0，旧 0.1.4 降级退出码 10；
- MSI 升级退出码 0，旧 0.1.4 降级退出码 1603；
- 两种安装器的注册表版本、桌面主程序和 Sidecar 新版哈希均未被旧安装器改变；
- 用户工作区哨兵在升级、降级尝试和卸载后保持。

因此本模块的自动制品门禁已关闭；原生 Windows 10/11 x64 人工抽检仍保留为发布环境覆盖项。

参考：Tauri 2 官方 Windows Installer 文档及当前 `@tauri-apps/cli` 配置 schema。
