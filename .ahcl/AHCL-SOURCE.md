# Source and history

The repository automation, workflows, and maintained guide are copied from
<https://github.com/czxieddan/memehub/tree/cf34b7045e14a742a9f9d8b4e6c19ed60f11958e/repository-template>.
The upstream complete modification history is <https://github.com/czxieddan/memehub>.
Changes to this deployment copy are recorded in <https://github.com/czxieddan/pig-memes>.

Original paths under `repository-template/` are retained relative to this repository root.
The App IDs and secrets are deployment settings; private keys are stored in GitHub Actions secrets and on the server, never in this tree.
Python 3.11 standard-library modules run the automation. The full workflow action commit pins are recorded in `.github/workflows/`.
The copied covered scope retains AHCL 1.2 and its original 2026-10-20 initial-adoption history.
The scope here is repository automation and its maintained documentation; no Rust application or database dependency is distributed here.
