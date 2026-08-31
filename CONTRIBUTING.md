# Contributing to Karios STT Desktop

Thank you for contributing to Karios STT Desktop（时奕教务排课）. By participating, you agree to follow `CODE_OF_CONDUCT.md` and to submit only code and assets that may be distributed under the project's licenses.

## Before opening a pull request

1. Open or reference an issue for behavior changes unless the change is a small, self-contained correction.
2. Branch from the current default branch and keep the change focused.
3. Do not commit credentials, private keys, real school data, proprietary code or generated signing artifacts.
4. Update tests and user-facing documentation when behavior changes.
5. Confirm that newly bundled dependencies and assets are redistributable under an OSI-compatible or otherwise documented compatible license.

## Required checks

Run the relevant checks before requesting review:

```powershell
uv sync --frozen --extra dev
uv run ruff check sidecar tests benchmarks
uv run pytest

cd apps/desktop
npm ci
npm run build

cd src-tauri
cargo fmt --check
cargo check --locked
cargo test --locked
```

Windows installer, frozen sidecar, import/export, backup and large scheduling changes may require the additional scripts documented under `docs/desktop`.

## Data, secrets and product boundaries

Do not commit or attach identifiable school data, production database exports, passwords, JWTs, enterprise keys, payment/SMTP secrets, service-role keys, PFX files, updater private keys or DPAPI credential exports. Use deterministic synthetic fixtures. Any new outbound field or service requires updates to the privacy boundary, mock registry and network tests.

- Academic-affairs data and scheduling remain local.
- AI assistant, personal center, institution management and platform review are out of scope.
- User-visible timetable candidates must have zero hard-constraint violations.
- File imports, project archives, backups and sidecar routes require path and integrity validation.
- Material modules include tests, implementation notes under `docs/desktop` and an isolated commit.

## Review and merge

- External pull requests require review by a listed project reviewer.
- CI must pass before merge. Review conversations must be resolved.
- Changes to build workflows, dependencies, artifact configuration, release scripts or code-signing scope receive additional security scrutiny.
- Force pushes to the default branch and replacement of published release artifacts are prohibited.

Submitting a pull request does not authorize a SignPath signing request. Signing is separately controlled by `CODE_SIGNING_POLICY.md` and requires origin verification plus manual approval.

## Security reports

Do not report exploitable vulnerabilities in a public issue. Follow `SECURITY.md` and use GitHub private vulnerability reporting or a private Security Advisory.
