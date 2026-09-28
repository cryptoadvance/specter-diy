# Browser simulator

The browser simulator tooling is maintained in
[`cryptoadvance/specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator).
This firmware repository pins both reusable workflow definitions and simulator
tooling to the same full commit SHA in `.github/workflows/build.yml` and
`.github/workflows/publish-browser.yml`. Updating simulator tooling requires
reviewing a full SHA and changing those trusted workflow pins together; builds
never resolve a moving `main` branch. Each build records the exact firmware
source and simulator-tooling commits in its provenance metadata. The trusted
publisher rejects successful build artifacts whose simulator repository or
commit differs from its own fixed configuration, so a PR can choose Specter
source but cannot choose the tooling version accepted for publication.

The trusted `Publish browser simulator` workflow publishes the stable build
and PR previews through this repository's GitHub Pages site:

- Stable: <https://cryptoadvance.github.io/specter-diy/>
- PR preview: `https://cryptoadvance.github.io/specter-diy/pr/<number>/`

For default-branch pushes, the trusted publisher also compares the completed
run's SHA with the current default-branch SHA immediately before invoking the
reusable publisher. Older or non-default-branch runs are skipped to prevent a
slow build from replacing a newer stable page.

To test the browser simulator with Specter Desktop, use the local
[`specter-virtual-host`](https://github.com/cryptoadvance/specter-virtual-host)
bridge. Its default site is the stable browser build; its local USB endpoint
exposes the simulator protocol, not physical USB access to Specter DIY.

The browser build is experimental and is not an official firmware release.
Never enter a real seed phrase or use real funds. It does not simulate physical
hardware security, STM32 timing, or an air gap.
