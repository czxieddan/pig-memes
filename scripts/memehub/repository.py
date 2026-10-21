"""Immutable Git trees and a three-way overlay against the current default branch."""

from dataclasses import dataclass

from .protocol import (Invalid, MAX_IMAGE, MAX_INDEX, MAX_METADATA, MAX_TREE, SHA,
                       read_entries, safe_path, unique_entries, validate_manifests)


@dataclass(frozen=True)
class Blob:
    repository: str
    sha: str
    size: int
    mode: str = "100644"


def managed(path):
    return path.split("/", 1)[0] in ("data", "manifest")


def check_tree_row(row):
    path = row["path"]
    safe_path(path)
    if row["type"] == "tree" and row["mode"] == "040000":
        return False
    if path in {"data", "manifest"}:
        raise Invalid(f"data and manifest must be directories: {path}")
    if row["type"] != "blob" or row["mode"] != "100644":
        raise Invalid(f"Only regular non-executable files and directories are allowed; symlinks and submodules are rejected: {path}")
    if not SHA.fullmatch(row["sha"]):
        raise Invalid(f"Invalid Git blob SHA: {path}")
    return True


def check_blob_size(path, size):
    if type(size) is not int or size < 0:
        raise Invalid(f"Invalid Git blob size: {path}")
    if not managed(path):
        return
    limit = MAX_METADATA if path.endswith(".toml") else MAX_IMAGE
    if path == "manifest/index.toml":
        limit = MAX_INDEX
    if size > limit:
        raise Invalid(f"File exceeds the size limit: {path}")


def read_tree(api, repository, commit):
    tree = api.tree(repository, commit)
    if tree.get("truncated") is not False:
        raise Invalid("GitHub returned a truncated Git tree; incomplete repositories are rejected")
    rows = tree["tree"]
    if len(rows) > MAX_TREE:
        raise Invalid(f"Git tree exceeds {MAX_TREE} nodes")
    files = {}
    seen = set()
    for row in rows:
        path = row["path"]
        if path in seen:
            raise Invalid(f"Git tree contains a duplicate path: {path}")
        seen.add(path)
        if check_tree_row(row):
            check_blob_size(path, row.get("size"))
            files[path] = Blob(repository, row["sha"], row["size"])
    return Snapshot(api, files)


class Snapshot:
    def __init__(self, api, files):
        self.api = api
        self.files = files

    def read(self, path, limit):
        blob = self.files[path]
        if blob.size > limit:
            raise Invalid(f"File exceeds the size limit: {path}")
        data = self.api.blob(blob.repository, blob.sha, limit)
        if len(data) != blob.size:
            raise Invalid(f"Git blob byte count does not match its tree entry: {path}")
        return data

    def entries(self):
        return read_entries(self.files, self.read)

    def validated(self):
        entries = self.entries()
        unique_entries(entries)
        validate_manifests(self.files, self.read, entries)
        return entries

    def identity(self, path):
        blob = self.files.get(path)
        if blob is None:
            return None
        return blob.sha, blob.mode


def changed_paths(before, after):
    return {path for path in before.files.keys() | after.files.keys()
            if before.identity(path) != after.identity(path)}


def overlay(base, ancestor, head):
    files = dict(base.files)
    for path in changed_paths(ancestor, head):
        if not path.startswith("data/"):
            continue
        ancestor_id = ancestor.identity(path)
        current_id = base.identity(path)
        if current_id not in (ancestor_id, head.identity(path)):
            raise Invalid(f"Conflict with the latest default branch; update the PR branch: {path}")
        if path in head.files:
            files[path] = head.files[path]
        else:
            files.pop(path, None)
    return Snapshot(base.api, files)
