"""Shared helpers for department agents."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from agents.schemas import SharedBundle

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def strip_fences(raw: str) -> str:
    return _FENCE.sub("", raw.strip())


def build_context(bundle: SharedBundle) -> str:
    """Render the shared bundle as numbered, cited source blocks for the prompt."""
    blocks = []
    for i, s in enumerate(bundle.sources):
        blocks.append(f"[{i}] ({s.source_type.value}) {s.url}\n{s.text}")
    return "\n\n".join(blocks)


def parse_into(raw: str, schema: type[T]) -> T:
    return schema.model_validate(json.loads(strip_fences(raw)))


GROUNDING_RULE = (
    "Every claim MUST include at least one citation whose `snippet` is copied "
    "VERBATIM from one of the sources above, plus that source's `url`. Do not "
    "invent facts. If a signal is not supported by the sources, omit it."
)
