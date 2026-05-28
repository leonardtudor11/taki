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
    obj = json.loads(strip_fences(raw))
    # V7.46 — some LLM responses arrive as a one-element JSON LIST wrapping
    # the schema dict ("[{...}]" instead of "{...}"). Observed crashing
    # Pfizer Finance attempt 3 with a ValidationError "Input should be a
    # valid dictionary ... input_type=list". Unwrap before validation.
    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
        obj = obj[0]
    try:
        return schema.model_validate(obj)
    except Exception:
        # V7.15 — LLMs occasionally wrap the schema content under a key
        # matching the class name. Observed patterns:
        #   pure wrap:   {"RiskProfile": {...}}
        #   hybrid:      {"RiskProfile": {...}, "target": "X"}
        # Lift the wrapped dict's keys into the top level, then re-validate.
        # Outer (sibling) keys win on conflict — they look more like the
        # user-supplied identity (e.g. `target` from the orchestrator).
        if isinstance(obj, dict):
            norm_class = schema.__name__.lower().replace("_", "")
            for k in list(obj.keys()):
                if k.lower().replace("_", "") == norm_class and isinstance(obj[k], dict):
                    wrapped = obj.pop(k)
                    merged = {**wrapped, **obj}   # outer (obj) wins on conflict
                    try:
                        return schema.model_validate(merged)
                    except Exception:
                        pass
        raise


GROUNDING_RULE = (
    "Every claim MUST include at least one citation whose `snippet` is copied "
    "VERBATIM from one of the sources above, plus that source's `url`. Do not "
    "invent facts. If a signal is not supported by the sources, omit it."
)
