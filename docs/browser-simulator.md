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
trusted Web Simulator finalizer creates or updates one marked preview comment
using a dedicated, non-collaborator machine-user account (for example
`specter-preview-bot`). It updates its own existing comment **in place** rather
than reposting, preventing duplicate timeline entries and notifications.
The bot account must never have write access to the Specter DIY repository.
When a new commit preview succeeds, the publisher removes the older browser pages
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

For the production `cryptoadvance` pair, configure a dedicated normal
GitHub machine-user account with **no repository write permissions**. Its
`public_repo` Personal Access Token (classic) is stored as the Web Simulator
Actions secret `SPECTER_PREVIEW_BOT_TOKEN`; set
`SPECTER_PREVIEW_BOT_LOGIN` as the Web Simulator Actions variable. A fresh
production PAT should be created separately from the successful fork test PAT.
The token is used **only by the trusted Web Simulator finalizer**, never by
untrusted PR build or verification jobs. The finalizer verifies the GitHub
identity, validates the exact live PR, and edits/deletes only its own marked
preview comments. A regular machine user does not get GitHub's official Bot
badge. Although `public_repo` is not a comment-only scope, the user's lack
of repository write permissions prevents it from changing other people's PR
metadata or comments. It may still perform ordinary public-user actions.

The Web Simulator's `main` branch is a trusted deployment boundary and must
require maintainer review and passing CI, with direct and force pushes
restricted. Paired forks do not receive the production PAT; comment writing
from a paired fork requires a separately configured fork test account and
secret. The Specter DIY dispatcher itself never receives a PR-comment token.

Previews are experimental and execute PR-controlled code in the browser.
Never enter a real seed phrase or use real funds.
