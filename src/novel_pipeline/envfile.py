"""Minimal ``.env`` loader for local, non-technical use.

The project never writes secrets itself. A user may copy ``.env.example`` to
``.env`` and fill in a key; this module reads that file into the process
environment without printing values. Existing environment variables win by
default, so a shell export or CI secret is never silently replaced.
"""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env(text: str) -> dict[str, str]:
    """Parse simple ``KEY=VALUE`` lines.

    Supports comments, blank lines, an optional ``export`` prefix, single or
    double quotes, and unquoted trailing comments. It deliberately does not
    expand variables or support multi-line values; a novel-generation tool
    needs a small, predictable format, not a shell.
    """
    values: dict[str, str] = {}
    # Windows Notepad may save .env as UTF-8 with a BOM. Without this, the
    # first key would silently become ``﻿NOVEL_LLM_PROVIDER``.
    text = text.removeprefix("﻿")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.match(line)
        if match is None:
            continue
        key, raw_value = match.groups()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value
    return values


def load_env_file(
    path: str | Path = ".env",
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> dict[str, str]:
    """Load ``path`` into ``environ`` (default ``os.environ``).

    Returns only the values that were actually applied. A missing file is not
    an error: local users may configure the process environment directly.
    """
    target = os.environ if environ is None else environ
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    values = parse_env(file_path.read_text(encoding="utf-8"))
    applied: dict[str, str] = {}
    for key, value in values.items():
        if override or key not in target:
            target[key] = value
            applied[key] = value
    return applied
