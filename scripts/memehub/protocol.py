"""Image, metadata and published TOML protocol. Paths are Git paths."""

from dataclasses import dataclass
import hashlib
import json
import re
import tomllib

MAX_IMAGE = 5 * 1024 * 1024
MAX_METADATA = 32 * 1024
MAX_INDEX = 64 * 1024
MAX_ENTRIES = 500
MAX_TREE = 10000
MAX_DATA = 128 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
USER = re.compile(r"[1-9][0-9]{0,19}\Z")
EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MANIFEST_FIELDS = {"schema_version", "hash", "uploader_id", "name", "display_name", "path"}
UNSAFE = re.compile(r"[\\\x00-\x1f\x7f]")


class Invalid(ValueError):
    """A bounded, contributor-visible validation error."""


class Duplicate(Invalid):
    def __init__(self, digest, existing, proposed):
        self.digest = digest
        self.existing = existing
        self.proposed = proposed
        super().__init__(f"Duplicate image: /{proposed} and existing /{existing} have the same raw-byte "
                         f"SHA-256: {digest}. Duplicates are forbidden across the repository, including different Names for one user.")


@dataclass(frozen=True)
class Entry:
    uploader_id: int
    name: str
    display_name: str
    path: str
    digest: str

    @property
    def key(self):
        return f"{self.uploader_id}/{self.name}"

    @property
    def manifest_path(self):
        return f"manifest/{self.digest}/manifest.toml"

    def fields(self):
        return {"schema_version": 1, "hash": self.digest,
                "uploader_id": self.uploader_id, "name": self.name,
                "display_name": self.display_name, "path": "/" + self.path}


def safe_path(path):
    if not isinstance(path, str) or len(path) > 1024:
        raise Invalid("Invalid or overly long Git path")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise Invalid(f"Unsafe path: {path!r}")
    if UNSAFE.search(path):
        raise Invalid(f"Unsafe path: {path!r}")
    return parts


def data_location(path):
    parts = safe_path(path)
    if len(parts) != 4 or parts[0] != "data":
        raise Invalid(f"Images and meme.toml must be under data/userID/Name/: {path}")
    if not USER.fullmatch(parts[1]) or not NAME.fullmatch(parts[2]):
        raise Invalid(f"Invalid user ID or Name: {path}; Name must be 1-64 ASCII letters, digits, underscores, or hyphens")
    if len(parts[3].encode("utf-8")) > 255:
        raise Invalid(f"Filename is too long: {path}")
    return parts


def parse_toml(data, path, limit=MAX_METADATA):
    if len(data) > limit:
        raise Invalid(f"TOML exceeds {limit} bytes: {path}")
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid(f"Invalid UTF-8 TOML: {path}") from error


def image_kind(data):
    signatures = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"),
                  (b"GIF87a", "gif"), (b"GIF89a", "gif"))
    for signature, kind in signatures:
        if data.startswith(signature):
            return kind
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    raise Invalid("Invalid image signature; only PNG, JPEG, WebP, and GIF are supported")


def check_image(data, path):
    if not data or len(data) > MAX_IMAGE:
        raise Invalid(f"Image is empty or exceeds 5 MiB: {path}")
    extension = path.rsplit(".", 1)[-1].lower()
    if extension not in EXTENSIONS:
        raise Invalid(f"Unsupported image extension: {path}")
    expected = "jpeg" if extension == "jpg" else extension
    if image_kind(data) != expected:
        raise Invalid(f"Image signature does not match its extension: {path}")
    return hashlib.sha256(data).hexdigest()


def read_metadata(read, path):
    metadata = parse_toml(read(path, MAX_METADATA), path)
    if set(metadata) != {"file", "display_name"}:
        raise Invalid(f"meme.toml must contain only file and display_name: {path}")
    if not isinstance(metadata["file"], str):
        raise Invalid(f"file must be a filename string: {path}")
    display = metadata["display_name"]
    if not isinstance(display, str) or not display.strip():
        raise Invalid(f"display_name must be a nonempty string: {path}")
    return metadata


def entry_from_files(key, paths, read):
    metadata_path = f"data/{key}/meme.toml"
    if metadata_path not in paths or len(paths) != 2:
        raise Invalid(f"data/{key}/ must contain exactly one image and meme.toml")
    metadata = read_metadata(read, metadata_path)
    filename = metadata["file"]
    image_path = f"data/{key}/{filename}"
    data_location(image_path)
    if image_path not in paths or filename == "meme.toml":
        raise Invalid(f"file must point to the only image in the same directory: {metadata_path}")
    user, name = key.split("/")
    digest = check_image(read(image_path, MAX_IMAGE), image_path)
    return Entry(int(user), name, metadata["display_name"], image_path, digest)


def read_entries(paths, read):
    groups = {}
    for path in sorted(paths):
        if path.startswith("data/"):
            parts = data_location(path)
            groups.setdefault("/".join(parts[1:3]), set()).add(path)
    if len(groups) > MAX_ENTRIES:
        raise Invalid(f"Entry count exceeds the per-run limit of {MAX_ENTRIES}")
    return {key: entry_from_files(key, files, read) for key, files in groups.items()}


def unique_entries(entries, preferred=()):
    seen = {}
    order = sorted(entries, key=lambda key: (key not in preferred, key))
    for key in order:
        entry = entries[key]
        if entry.digest in seen:
            raise Duplicate(entry.digest, seen[entry.digest], entry.path)
        seen[entry.digest] = entry.path


def manifest_bytes(entry):
    lines = []
    for key, value in entry.fields().items():
        encoded = json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
        lines.append(f"{key} = {encoded}\n")
    data = "".join(lines).encode("utf-8")
    if len(data) > MAX_METADATA:
        raise Invalid("Generated manifest exceeds 32 KiB; shorten display_name")
    return data


def expected_manifests(entries):
    return {entry.manifest_path: manifest_bytes(entry) for entry in entries.values()}


def check_manifest_path(path):
    parts = safe_path(path)
    valid = len(parts) == 3 and parts[0] == "manifest"
    if not valid or not HASH.fullmatch(parts[1]) or parts[2] != "manifest.toml":
        raise Invalid(f"Invalid generated file path: {path}")


def validate_manifests(paths, read, entries):
    actual = {path for path in paths if path.startswith("manifest/")}
    actual.discard("manifest/index.toml")
    expected = expected_manifests(entries)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise Invalid(f"Manifests do not match the image set; missing {missing[:3]}, extra {extra[:3]}")
    for path, canonical in expected.items():
        check_manifest_path(path)
        fields = parse_toml(read(path, MAX_METADATA), path)
        if set(fields) != MANIFEST_FIELDS:
            raise Invalid(f"Manifest fields do not match schema_version=1: {path}")
        if type(fields.get("schema_version")) is not int or type(fields.get("uploader_id")) is not int:
            raise Invalid(f"Manifest version and user ID must be integers: {path}")
        if fields != parse_toml(canonical, path):
            raise Invalid(f"Manifest does not match the image bytes or meme.toml: {path}")


def index_bytes(source_commit, hashes):
    if not SHA.fullmatch(source_commit):
        raise Invalid("source_commit must be a full 40-character lowercase Git SHA")
    values = sorted(set(hashes))
    if any(not HASH.fullmatch(value) for value in values):
        raise Invalid("Index contains an invalid image SHA-256")
    return (f'schema_version = 1\nsource_commit = "{source_commit}"\n'
            f'hashes = {json.dumps(values)}\n').encode("utf-8")
