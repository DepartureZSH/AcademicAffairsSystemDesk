# 跨平台中文 PDF 字体与合规

## 1. 缺陷与修复

Windows 开发机和冻结制品能使用微软雅黑生成中文 PDF，但标准 Ubuntu Runner 没有任何候选 CJK 系统字体，导致 PDF 导出真实失败。只在 CI 执行 `apt install` 会掩盖应用的跨平台离线缺陷，因此项目改为随 Sidecar 捆绑受审计的 Noto Sans SC Variable 字体，并把系统字体保留为后备。

## 2. 固定资产

| 项目 | 值 |
| --- | --- |
| 上游 | `notofonts/noto-cjk` |
| 发布 | `Sans2.004` |
| 提交 | `523d033d6cb47f4a80c58a35753646f5c3608a78` |
| 文件 | `Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf` |
| 字节数 | 17,773,132 |
| SHA-256 | `D68BAFCB48A2707749396AA12BBBD833CB70401F3A9A689FD2902C7E0D295964` |
| 许可证 | SIL Open Font License 1.1 |

上游来源：[Noto CJK](https://github.com/notofonts/noto-cjk)、[Sans LICENSE](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)。

## 3. 打包与运行边界

- 源码态从 `sidecar/stt_desktop/assets/fonts/NotoSansSC-VF.ttf` 加载；
- PyInstaller 使用显式 `--add-data` 把整个字体目录写入 onefile 制品；
- OFL 完整文本同时嵌入 Sidecar，并作为 Tauri `legal/Noto-Sans-SC-OFL-1.1.txt` 安装；
- `THIRD_PARTY_NOTICES.md` 记录版权、许可与来源；
- 依赖清单生成器核对字体的固定大小和 SHA-256，并把它作为 `asset`/CycloneDX `file` 组件；
- 若内置字体损坏，运行时才尝试微软雅黑、黑体、系统 Noto 或苹方；全部不可用时明确失败，不生成缺字的伪成功 PDF。

## 4. 验收

固定变量 TTF 已由 ReportLab 5 实际注册并生成包含“时奕教务排课：一年级数学”的 PDF。Windows Python 88 项、Ubuntu Python 88 项、重新冻结 Sidecar 的五种导出全流程、wheel 三项字体资源和 PyInstaller CArchive 三项字体资源均已通过。`v0.1.5-test.6` 的依赖清单与 CycloneDX SBOM 共记录 656 个包/资产且许可证缺失为 0；干净 Windows NSIS/MSI 安装验证也确认安装包和内层程序可用。本模块已完成，macOS/Linux 原生桌面安装包仍属于后续平台适配范围。
