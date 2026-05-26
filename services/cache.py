"""Shared scrape-cache — the Lean single-fetch store.

Scrape a target once, persist the SharedBundle, and let every department read
it. Re-runs short-circuit on the cached bundle so we never pay to scrape twice.
"""

from __future__ import annotations

import re
from pathlib import Path

from agents.schemas import CascadeBrief, SharedBundle

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def slugify(target: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")
    return slug or "unknown"


def _target_dir(target: str) -> Path:
    d = DATA_DIR / slugify(target)
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundle_path(target: str) -> Path:
    return _target_dir(target) / "bundle.json"


def brief_path(target: str) -> Path:
    return _target_dir(target) / "brief.json"


def save_bundle(bundle: SharedBundle) -> Path:
    path = bundle_path(bundle.target)
    path.write_text(bundle.model_dump_json(indent=2))
    return path


def load_bundle(target: str) -> SharedBundle | None:
    path = bundle_path(target)
    if not path.exists():
        return None
    return SharedBundle.model_validate_json(path.read_text())


def save_brief(brief: CascadeBrief) -> Path:
    path = brief_path(brief.target)
    path.write_text(brief.model_dump_json(indent=2))
    return path


def load_brief(target: str) -> CascadeBrief | None:
    path = brief_path(target)
    if not path.exists():
        return None
    return CascadeBrief.model_validate_json(path.read_text())
