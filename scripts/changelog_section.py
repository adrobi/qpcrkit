"""Print one version's section of CHANGELOG.md: the text of its GitHub release.

Usage: python scripts/changelog_section.py v1.1.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def section(text: str, version: str) -> str:
    version = version.lstrip("v")
    m = re.search(rf"^## \[{re.escape(version)}\].*?$(.*?)(?=^## \[|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


if __name__ == "__main__":
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    text = section(changelog.read_text(encoding="utf-8"), sys.argv[1])
    if not text:
        sys.exit(f"CHANGELOG.md has no section for {sys.argv[1]}")
    print(text)
