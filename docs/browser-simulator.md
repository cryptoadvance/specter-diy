# Browser simulator PR previews

Browser previews are built and hosted by the paired
[`specter-diy-web-simulator`](https://github.com/cryptoadvance/specter-diy-web-simulator)
repository. The preview URL is
`https://<owner>.github.io/specter-diy-web-simulator/pr/<number>/<full-head-sha>/`.

Specter DIY's trusted PR workflow validates the live PR, dispatches its exact
metadata to the paired Web Simulator, and exits. It does not build PR-controlled
code, poll for the remote result, or publish Pages. The Web Simulator validates
the request again, builds and tests the exact PR head SHA, publishes a
commit-specific preview, and (for `cryptoadvance/specter-diy` PRs) the
trusted Web Simulator finalizer posts the preview comment using a short-lived
GitHub App installation token. It posts the refreshed comment before deleting
older App-owned marked comments, preserving the previous comment if posting
fails. When a new commit preview succeeds, it removes the older browser pages
for that PR; failed builds keep the last successful preview online.

The existing Specter DIY firmware build and its GitHub Actions artifacts are
not changed by this PR. All preview-specific firmware artifacts are created
and managed independently by the Web Simulator. After successfully publishing
and reporting a newer preview, the Web Simulator removes its own superseded
firmware artifacts; a failed build preserves the last successful preview and
firmware. Closing a PR triggers cleanup of the Web Simulator's own firmware
artifacts and browser previews. If GitHub Pages approaches its size budget,
the Web Simulator can remove previews from the least recently updated PRs
while preserving the currently published PR and its firmware artifact.

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

For the production `cryptoadvance` pair, the administrator must restrict the
reporter GitHub App installation to `cryptoadvance/specter-diy`, with
`Pull requests: Read and write`, and configure
`SPECTER_PREVIEW_APP_ID` (Web Simulator Actions variable) and
`SPECTER_PREVIEW_APP_PRIVATE_KEY` (Web Simulator Actions secret).
This permission also permits changes to PR metadata, not just preview comments.
The Web Simulator's `main` branch therefore becomes a trusted deployment
boundary and must require maintainer review and passing CI, with direct and
force pushes restricted. Forks run the preview build without that upstream App
credential and do not get an automatic App-authored PR comment.

Previews are experimental and execute PR-controlled code in the browser.
Never enter a real seed phrase or use real funds.
