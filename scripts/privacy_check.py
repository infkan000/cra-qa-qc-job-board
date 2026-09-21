#!/usr/bin/env python3
"""Fail publication when likely credentials or personal identifiers are present."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".json", ".jsonl", ".py", ".html", ".md", ".yml", ".yaml", ".txt"}
RULES = {
    "GitHub access token": re.compile(r"(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    "OpenAI access token": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "embedded credential": re.compile(r"(?i)(?:password|passwd|access[_-]?token|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
    "local user path": re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+"),
    "mainland mobile number": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "personal email": re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
}


def main() -> int:
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in RULES.items():
            for match in pattern.finditer(text):
                value = match.group(0)
                if path.name == "privacy_check.py" and name == "local user path":
                    continue
                if name == "personal email" and value.lower().endswith("@users.noreply.github.com"):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name}")
    forbidden_names = {".env", "id_rsa", "id_ed25519", "credentials.json"}
    for path in ROOT.rglob("*"):
        if path.is_file() and path.name.lower() in forbidden_names:
            findings.append(f"{path.relative_to(ROOT)}: forbidden credential file")
    if findings:
        print("PRIVACY_CHECK_FAILED")
        print("\n".join(findings))
        return 1
    print("PRIVACY_CHECK_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

