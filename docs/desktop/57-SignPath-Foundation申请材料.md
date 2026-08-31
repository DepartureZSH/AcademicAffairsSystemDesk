# SignPath Foundation 申请材料

> 本文按 2026-09-01 的 Foundation 申请表整理。申请必须由维护者本人核对并提交；不得虚构声誉、下载量、组织身份或用户数量。

## 1. 建议填写内容

| 表单字段 | 建议值 |
| --- | --- |
| Project Name | `Karios STT Desktop (时奕教务排课)` |
| Repository URL | `https://github.com/DepartureZSH/AcademicAffairsSystemDesk` |
| Homepage URL | `https://github.com/DepartureZSH/AcademicAffairsSystemDesk#readme` |
| Download URL | `https://github.com/DepartureZSH/AcademicAffairsSystemDesk/releases/tag/v0.1.5-test.6` |
| Privacy Policy URL | `https://github.com/DepartureZSH/AcademicAffairsSystemDesk/blob/main/PRIVACY.md` |
| Wikipedia URL | 留空；项目目前没有英文 Wikipedia 页面 |
| Maintainer Type | 若公司实际维护或资助，选 `For-profit company or corporate-backed project`；否则按事实选择 `Individual maintainer(s)` |
| Build System | `GitHub Actions` |
| First Name / Last Name | 必须与申请人 SignPath 账号和真实身份一致，人工填写 |
| Email | 填写长期可访问且已启用 MFA 的维护者邮箱，人工填写 |
| Company Name | 仅在确由公司维护时填写准确的法定中/英文名称，人工核对 |
| Primary Discovery Channel | 按首次发现渠道如实选择；不得为迎合申请而改写 |

### Tagline

```text
A local-first, open-source desktop application for academic timetabling and school scheduling.
```

### Description

```text
Karios STT Desktop is an open-source desktop application for managing academic data, defining scheduling constraints, generating and comparing timetable candidates, making manual adjustments, and exporting school timetables. School data and scheduling algorithms remain on the user's device, while optional remote services are strictly separated from academic business data.
```

### Reputation

`Reputation` 是必填项，但项目当前属于新发布阶段，不能声称已经广泛使用。可如实填写：

```text
Karios STT Desktop is a newly released open-source project, so we do not claim broad adoption or independent media coverage yet. Public trust evidence includes an Apache-2.0 repository, immutable Windows prereleases, reproducible GitHub Actions runs, a published dependency inventory and CycloneDX SBOM, automated clean-install and upgrade/downgrade verification, and documented privacy, security and code-signing policies. Release and verification evidence is available at https://github.com/DepartureZSH/AcademicAffairsSystemDesk/releases/tag/v0.1.5-test.6 and https://github.com/DepartureZSH/AcademicAffairsSystemDesk/blob/main/docs/desktop/56-v0.1.5-test.6发布与验收证据.md. We understand that the project is early-stage and that SignPath Foundation may require additional independent reputation evidence before acceptance.
```

这段内容是技术可信度证据，不等同于社区声誉。若申请前获得真实用户反馈、外部文章、学校试用记录、GitHub stars/forks 或可区分的下载统计，应补充对应公开链接；不得把维护者自己的远端回下载量写成用户采用量。

## 2. Foundation 公开声明

README、下载页和签名政策必须包含：

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

在获批前还必须同时声明当前测试版仍为自签名，避免让用户误以为已经得到 Foundation 签名。

## 3. 申请前检查

- 默认分支包含实际可构建源码、锁文件、CI 和发布脚本；
- 仓库公开并使用 Apache-2.0，不包含私有或商业双许可证代码；
- README 能解释功能、数据边界、下载方式及生产服务尚未完成的限制；
- `CODE_SIGNING_POLICY.md`、`PRIVACY.md`、`SECURITY.md`、`GOVERNANCE.md` 和 `CONTRIBUTING.md` 可从 README 直接访问；
- 维护者的 GitHub 与 SignPath 账号启用 MFA；
- `main` 禁止强推和删除，必要检查通过后才能合并；
- SignPath Artifact Configuration 限制文件名、版本和 PE/MSI 元数据；
- GitHub Actions Trusted Build System 与 Origin Verification 已配置；
- 每次生产签名都有人工审批；
- 公开 Release 页面包含 Foundation 声明、签名政策与隐私政策链接；
- 申请人已如实确认 `Reputation`，理解新项目可能因缺少独立声誉而暂缓批准。

## 4. 证书边界

Foundation 证书签发给 `SignPath Foundation`，Windows Publisher 也显示该名称，不会显示维护公司名称。若需要公司名称作为 Publisher，应单独购买商业 CA 的组织验证代码签名证书，不能把 Foundation 申请描述为公司 OV 证书。
