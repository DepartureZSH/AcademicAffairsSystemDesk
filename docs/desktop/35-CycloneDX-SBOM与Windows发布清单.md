# CycloneDX SBOM 与 Windows 发布清单

## 1. 模块结论

发布证据现在同时提供人工可审计的依赖清单、标准 CycloneDX 1.6 SBOM、Windows 制品 manifest 和 `SHA256SUMS.txt`。这些文件不包含私钥、签名密码、PFX 或 Supabase/支付秘密，可以随测试版 Release 一起公开。

## 2. 依赖与 SBOM

执行：

```powershell
uv run python scripts/generate_dependency_inventory.py
```

生成：

- `build/compliance/dependency-inventory.json`；
- `build/compliance/dependency-sbom.cdx.json`。

两者均由锁定的 Python 环境、`package-lock.json` 和 `cargo metadata --locked` 离线生成。任一依赖缺失许可证元数据都会返回非零退出码。CycloneDX 为每个组件记录生态、名称、版本、purl、许可证名称和可用的来源地址；CI 同时上传两个文件。

## 3. 签名后发布清单

安装包完成 Authenticode 和 updater 签名并通过 `Test-WindowsRelease.ps1` 后执行：

```powershell
$thumbprint = (Get-ChildItem Cert:\CurrentUser\My |
  Where-Object FriendlyName -eq 'Karios Desktop TEST ONLY Code Signing' |
  Sort-Object NotAfter -Descending |
  Select-Object -First 1).Thumbprint

uv run python scripts/generate_release_manifest.py `
  --artifact 'apps/desktop/src-tauri/target/release/bundle/nsis/时奕教务排课_0.1.0_x64-setup.exe' `
  --artifact 'apps/desktop/src-tauri/target/release/bundle/msi/时奕教务排课_0.1.0_x64_zh-CN.msi' `
  --authenticode-thumbprint $thumbprint `
  --require-updater-signature
```

输出位于 `build/release/`，包含应用标识、版本、Git commit、公开证书指纹、签名顺序、每个安装包和 `.sig` 的大小与 SHA-256，以及依赖清单/SBOM 哈希。

生成器要求制品是存在的 `.exe` 或 `.msi`；使用 `--require-updater-signature` 时，缺少同名 `.sig` 会失败。它不自行声称 Authenticode 有效，正式发布仍必须先保存验签日志或 SignPath 审批证据。

## 4. 发布顺序

1. 在锁定提交构建未签名制品；
2. 自签名测试或 SignPath Authenticode；
3. 验证外层与内层签名和时间戳；
4. 对最终字节生成 updater `.sig` 并验证；
5. 生成依赖清单、CycloneDX SBOM、release manifest 和校验和；
6. 人工审批后上传不可变 Release 资产。

发布清单中的 `self-signed-test` 必须在切换 SignPath 后改为对应正式签名配置；不得把自签名测试证据描述成 Foundation OV 签名。
