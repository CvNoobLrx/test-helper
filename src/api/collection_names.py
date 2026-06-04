"""Display-name to storage-name mapping for user-facing subjects."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.core.settings import resolve_path

_VALID_COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,510}[A-Za-z0-9]$")


def _alias_path() -> Path:
    return resolve_path("data/db/collection_aliases.json")


def _load_aliases() -> dict[str, str]:
    path = _alias_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k and v}


def _save_aliases(aliases: dict[str, str]) -> None:
    path = _alias_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")


def is_storage_collection(name: str) -> bool:
    value = (name or "").strip()
    if not _VALID_COLLECTION_RE.match(value):
        return False
    if ".." in value:
        return False
    return not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", value)


def storage_collection(display_name: str) -> str:
    """Return a Chroma-safe collection name for a user-facing subject."""
    name = (display_name or "default").strip() or "default"
    if is_storage_collection(name):
        return name

    aliases = _load_aliases()
    if name in aliases:
        return aliases[name]

    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
    storage_name = f"c_{digest}"
    aliases[name] = storage_name
    _save_aliases(aliases)
    return storage_name


def display_collection(storage_name: str) -> str:
    """Return the original subject name when a storage alias exists."""
    name = (storage_name or "default").strip() or "default"
    aliases = _load_aliases()
    for display_name, stored in aliases.items():
        if stored == name:
            return display_name
    return name
