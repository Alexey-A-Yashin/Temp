#!/usr/bin/env python3
"""Готовит копию исходников для сборки под mono (C# 8):
   - file-scoped namespace  ->  блочный namespace { ... }
Работает по каталогу на месте.
"""
import re, sys, pathlib

root = pathlib.Path(sys.argv[1])
NS = re.compile(r'^namespace\s+([A-Za-z_][\w.]*)\s*;\s*$')

changed = 0
for f in sorted(root.rglob("*.cs")):
    lines = f.read_text(encoding="utf8").splitlines()
    idx = None
    for i, ln in enumerate(lines):
        m = NS.match(ln.strip())
        if m:
            idx = i
            name = m.group(1)
            break
    if idx is None:
        continue
    body = lines[idx + 1:]
    out = lines[:idx] + [f"namespace {name}", "{"] + ["    " + b if b.strip() else b for b in body] + ["}"]
    f.write_text("\n".join(out) + "\n", encoding="utf8")
    changed += 1

print(f"file-scoped namespace преобразован в {changed} файлах")
