from __future__ import annotations

import copy
import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from devflow_sdk.plugin.plugin_registry import PluginEntry

REGISTRY_PATH = Path.home() / ".devflow" / "plugin-registry.json"
REGISTRY_VERSION = 1


class RegistryError(Exception):
    """Base error for registry persistence and validation failures."""


class MalformedRegistryError(RegistryError):
    """The persisted registry does not match the supported schema."""


class RegistryIOError(RegistryError):
    """The registry or its lock could not be safely accessed or written."""


class InvalidRegistrationError(RegistryError):
    """A requested registration does not identify a regular plugin file."""


@dataclass
class _Snapshot:
    plugins: dict[str, PluginEntry]
    top_level_metadata: dict[str, Any]
    entry_metadata: dict[str, dict[str, Any]]


class RegistryStore:
    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._registry_path = registry_path
        self._lock_path = registry_path.parent / ".registry.lock"

    def snapshot(self) -> Mapping[str, PluginEntry]:
        with self._lock(shared=True):
            return self._public_snapshot(self._read_locked())

    def register(self, name: str, path: str, formula: str | None = None) -> None:
        self._validate_registration(name, path, formula)
        with self._lock(shared=False):
            snapshot = self._read_locked()
            metadata = copy.deepcopy(snapshot.entry_metadata.get(name, {}))
            snapshot.plugins[name] = PluginEntry(name=name, path=path, formula=formula)
            snapshot.entry_metadata[name] = metadata
            self._write_locked(snapshot)

    def unregister(self, name: str) -> None:
        with self._lock(shared=False):
            snapshot = self._read_locked()
            if name not in snapshot.plugins:
                return
            del snapshot.plugins[name]
            snapshot.entry_metadata.pop(name, None)
            self._write_locked(snapshot)

    def _purge_missing(self) -> tuple[Mapping[str, PluginEntry], list[str]]:
        with self._lock(shared=False):
            snapshot = self._read_locked()
            removed = sorted(
                name for name, entry in snapshot.plugins.items() if not Path(entry.path).is_file()
            )
            if removed:
                for name in removed:
                    del snapshot.plugins[name]
                    snapshot.entry_metadata.pop(name, None)
                self._write_locked(snapshot)
            return self._public_snapshot(snapshot), removed

    @contextmanager
    def _lock(self, *, shared: bool) -> Iterator[None]:
        try:
            self._ensure_parent_directory()
            lock_fd = self._open_lock()
            with os.fdopen(lock_fd, "r+") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except RegistryError:
            raise
        except OSError as error:
            raise RegistryIOError(
                f"registry lock operation failed for {self._registry_path}: {error}"
            ) from error

    def _ensure_parent_directory(self) -> None:
        current = self._registry_path.parent
        missing: list[Path] = []
        while not current.exists():
            missing.append(current)
            current = current.parent
        for parent in [current, *reversed(missing)]:
            if parent.is_symlink() or not parent.is_dir():
                raise RegistryIOError(f"registry parent is not a real directory: {parent}")
            if parent in missing:
                parent.mkdir(mode=0o700)

    def _open_lock(self) -> int:
        if self._lock_path.is_symlink() or (
            self._lock_path.exists() and not self._lock_path.is_file()
        ):
            raise RegistryIOError(f"registry lock is not a regular file: {self._lock_path}")
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            try:
                fd = os.open(
                    self._lock_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
                    0o600,
                )
            except FileExistsError:
                if self._lock_path.is_symlink() or not self._lock_path.is_file():
                    raise RegistryIOError(
                        f"registry lock is not a regular file: {self._lock_path}"
                    )
                fd = os.open(self._lock_path, os.O_RDWR | nofollow)
            os.fchmod(fd, 0o600)
            return fd
        except RegistryError:
            raise
        except OSError as error:
            raise RegistryIOError(f"cannot open registry lock {self._lock_path}: {error}") from error

    def _read_locked(self) -> _Snapshot:
        if not os.path.lexists(self._registry_path):
            return _Snapshot({}, {}, {})
        if self._registry_path.is_symlink() or not self._registry_path.is_file():
            raise RegistryIOError(f"registry path is not a regular file: {self._registry_path}")
        try:
            raw = json.loads(self._registry_path.read_text())
        except json.JSONDecodeError as error:
            raise MalformedRegistryError(
                f"malformed registry at {self._registry_path}: invalid JSON"
            ) from error
        except OSError as error:
            raise RegistryIOError(f"cannot read registry {self._registry_path}: {error}") from error
        return self._parse(raw)

    def _parse(self, raw: Any) -> _Snapshot:
        if not isinstance(raw, dict) or raw.get("version") != REGISTRY_VERSION:
            raise MalformedRegistryError(f"unsupported registry format at {self._registry_path}")
        plugins_raw = raw.get("plugins")
        if not isinstance(plugins_raw, dict):
            raise MalformedRegistryError(f"plugins must be an object at {self._registry_path}")
        plugins: dict[str, PluginEntry] = {}
        entry_metadata: dict[str, dict[str, Any]] = {}
        for name, entry in plugins_raw.items():
            if not isinstance(name, str) or not name.strip():
                raise MalformedRegistryError(f"invalid plugin name at {self._registry_path}")
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
                raise MalformedRegistryError(f"invalid path for plugin {name!r}")
            formula = entry.get("formula")
            if formula is not None and (not isinstance(formula, str) or not formula.strip()):
                raise MalformedRegistryError(f"invalid formula for plugin {name!r}")
            plugins[name] = PluginEntry(name=name, path=entry["path"], formula=formula)
            entry_metadata[name] = copy.deepcopy(
                {key: value for key, value in entry.items() if key not in {"path", "formula"}}
            )
        top_metadata = copy.deepcopy({key: value for key, value in raw.items() if key not in {"version", "plugins"}})
        return _Snapshot(plugins, top_metadata, entry_metadata)

    def _write_locked(self, snapshot: _Snapshot) -> None:
        mode = stat.S_IMODE(self._registry_path.stat().st_mode) if self._registry_path.exists() else 0o600
        payload = copy.deepcopy(snapshot.top_level_metadata)
        payload.update({"version": REGISTRY_VERSION, "plugins": {}})
        for name, entry in snapshot.plugins.items():
            data = copy.deepcopy(snapshot.entry_metadata.get(name, {}))
            data.update({"path": entry.path})
            if entry.formula is not None:
                data["formula"] = entry.formula
            payload["plugins"][name] = data
        fd = -1
        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._registry_path.parent, prefix=".registry-")
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w") as file:
                fd = -1
                json.dump(payload, file, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.rename(tmp_path, self._registry_path)
        except OSError as error:
            if fd >= 0:
                os.close(fd)
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise RegistryIOError(f"cannot write registry {self._registry_path}: {error}") from error

    def _public_snapshot(self, snapshot: _Snapshot) -> Mapping[str, PluginEntry]:
        return MappingProxyType(dict(snapshot.plugins))

    def _validate_registration(self, name: str, path: str, formula: str | None) -> None:
        if not isinstance(name, str) or not name.strip():
            raise InvalidRegistrationError("plugin name must be non-empty")
        if not isinstance(path, str) or not Path(path).is_file():
            raise InvalidRegistrationError(f"plugin path must be a regular file: {path}")
        if formula is not None and (not isinstance(formula, str) or not formula.strip()):
            raise InvalidRegistrationError("formula must be None or a non-empty string")
