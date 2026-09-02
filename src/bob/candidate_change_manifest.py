"""Controller-owned production-tree witnesses for hardened feature runs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


SCHEMA_VERSION = "bob.candidate-change-bundle.v1"
DEFAULT_MAX_EVALUATOR_CONTENT_BYTES: int | None = None
_RUNTIME_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".bob",
        ".claude",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)
_RUNTIME_FILE_NAMES = frozenset({".coverage"})


@dataclass(frozen=True, order=True)
class CandidateTreeEntry:
    path: str
    entry_type: str
    mode: int
    sha256: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class CandidateChangeBundle:
    feature_id: str
    baseline_manifest_sha256: str
    final_manifest_sha256: str
    changes: tuple[dict[str, object], ...]
    content: tuple[dict[str, str], ...]
    sha256: str
    canonical_json: str

    @property
    def stage_paths(self) -> tuple[str, ...]:
        return tuple(
            str(item["path"])
            for item in self.changes
            if item.get("entry_type") != "directory"
        )

    @property
    def expected_file_sha256(self) -> dict[str, str | None]:
        return {
            str(item["path"]): (
                str(item["sha256"]) if item.get("sha256") is not None else None
            )
            for item in self.changes
            if item.get("entry_type") != "directory"
        }

    @property
    def expected_file_modes(self) -> dict[str, str | None]:
        """Return Git index modes for every changed non-directory path."""
        result: dict[str, str | None] = {}
        for item in self.changes:
            if item.get("entry_type") == "directory":
                continue
            mode = item.get("mode")
            result[str(item["path"])] = (
                None if mode is None else ("100755" if int(mode) & 0o111 else "100644")
            )
        return result


def _normalise_excluded_roots(values: Sequence[str]) -> tuple[PurePosixPath, ...]:
    roots: list[PurePosixPath] = []
    for value in values:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"excluded root must be workspace-relative: {value!r}")
        roots.append(path)
    return tuple(roots)


def _is_excluded(path: str, roots: Sequence[PurePosixPath]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate == root or root in candidate.parents for root in roots)


def _hash_regular_file(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"candidate file is not regular/single-link: {path}")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_mode,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        ):
            raise ValueError(f"candidate file changed while hashing: {path}")
        return digest.hexdigest(), size
    finally:
        os.close(fd)


def _read_regular_file_stable(path: Path) -> bytes:
    """Read one single-link regular file without following or racing links."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"candidate file is not regular/single-link: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_mode,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        ):
            raise ValueError(f"candidate file changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def snapshot_candidate_tree(
    *,
    cwd: str | Path,
    excluded_roots: Sequence[str] = (),
) -> tuple[CandidateTreeEntry, ...]:
    """Hash the complete production tree without following links."""
    workspace = Path(cwd).resolve(strict=True)
    excluded = _normalise_excluded_roots(excluded_roots)
    entries: list[CandidateTreeEntry] = []
    for current, dir_names, file_names in os.walk(workspace, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(dir_names):
            path = current_path / name
            relative = path.relative_to(workspace).as_posix()
            if (
                current_path == workspace
                and name in _RUNTIME_DIRECTORY_NAMES
                or _is_excluded(relative, excluded)
            ):
                continue
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path).encode("utf-8", errors="surrogateescape")
                entries.append(
                    CandidateTreeEntry(
                        relative,
                        "symlink",
                        stat.S_IMODE(info.st_mode),
                        hashlib.sha256(target).hexdigest(),
                        len(target),
                    )
                )
                continue
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"non-directory tree entry: {relative}")
            entries.append(
                CandidateTreeEntry(
                    relative,
                    "directory",
                    stat.S_IMODE(info.st_mode),
                    None,
                    None,
                )
            )
            kept.append(name)
        dir_names[:] = kept

        for name in sorted(file_names):
            if current_path == workspace and name in _RUNTIME_FILE_NAMES:
                continue
            path = current_path / name
            relative = path.relative_to(workspace).as_posix()
            if _is_excluded(relative, excluded):
                continue
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path).encode("utf-8", errors="surrogateescape")
                entries.append(
                    CandidateTreeEntry(
                        relative,
                        "symlink",
                        mode,
                        hashlib.sha256(target).hexdigest(),
                        len(target),
                    )
                )
            elif stat.S_ISREG(info.st_mode):
                digest, size = _hash_regular_file(path)
                entries.append(
                    CandidateTreeEntry(relative, "file", mode, digest, size)
                )
            else:
                raise ValueError(f"non-regular candidate entry: {relative}")
    return tuple(sorted(entries))


