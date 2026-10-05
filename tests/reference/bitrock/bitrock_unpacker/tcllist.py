from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

ManifestEntry = tuple[str, str, str, int]


def tokenize_tcl_list(s: str) -> Iterator[str]:
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        c = s[i]
        if c == "{":
            depth = 1
            i += 1
            start = i
            while i < n and depth:
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                i += 1
            yield s[start : i - 1]
        elif c == '"':
            i += 1
            buf = []
            while i < n:
                ch = s[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\" and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                buf.append(ch)
                i += 1
            yield "".join(buf)
        else:
            start = i
            while i < n and not s[i].isspace():
                i += 1
            yield s[start:i]


def parse_manifest(text: str) -> tuple[list[ManifestEntry], dict[str, int], int]:
    entries: list[ManifestEntry] = []
    tokens = list(tokenize_tcl_list(text))
    for j in range(0, len(tokens) - 1, 2):
        name = tokens[j]
        props = tokens[j + 1].strip()
        m = re.match(r"^(file|directory|link)\s+(\S+)", props)
        if not m:
            continue
        typ = m.group(1)
        mode = m.group(2)
        declared = 0
        if typ == "file":
            for size in re.findall(r"\{\{\d+\s+(\d+)\}\}", props):
                declared += int(size)
        entries.append((name, typ, mode, declared))
    counts: dict[str, int] = {"file": 0, "directory": 0, "link": 0}
    total_bytes = 0
    for _, typ, _, declared in entries:
        counts[typ] += 1
        total_bytes += declared
    return entries, counts, total_bytes
