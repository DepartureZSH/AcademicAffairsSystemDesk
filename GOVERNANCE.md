# Project Governance

## Project ownership

Karios STT Desktop（时奕教务排课）is an open-source project maintained in the public repository at <https://github.com/DepartureZSH/AcademicAffairsSystemDesk>. Apache-2.0 applies to the source code. Official names, trademarks, release channels and signing identity are governed separately as described in `TRADEMARKS.md` and `CODE_SIGNING_POLICY.md`.

## Current roles

The project currently has one maintainer:

| Responsibility | Member |
| --- | --- |
| Author and committer | [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) |
| Reviewer for external contributions | [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) |
| SignPath signing approver | [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) |
| Security coordinator | [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) |

Additional trusted members will be added by a reviewed repository change and assigned least-privilege GitHub and SignPath roles. The same person currently holds multiple responsibilities because the project has a single maintainer; independent review and signing approval will be separated when staffing permits.

## Changes and releases

- External contributions require a pull request and maintainer review.
- The protected default branch requires passing CI; force pushes and deletion are prohibited.
- Official release candidates are built from public source by GitHub Actions.
- Production code signing requires SignPath origin verification and manual approval for every release.
- Published tags and binary assets are immutable. Corrections use a new version.

Technical contribution requirements are documented in `CONTRIBUTING.md`; release authorization is documented in `CODE_SIGNING_POLICY.md`; private vulnerability reporting is documented in `SECURITY.md`.

## Decisions and conflicts

Maintainers decide roadmap, compatibility and release questions using the published product scope and test evidence. Decisions that affect security, privacy, licensing or signed artifact scope must be documented in the repository. Conflicts of interest must be disclosed, and access must be removed promptly when a role is no longer required.