def manifest_sha256(manifest: Sequence[CandidateTreeEntry]) -> str:
    payload = [asdict(entry) for entry in sorted(manifest)]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_candidate_change_bundle(
    *,
    feature_id: str,
    cwd: str | Path,
    baseline: Sequence[CandidateTreeEntry],
    final: Sequence[CandidateTreeEntry],
    max_content_bytes: int | None = DEFAULT_MAX_EVALUATOR_CONTENT_BYTES,
) -> CandidateChangeBundle:
    """Bind all baseline→final changes, including untracked regular files."""
    if max_content_bytes is not None and max_content_bytes < 1:
        raise ValueError("max_content_bytes must be positive")
    workspace = Path(cwd).resolve(strict=True)
    before = {entry.path: entry for entry in baseline}
    after = {entry.path: entry for entry in final}
    changed_non_directory_paths = {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
        and (after.get(path) or before.get(path)).entry_type != "directory"
    }
    changes: list[dict[str, object]] = []
    content: list[dict[str, str]] = []
    content_bytes = 0
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        operation = "created" if old is None else "deleted" if new is None else "modified"
        entry = new or old
        assert entry is not None
        if entry.entry_type == "directory":
            # Git does not version directories.  A created/deleted directory is
            # admissible only when it is mechanically implied by an authorized
            # changed file beneath it; mode-only and empty-directory changes
            # cannot be represented by the exact commit and therefore fail
            # closed instead of becoming evaluator-only evidence.
            prefix = f"{path}/"
            if (
                old is not None
                and new is not None
                or not any(
                    candidate.startswith(prefix)
                    for candidate in changed_non_directory_paths
                )
            ):
                raise ValueError(
                    f"uncommittable directory-only candidate change: {path}"
                )
            continue
        if new is not None and new.entry_type == "symlink":
            raise ValueError(f"new or modified candidate symlink is forbidden: {path}")
        change = {
            "path": path,
            "operation": operation,
            "entry_type": new.entry_type if new is not None else old.entry_type,
            "mode": new.mode if new is not None else None,
            "sha256": new.sha256 if new is not None else None,
            "size_bytes": new.size_bytes if new is not None else None,
            "baseline_sha256": old.sha256 if old is not None else None,
        }
        changes.append(change)
        if new is None or new.entry_type != "file":
            continue
        raw = _read_regular_file_stable(workspace / path)
        if hashlib.sha256(raw).hexdigest() != new.sha256:
            raise ValueError(f"candidate file changed after final manifest: {path}")
        try:
            rendered = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"binary production change is evaluator-blind and forbidden: {path}"
            ) from exc
        if "\x00" in rendered:
            raise ValueError(
                f"NUL-containing production change is evaluator-blind and forbidden: {path}"
            )
        content_bytes += len(raw)
        if max_content_bytes is not None and content_bytes > max_content_bytes:
            raise ValueError(
                "candidate textual change content exceeds hardened evaluator "
                f"limit of {max_content_bytes} bytes"
            )
        content.append({"path": path, "text": rendered})

    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "feature_id": feature_id,
        "baseline_manifest_sha256": manifest_sha256(baseline),
        "final_manifest_sha256": manifest_sha256(final),
        "changes": changes,
        "content": content,
    }
    unsigned_json = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(unsigned_json.encode("utf-8")).hexdigest()
    signed = dict(unsigned)
    signed["change_bundle_sha256"] = digest
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":"))
    return CandidateChangeBundle(
        feature_id=feature_id,
        baseline_manifest_sha256=unsigned["baseline_manifest_sha256"],
        final_manifest_sha256=unsigned["final_manifest_sha256"],
        changes=tuple(changes),
        content=tuple(content),
        sha256=digest,
        canonical_json=canonical,
    )


__all__ = [
    "CandidateChangeBundle",
    "CandidateTreeEntry",
    "build_candidate_change_bundle",
    "manifest_sha256",
    "snapshot_candidate_tree",
]
