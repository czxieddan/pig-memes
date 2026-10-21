"""Publish only the index, after checking every existing manifest and image."""

from .github import ApiError
from .protocol import Invalid, MAX_INDEX, SHA, index_bytes, parse_toml
from .repository import read_tree


def content_identity(snapshot):
    return {path: snapshot.identity(path) for path in snapshot.files if path != "manifest/index.toml"}


def previous_index(current):
    path = "manifest/index.toml"
    if path not in current.files:
        return {}
    try:
        return parse_toml(current.read(path, MAX_INDEX), path, MAX_INDEX)
    except Invalid:
        return {}


def valid_index(fields, hashes):
    source = fields.get("source_commit")
    if not isinstance(source, str) or not SHA.fullmatch(source):
        return False
    expected = parse_toml(index_bytes(source, hashes), "manifest/index.toml", MAX_INDEX)
    return type(fields.get("schema_version")) is int and fields == expected


def already_published(api, repository, current, hashes):
    fields = previous_index(current)
    if not valid_index(fields, hashes):
        return False
    published = read_tree(api, repository, fields["source_commit"])
    return content_identity(published) == content_identity(current)


def publish(api, repository):
    branch = api.repo(repository)["default_branch"]
    for _attempt in range(3):
        parent = api.ref(repository, branch)
        current = read_tree(api, repository, parent)
        entries = current.validated()
        hashes = [entry.digest for entry in entries.values()]
        if already_published(api, repository, current, hashes):
            return parent
        content = index_bytes(parent, hashes)
        sha = api.create_commit(repository, parent, {"manifest/index.toml": content},
                                "chore(index): publish image index [memehub-index]")
        if try_advance(api, repository, branch, parent, sha):
            return sha
    raise Invalid("Default branch kept changing during index publication; 3 non-force compare-and-swap retries failed. Rerun publication.")


def try_advance(api, repository, branch, parent, sha):
    if api.ref(repository, branch) != parent:
        return False
    try:
        api.update_ref(repository, branch, sha)
    except ApiError as error:
        if error.status in {409, 422}:
            return False
        raise
    return True
