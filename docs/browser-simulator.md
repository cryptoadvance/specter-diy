# Browser simulator previews

Pull requests targeting this repository's default branch run the browser build
through the reusable workflow in
[specter-diy-web-simulator](https://github.com/cryptoadvance/specter-diy-web-simulator).
The small local caller in `.github/workflows/browser-simulator.yml` pins that
workflow to commit
`95bfa2ec09badfe29b8e5a30a0f674c996b19af0`. A maintainer updates the pin only
after reviewing a new Web Simulator commit, then changes the full SHA in both
browser workflow files and runs the publisher/workflow contract checks.

## Trust boundary

The reusable build runs in the calling Specter repository's Actions context
with `contents: read`; it receives no secrets and cannot publish Pages or
write comments. It builds the exact PR head and uploads a versioned artifact
with source, simulator, run-attempt, and SHA-256 provenance.

`.github/workflows/publish-browser.yml` runs after the local browser workflow
completes. It checks out publisher code from the protected default branch,
validates the artifact as hostile data, safely extracts it, rechecks the live
PR head and pin, then updates that repository's `gh-pages` branch and Pages
deployment. It executes no code from the PR or Web Simulator checkout. The
Web Simulator checkout supplies only static page files to copy after recursive
symlink checks. The publisher updates one bot comment for the current PR
commit. Failed current builds remove the earlier preview; old runs cannot
replace or remove a preview with a larger run ID. A read-only caller signal
lets the trusted publisher remove previews when a PR closes.

## Fork behavior

- A PR to `cryptoadvance/specter-diy` is built and published by the official
  repository, including PRs whose source branch belongs to a contributor fork.
- A PR within an independent `alice/specter-diy` fork is built and published
  by Alice's repository with its own Pages site and `gh-pages` branch.
- Only `specter-diy` must be forked. No Web Simulator fork or central build
  service is involved.

Before the first preview in an independent fork, its owner must enable GitHub
Pages once under **Settings → Pages → Build and deployment → Source: GitHub
Actions**. GitHub requires a publishing source to be configured for Pages
deployments ([documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)).
The publisher uses only that repository's `GITHUB_TOKEN`; GitHub's
`configure-pages` action requires a separate administrative token to enable an
unconfigured site, so the trusted workflow does not try to bootstrap this
setting. Once enabled, PR previews deploy automatically to the fork's own
Pages site.

Preview URLs follow the repository that owns the PR:

```text
https://<owner>.github.io/specter-diy/pr/<PR_NUMBER>/
```

For the official repository, this is
`https://cryptoadvance.github.io/specter-diy/pr/<PR_NUMBER>/`.

## Migration from the PR #431 exploration

| Responsibility or file | Decision | New home |
| --- | --- | --- |
| `.github/simulator/publish_preview.py` | Keep and refactor; local trusted publisher | `specter-diy/.github/simulator/publish_preview.py` |
| `.github/simulator/resolve_build_target.py` | Move; derive source from caller event | `specter-diy-web-simulator/web/tools/resolve_build_target.py` |
| `.github/simulator/source_info.py` and build verification | Move/replace with browser build provenance | `specter-diy-web-simulator/web/browser/` and `web/tools/package_preview.py` |
| Dynamic publisher target resolution and simulator-main lookup | Delete; immutable Web Simulator SHA is configured locally | `.github/workflows/browser-simulator.yml` and `publish-browser.yml` |
| Publisher security tests | Replace with archive, provenance, stale-run, close, and comment tests | `specter-diy/.github/simulator/test_publish_preview.py` |
| Build-target and browser tests | Move to Web Simulator | `specter-diy-web-simulator/web/tests/` |
| Browser jobs in `.github/workflows/build.yml` | Move out; the current default branch already keeps this workflow firmware-focused | `specter-diy-web-simulator/.github/workflows/build-preview.yml` |
| `.github/workflows/publish-browser.yml` | Keep and refactor as the privileged `workflow_run` publisher | `specter-diy/.github/workflows/publish-browser.yml` |
| `.github/workflows/test.yml` | Keep normal tests; add read-only publisher contract tests | `specter-diy/.github/workflows/test.yml` |
| Browser build guide | Move the manual build path to the canonical Web Simulator docs | `specter-diy-web-simulator/docs/browser-simulator.md` |
| Manual build dispatch and dynamic-source helper code | Delete; PR events and the reusable workflow cover the supported path | Removed from both repositories |

The Web Simulator's complete manual build, test, serve, and Virtual Host
instructions are in its [Getting Started guide](https://github.com/cryptoadvance/specter-diy-web-simulator/blob/95bfa2ec09badfe29b8e5a30a0f674c996b19af0/docs/browser-simulator.md).
