# Pig Memes

The public image repository for [PigMemeHub](https://meme.xn--y7x.org/).
Submit images through the website or open a pull request using the format below.
Website submissions are opened by `pigmemehub[bot]` with verified uploader attribution.
New submissions require the `memehub/validate` status and an up-to-date branch before merging.

The repository automation and documentation come from
[memehub at cf34b7045e14](https://github.com/czxieddan/memehub/tree/cf34b7045e14a742a9f9d8b4e6c19ed60f11958e/repository-template).
Their AHCL 1.2 notice is in [LICENSE](LICENSE), with source and history in [.ahcl/AHCL-SOURCE.md](.ahcl/AHCL-SOURCE.md).
These software notices do not grant new rights over submitted images; contributors must have the right to share them.

## Repository guide

Copy this directory, including `.github/`, into a separate public image repository. Keep the trusted scripts and workflows on its default branch. Automation uses Python 3.11 standard-library modules, with no Rust, pip packages, or personal access token required.

## Submission format

```text
data/121408646/BigPig/meme.png
data/121408646/BigPig/meme.toml
```

`121408646` is the GitHub numeric user ID. `BigPig` is a case-sensitive Name containing 1–64 ASCII letters, digits, underscores, or hyphens. Filenames cannot contain directory separators. Each ID/Name directory contains exactly one image and a UTF-8 `meme.toml`:

```toml
file = "meme.png"
display_name = "Big Pig"
```

Images may be PNG, JPEG (`.jpg` or `.jpeg`), WebP, or GIF, up to 5 MiB each. Scripts check extensions and signatures without decoding or changing image bytes. Images should first pass the website's image decoding and resource checks. Display names support Unicode. Changing the Name or display name does not change the image hash.

For direct submissions, the directory ID must match the PR author's numeric ID. Updates and deletions also require ownership. Website submissions use a GitHub App to open a branch and PR in this repository, with this marker in the PR body:

```html
<!-- memehub-uploader:121408646 -->
```

The marker is accepted only when the author has `type=Bot` and a login exactly matching `MEMEHUB_BOT_LOGIN`. It must be unique and complete. Other authors cannot use it to change ownership; `Co-authored-by` provides credit but does not authorize submissions for another user.

## Validation and publication

PR opened, reopened, and synchronize events run trusted scripts. They use the fixed `https://api.github.com` endpoint to read immutable commit snapshots, comparing the latest default branch with the PR's final image set. Raw-image lowercase SHA-256 hashes must be unique across the repository, including different Names belonging to one user. Replacing an entry excludes that entry's previous version from collision checks.

A duplicate causes a comment naming the PR head, duplicate and existing paths, and complete hash, then closes the entire PR. Scripts reread the head before commenting and before closing. GitHub's close API has no atomic head condition, leaving a short race between the final read and close request.

After validation, the bot commits individual manifests only to the PR source branch, removing manifests made obsolete by replacements or deletions:

```text
manifest/<64-character-image-sha256>/manifest.toml
```

```toml
schema_version = 1
hash = "<64-character-lowercase-sha256>"
uploader_id = 121408646
name = "BigPig"
display_name = "Big Pig"
path = "/data/121408646/BigPig/meme.png"
```

The placeholder hash illustrates the format; scripts generate the real value. PR validation does not write `manifest/index.toml`. Contributors cannot edit generated manifests, indexes, workflows, scripts, or unrelated paths. The bot writes `memehub/generated` commit-status receipts in the target repository. Reruns verify the latest commit changing generated files and the receipt's Bot identity before accepting earlier output. Receipts created in a fork do not count. Preserve generated commits rather than recreating or squashing them before updating a submission.

After a PR merges into the default branch, publication fetches its latest commit and validates all images, metadata, and existing manifests. It writes only `manifest/index.toml`:

```toml
schema_version = 1
source_commit = "<40-character-commit-before-index-generation>"
hashes = ["<sorted-unique-64-character-image-sha256>"]
```

An empty repository uses `hashes = []`. Readers fetch manifests and images at `source_commit`. Failed publication preserves the previous index. Identical publication produces no commit. Non-forced ref updates protect concurrent changes; a changed default branch triggers up to three fresh attempts.

## GitHub App and permissions

Use a publishing GitHub App installed on the image repository. Grant Contents, Pull requests, and Commit statuses read/write, plus Metadata read. It does not need Actions write access.

| Type | Name | Value |
| --- | --- | --- |
| Repository variable | `MEMEHUB_APP_ID` | Publishing App numeric ID |
| Actions secret | `MEMEHUB_APP_PRIVATE_KEY` | Private key with original line breaks |
| Repository variable | `MEMEHUB_BOT_LOGIN` | Exact website App login, such as `memehub-web[bot]`; empty disables uploader markers |
| Repository variable | `MEMEHUB_ALLOW_MAINTAINER_IMPORT` | Defaults to `false`; only literal `true` enables maintainer imports |

The publishing identity comes from the token action's `app-slug`. Website and publishing Apps may differ. With maintainer imports enabled, REST permission checks require `admin` or `maintain` access before permitting changes under another user's ID. Organization membership or write access is insufficient. Imports still follow content, collision, and generated-file rules.

Without App credentials, same-repository submissions can use the workflow's `GITHUB_TOKEN` permissions: `contents: write`, `pull-requests: write`, and `statuses: write`. Repository Actions settings must permit those writes. Because GITHUB_TOKEN commits usually do not trigger workflows, scripts explicitly set `memehub/validate` on the generated head SHA. The App path sets this status too.

Fork submissions require the same publishing App installed on the head fork, with Contents and Commit statuses write access. The workflow obtains a separate installation token for that fork and writes only to its source branch. A target-repository GITHUB_TOKEN cannot write across repositories. Missing access fails with the actual fork name; manifests are never redirected to the default branch. Install the App and rerun, or push another submission commit. Website submissions use same-repository branches and avoid this installation step.

Default-branch push revalidation does not require a fork write token. If it finds pending generated changes, it fails; the PR's synchronize task must generate those changes with its fork token.

`actions/checkout`, `actions/setup-python`, and `actions/create-github-app-token` use full official commit pins. The publishing token action is pinned to `fee1f7d63c2ff003460e3d139729b119787bc349` (v2). Verify upstream releases and changes before updating pins.

## Branch protection and concurrency

Configure the default branch to prevent concurrent PRs from merging duplicate images:

1. Require the `memehub/validate` commit status, preferably restricted to the publishing App. Use the status context rather than a workflow job's display name.
2. Enable **Require branches to be up to date before merging**. This template does not handle `merge_group`; enabling a merge queue does not replace that requirement.
3. Restrict direct pushes, force pushes, and bypasses. Only the publishing App should receive the controlled default-branch access needed to commit the index.
4. Review script and workflow changes through a separate maintainer process. Ordinary image PRs cannot change them.

Default-branch pushes first mark open PRs pending, then revalidate against the latest default branch. A newly duplicated PR is commented on and closed. When GITHUB_TOKEN suppresses follow-up events, the up-to-date rule still prevents an old PR from merging; updating its branch triggers synchronize.

Tasks for one PR run serially without cancelling active writes. Push revalidation has its own serial queue. Index publication is serialized per default branch with `cancel-in-progress: false`; ref updates still check current state and use `force: false`. Pushes changing only `manifest/index.toml` are excluded from revalidation to avoid a publication loop.

## Security and resource limits

Privileged workflows use `pull_request_target` and check out the trusted base commit from the event; push revalidation uses the default-branch event SHA. Checkout sets `persist-credentials: false`. Workflows do not check out PR heads, run PR scripts or artifacts, execute images, or interpolate PR text into shell commands. PR files are read into memory as data. API endpoints cannot be overridden through environment variables; redirects are disabled, and tokens or raw upstream errors are not printed.

Each run permits up to 10000 Git tree nodes, 500 entries, 128 MiB of downloaded blobs, 256 MiB of HTTP responses, and 2048 REST requests. Each response is limited to 8 MiB, each request to 20 seconds, and the request budget to 540 seconds; jobs have a 15-minute limit. Images are limited to 5 MiB, metadata and manifests to 32 KiB, and indexes to 64 KiB. Push revalidation handles up to 20 open PRs; reduce the queue before rerunning when that limit is reached. Truncated trees, symlinks, executable files, submodules, path traversal, and invalid file counts fail validation.

Review these budgets and GitHub rate limits before expanding the repository. Keep publishing keys out of frontend assets and submission branches, and prevent contributors from controlling other privileged workflows in the target repository.

## Workflow commands

Trusted workflows invoke the installed scripts with configured credentials and event files:

```sh
PYTHONPATH=scripts python -m memehub.cli validate
PYTHONPATH=scripts python -m memehub.cli revalidate
PYTHONPATH=scripts python -m memehub.cli publish
```

These commands call GitHub and write branches or statuses. Publication accepts only a merged PR event. Merge the template before opening the first image PR; its merge creates the first index. Until then, the application treats the repository as unpublished.
