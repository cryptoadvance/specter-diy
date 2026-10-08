# Browser simulator PR previews

Browser previews are built and hosted by the paired
[`specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator)
repository. The preview URL is
`https://<owner>.github.io/specter-diy-web-simulator/pr/<number>/`.

Specter DIY's trusted PR workflow only dispatches PR metadata, polls the
Web Simulator's public status record, and updates one PR comment. It does not
build browser code or publish Pages. The remote build uses the exact PR head
SHA; a close event removes its preview. Regular firmware CI in this repository
remains independent.

Forks that want previews must fork **both** repositories under the same owner.
Enable Actions in both, enable GitHub Pages with the GitHub Actions source in
the Web Simulator fork, and add a fine-grained token to the Specter DIY fork as
the `WEB_SIMULATOR_DISPATCH_TOKEN` secret. Give that token access only to the
paired Web Simulator repository and **Actions: Read and write** permission. It
does not need write access to Specter DIY. An optional
`WEB_SIMULATOR_REPOSITORY` Actions variable overrides the default paired-owner
name. See the Web Simulator's
[setup and security guide](https://github.com/cryptoadvance/specter-diy-web-simulator/blob/main/docs/browser-simulator.md)
for the complete fork steps and trust boundary.

Previews are experimental and execute PR-controlled code in the browser.
Never enter a real seed phrase or use real funds.
