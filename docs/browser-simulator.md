# Browser simulator

The browser simulator tooling is maintained in
[`cryptoadvance/specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator).
This firmware repository calls its reusable GitHub Actions workflows at the
current workflows from the simulator repository's `main` branch. At the start
of each build, the target job resolves `main` to one exact commit SHA and uses
that SHA for all simulator tooling in that run. Each build records the exact
firmware source and simulator-tooling commits, so it automatically follows
latest `main` without losing per-build provenance.

The trusted `Publish browser simulator` workflow publishes the stable build
and PR previews through this repository's GitHub Pages site:

- Stable: <https://cryptoadvance.github.io/specter-diy/>
- PR preview: `https://cryptoadvance.github.io/specter-diy/pr/<number>/`

To test the browser simulator with Specter Desktop, use the local
[`specter-virtual-host`](https://github.com/cryptoadvance/specter-virtual-host)
bridge. Its default site is the stable browser build; its local USB endpoint
exposes the simulator protocol, not physical USB access to Specter DIY.

The browser build is experimental and is not an official firmware release.
Never enter a real seed phrase or use real funds. It does not simulate physical
hardware security, STM32 timing, or an air gap.
