# Browser simulator

The browser simulator tooling is maintained in
[`cryptoadvance/specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator).
The build resolves simulator `main` once and checks out that exact revision in
every build job. It runs simulator scripts from this checkout and records the exact
firmware source and simulator-tooling commits in provenance metadata. Before
publishing a successful build, the trusted publisher checks that the recorded
simulator commit still equals the current simulator `main` tip. If `main`
advanced while the build ran, publication fails closed and the build must be
rerun.

The `Build` workflow starts directly on `pull_request` with only
`contents: read`. Its firmware and browser jobs check out the exact PR head
repository and SHA, run the firmware tests and browser smoke tests, and upload
their outputs. The target job also checks out the PR head so a resolver added
by that PR is available on its first run; this job has no write permissions or
secrets. PR source, submodules, build scripts, and all artifacts are untrusted.
The default-branch `Publish browser simulator` workflow starts on
`workflow_run(Build)` and receives the write and Pages permissions. It checks
the current PR and both artifact manifests against GitHub's run metadata and
the simulator `main` tip before publishing. Publisher code comes from this
repository's protected default branch. A separate read-only job in that
workflow builds the trusted runtime from the resolved simulator SHA. The
write-enabled job validates it against the browser artifact and copies the
simulator shell as data; it never builds or executes simulator code.

The trusted `Publish browser simulator` workflow publishes the stable build
and PR previews through this repository's GitHub Pages site:

- Stable: <https://cryptoadvance.github.io/specter-diy/>
- PR preview: `https://cryptoadvance.github.io/specter-diy/pr/<number>/`

For default-branch pushes, the trusted publisher compares the completed run's
SHA with the current default-branch SHA before staging the stable page. Older
or non-default-branch runs are skipped, preventing a slow build from replacing
a newer stable page.

To test the browser simulator with Specter Desktop, use the local
[`specter-virtual-host`](https://github.com/cryptoadvance/specter-virtual-host)
bridge. Its default site is the stable browser build; its local USB endpoint
exposes the simulator protocol, not physical USB access to Specter DIY.

The browser build is experimental and is not an official firmware release.
Never enter a real seed phrase or use real funds. It does not simulate physical
hardware security, STM32 timing, or an air gap.
