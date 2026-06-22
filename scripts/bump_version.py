#!/usr/bin/env python
"""Bumpa la versione in pyproject.toml e crea commit + tag git.
Uso: uv run python scripts/bump_version.py [patch|minor|major]  (default: patch)."""

import re
import subprocess
import sys
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _current() -> str:
    m = re.search(r'^version\s*=\s*"(.+?)"', PYPROJECT.read_text(), re.M)
    if not m:
        raise RuntimeError("version non trovata in pyproject.toml")
    return m.group(1)


def _bump(part: str) -> str:
    major, minor, patch = map(int, _current().split("."))
    if part == "patch":
        patch += 1
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"part deve essere patch|minor|major, non '{part}'")
    return f"{major}.{minor}.{patch}"


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    old = _current()
    new = _bump(part)
    content = re.sub(r'^(version\s*=\s*)"[^"]+"', rf'\1"{new}"', PYPROJECT.read_text(), flags=re.M)
    PYPROJECT.write_text(content)
    print(f"Bumped {old} → {new}")
    subprocess.run(["git", "add", str(PYPROJECT)], check=True)  # noqa: S603,S607 — git in PATH, script locale
    subprocess.run(["git", "commit", "-m", f"chore: bump version {old} → {new}"], check=True)  # noqa: S603,S607
    subprocess.run(["git", "tag", f"v{new}"], check=True)  # noqa: S603,S607
    print(f"Tag v{new} creato. Per pushare: git push && git push --tags")


if __name__ == "__main__":
    main()
