import re
from typing import Set

VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")

def extract_versions(version_name: str) -> Set[str]:
    if not version_name:
        return set()
    return set(VERSION_RE.findall(version_name))
