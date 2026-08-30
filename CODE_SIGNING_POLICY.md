# Code Signing Policy

## Scope

This policy covers official Windows executables, sidecars, NSIS/MSI installers, updater artifacts, and release metadata for `tech.karios.stt.desktop`. Test self-signing and SignPath Foundation signing are distinct channels.

## Authorized source

Official artifacts must be built from a public commit or protected release tag in this repository with lock files present. CI records the exact commit, toolchain, tests, dependency inventory, artifact hashes, and unsigned outputs. Build inputs may not be replaced after review.

The signing scope is limited to code and redistributable dependencies required by this open-source project. Private products, unrelated binaries, downloaded post-build payloads, macros, drivers, scripts from external repositories, or artifacts built from an unreviewed working tree are excluded.

## Roles and approval

- Authors prepare changes and evidence.
- Reviewers evaluate code, tests, dependency changes, and signing scope.
- Approvers verify the release tag/commit, CI result, artifact identity, version, hashes, and release notes before authorizing production signing.

Production approval should be performed by a person independent from the release author whenever staffing permits. Maintainers and signing approvers must use MFA. SignPath project roles and GitHub permissions follow least privilege.

## Test channel

Before SignPath approval, a dedicated self-signed Code Signing certificate may sign public test artifacts. The private key remains non-exportable in an isolated Windows user certificate store. Releases prominently state that the certificate is not publicly trusted. Testers manually verify and trust the public CER only in disposable or dedicated test environments.

## Production channel

The production sequence is:

1. protected tag triggers a GitHub-hosted Windows build;
2. tests, license inventory, SBOM/inventory, and unsigned artifact hashes complete;
3. unsigned artifacts are submitted to SignPath with origin verification;
4. an authorized approver reviews and approves the request;
5. SignPath returns Authenticode-signed artifacts;
6. CI verifies Publisher, timestamp, file identity, and expected signing policy;
7. Tauri updater signatures are generated over the final Authenticode bytes;
8. immutable artifacts, checksums, manifest, provenance, and notes are published.

The expected production Windows Publisher is `SignPath Foundation`. The company name remains copyright and trademark attribution, not the certificate publisher.

## Updater key

The updater Ed25519 private key is separate from Authenticode and never enters the repository. The public key is compiled into the application. Loss or suspected disclosure requires stopping the update channel and executing a documented key-transition release; existing artifacts are never silently replaced.

## Incident handling

On suspected key, role, runner, dependency, or origin compromise: pause signing and publishing, preserve logs, revoke or rotate affected credentials where possible, notify users through authenticated channels, and publish a new version rather than overwriting an existing release. Test CER trust removal instructions are included when a test certificate is replaced.
