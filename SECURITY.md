# Security Policy

## Supported versions

Only the latest published stable version and the latest explicitly identified public test version receive security fixes. Source builds from arbitrary commits and third-party forks are not official signed releases.

## Reporting a vulnerability

Use GitHub Private vulnerability reporting or open a private draft Security Advisory for this repository. Do not disclose exploitable details in a public issue. Include the affected version/commit, platform, reproduction steps, impact, and whether credentials or school data may have been exposed.

Never submit real passwords, JWTs, enterprise keys, payment secrets, private keys, production database dumps, or identifiable school data. Replace them with deterministic test fixtures.

The maintainers will acknowledge a valid private report, assess severity, coordinate a fix and release, and credit the reporter when requested and safe. No guaranteed response SLA is asserted until a staffed security contact is published.

## Security boundaries

- Academic-affairs data and scheduling run locally.
- Remote services are limited to identity, licensing, payment, device-risk records, and signed updates.
- The WebView never receives Supabase sessions, device private keys, sidecar bearer tokens, or license signing keys.
- The sidecar binds only to a random loopback port and requires a one-time high-entropy session token.
- Official Windows artifacts require Authenticode and a separate Tauri updater Ed25519 signature.

See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) for release authorization and [PRIVACY.md](PRIVACY.md) for the data boundary.
