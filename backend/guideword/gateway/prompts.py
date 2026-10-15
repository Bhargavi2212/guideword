"""Versioned prompts (CLAUDE.md §9 "Prompts"; plan R19).

`config/routing.yaml` names the version of each prompt; the file is
`prompts/<name>/<version>.md`. Everything above the first `---` line is a header for people
(job, placeholders, tools) and is not sent. Placeholders `{{name}}` are filled in one pass,
so plant text that happens to contain `{{...}}` is never expanded.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from guideword.config import DEFAULT_PROMPTS_DIR, Config

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_HEADER_END = "\n---\n"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    body: str

    @property
    def label(self) -> str:
        """The prompt version recorded on every model call and in the cache key."""
        return f"{self.name}/{self.version}"


def load_prompt(name: str, config: Config, prompts_dir: Path | None = None) -> Prompt:
    version = config.routing.prompts[name]
    root = prompts_dir if prompts_dir is not None else DEFAULT_PROMPTS_DIR
    text = (root / name / f"{version}.md").read_text(encoding="utf-8")
    _, found, body = text.partition(_HEADER_END)
    return Prompt(name, version, (body if found else text).lstrip("\n"))


def render(body: str, values: Mapping[str, str]) -> str:
    """Fill every `{{name}}`; a missing value or an unused one is an error."""
    used: set[str] = set()

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"no value for placeholder {key}")
        used.add(key)
        return values[key]

    text = _PLACEHOLDER.sub(fill, body)
    unused = set(values) - used
    if unused:
        raise KeyError(f"values for placeholders the prompt does not have: {sorted(unused)}")
    return text
