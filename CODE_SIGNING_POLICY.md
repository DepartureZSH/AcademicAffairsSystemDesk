# Code Signing Policy

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

Until the SignPath Foundation application is approved, public test releases use a clearly identified self-signed test certificate. They are not represented as SignPath Foundation-signed releases.

## Scope

This policy covers official Windows executables, sidecars, NSIS/MSI installers, updater artifacts, and release metadata for `tech.karios.stt.desktop`. Test self-signing and SignPath Foundation signing are distinct channels.

## Authorized source

Official artifacts must be built by GitHub Actions from the protected `main` branch or a protected release tag in this repository with lock files present. CI records the exact commit, toolchain, tests, dependency inventory, artifact hashes, and unsigned outputs. Build inputs may not be replaced after review. SignPath origin verification must bind every production signing request to that public build and source revision.

The signing scope is limited to code and redistributable dependencies required by this open-source project. Private products, unrelated binaries, downloaded post-build payloads, macros, drivers, scripts from external repositories, or artifacts built from an unreviewed working tree are excluded.

## Roles and approval

- **Author/committer:** [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) prepares maintained changes and release evidence.
- **Reviewer:** [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) reviews external contributions, tests, dependency changes and signing scope. Additional trusted reviewers will be listed here when appointed.
- **Signing approver:** [Shuhai Zhang (`@DepartureZSH`)](https://github.com/DepartureZSH) verifies the protected release tag/commit, CI result, artifact identity, version, hashes and release notes before manually authorizing a production signing request. Additional approvers will be listed here when appointed.

The project currently has one maintainer, so these roles are held by the same person. External contributions may not be merged without maintainer review. Production approval should be performed by a person independent from the release author whenever staffing permits. Maintainers and signing approvers must use MFA. SignPath project roles and GitHub permissions follow least privilege. See [GOVERNANCE.md](GOVERNANCE.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Test channel

Before SignPath approval, a dedicated self-signed Code Signing certificate may sign public test artifacts. The private key remains non-exportable in an isolated Windows user certificate store. Releases prominently state that the certificate is not publicly trusted. Testers manually verify and trust the public CER only in disposable or dedicated test environments.

## Production channel

The production sequence is:

1. protected tag triggers a GitHub-hosted Windows build;
2. tests, license inventory, SBOM/inventory and unsigned artifact hashes complete;
3. the desktop executable and Python sidecar are submitted as a constrained multi-file artifact with origin verification;
4. an authorized approver reviews the request and SignPath returns the signed inner executables;
5. CI verifies those signatures and packages the signed executables into NSIS and MSI installers;
6. each outer installer is submitted under its dedicated artifact configuration with origin verification and manual approval;
7. CI verifies Publisher, timestamp, file identity, version metadata and expected signing policy on the returned installers and installed executables;
8. Tauri updater signatures are generated over the final Authenticode bytes;
9. immutable artifacts, checksums, manifest, provenance and notes are published.

The expected production Windows Publisher is `SignPath Foundation`. The company name remains copyright and trademark attribution, not the certificate publisher.

## Artifact and metadata restrictions

Production signing policies are limited to the documented desktop executable, Python sidecar, NSIS installer and MSI installer. Artifact configurations must restrict expected file names and PE/MSI metadata, require a consistent release version, and reject unrelated executables, drivers, scripts or packages. A request may only contain binaries produced by this repository's trusted build; upstream binaries must not be signed as project-owned code.

## Updater key

The updater Ed25519 private key is separate from Authenticode and never enters the repository. The public key is compiled into the application. Loss or suspected disclosure requires stopping the update channel and executing a documented key-transition release; existing artifacts are never silently replaced.

## Incident handling

On suspected key, role, runner, dependency, or origin compromise: pause signing and publishing, preserve logs, revoke or rotate affected credentials where possible, notify users through authenticated channels, and publish a new version rather than overwriting an existing release. Test CER trust removal instructions are included when a test certificate is replaced.

Security reports follow [SECURITY.md](SECURITY.md). The application's local and remote data boundaries are documented in [PRIVACY.md](PRIVACY.md).
