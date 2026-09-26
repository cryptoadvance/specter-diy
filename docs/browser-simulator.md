# Browser simulator

The browser simulator tooling is maintained in
[`cryptoadvance/specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator).
This firmware repository calls its reusable GitHub Actions workflows at the
immutable simulator commit recorded in `.github/workflows/build.yml`. Each
build records the exact firmware source and simulator-tooling commits.

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
