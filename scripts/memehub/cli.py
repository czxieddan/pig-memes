"""Workflow entry points. Credentials and event paths arrive through environment."""

import argparse
import json
import os
from pathlib import Path
import sys

from .github import GitHub
from .protocol import Invalid
from .publish import publish
from .pull_request import Config, Validator


def event_data():
    path = Path(os.environ["GITHUB_EVENT_PATH"])
    if path.stat().st_size > 1024 * 1024:
        raise Invalid("Workflow event exceeds 1 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def configuration():
    return Config(bot_login=os.environ.get("MEMEHUB_BOT_LOGIN", ""),
                  publisher_login=os.environ.get("MEMEHUB_PUBLISHER_LOGIN", "github-actions[bot]"),
                  allow_maintainer_import=os.environ.get("MEMEHUB_ALLOW_MAINTAINER_IMPORT", "false") == "true")


def clients():
    api = GitHub(os.environ.get("MEMEHUB_TOKEN", ""))
    token = os.environ.get("MEMEHUB_HEAD_TOKEN", "")
    head = GitHub(token, api.budget) if token else None
    return api, head


def revalidate(api, repository, config):
    validator = Validator(api, repository, config)
    branch = api.repo(repository)["default_branch"]
    pulls = [pull for pull in api.open_pulls(repository) if pull["base"]["ref"] == branch]
    # Invalidate every old success before processing the queue against the new base.
    for pull in pulls:
        api.status(repository, pull["head"]["sha"], "pending", "Default branch updated; revalidation required")
    failed = False
    for pull in pulls:
        try:
            validator.run(pull["number"])
        except Invalid as error:
            print(f"PR #{pull['number']}: {error}", file=sys.stderr)
            failed = True
    if failed:
        raise Invalid("Some open PRs failed validation against the latest default branch; check their comments and statuses")


def execute(mode):
    api, head_api = clients()
    repository = os.environ["GITHUB_REPOSITORY"]
    event = event_data()
    if mode == "publish":
        if event.get("pull_request", {}).get("merged") is not True:
            raise Invalid("The index can only be published for a merged PR event")
        sha = publish(api, repository)
        print(f"Index published or already up to date: {sha}")
    elif mode == "validate":
        pull = event["pull_request"]
        Validator(api, repository, configuration(), head_api).run(pull["number"])
    else:
        revalidate(api, repository, configuration())


def main():
    parser = argparse.ArgumentParser(description="memehub image repository automation")
    parser.add_argument("mode", choices=("validate", "revalidate", "publish"))
    args = parser.parse_args()
    try:
        execute(args.mode)
    except (Invalid, KeyError, OSError, ValueError) as error:
        if isinstance(error, Invalid):
            print(str(error), file=sys.stderr)
        else:
            print("Invalid configuration or event data; raw responses and environment variables are omitted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
