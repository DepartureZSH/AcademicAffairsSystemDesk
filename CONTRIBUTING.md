# Contributing

## Development

Use a feature branch, keep generated binaries and secrets out of Git, and install locked dependencies with `uv sync --frozen --extra dev`, `npm ci`, and Cargo's checked-in lock file. Windows contributors can use `scripts/start-desktop-dev.ps1` and `scripts/build-windows.ps1`.

Before submitting a change, run:

```powershell
uv run ruff check sidecar tests benchmarks
uv run pytest
Set-Location apps\desktop
npm run build
Set-Location src-tauri
cargo fmt --check
cargo check --locked
cargo test --locked
```

## Data and secrets

Do not commit or attach identifiable school data, production database exports, passwords, JWTs, enterprise keys, payment/SMTP secrets, service-role keys, PFX files, updater private keys, or DPAPI credential exports. Use deterministic synthetic fixtures. Any new outbound field or service requires updates to the privacy boundary, mock registry, and network tests.

## Design constraints

- Academic-affairs data and scheduling remain local.
- AI assistant, personal center, institution management, and platform review are out of scope.
- User-visible candidates must have zero hard-constraint violations.
- File imports, project archives, backups, and sidecar routes require path and integrity validation.
- Material modules include tests, implementation notes under `docs/desktop`, and an isolated commit.

Security vulnerabilities follow [SECURITY.md](SECURITY.md), not public issues.
