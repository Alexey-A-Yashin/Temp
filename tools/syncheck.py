#!/usr/bin/env python3
"""Синтаксическая проверка всех C#-файлов через tree-sitter."""
import sys, pathlib
from tree_sitter import Language, Parser
import tree_sitter_c_sharp as tscs

LANG = Language(tscs.language())
parser = Parser(LANG)

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
files = sorted(p for p in root.rglob("*.cs") if ".git" not in p.parts)

def collect(node, out, path):
    if node.type == "ERROR" or node.is_missing:
        out.append((node.start_point[0] + 1, node.type, node.text[:80].decode("utf8", "replace")))
    for c in node.children:
        collect(c, out, path)

bad = 0
for f in files:
    src = f.read_bytes()
    tree = parser.parse(src)
    errs = []
    collect(tree.root_node, errs, f)
    if errs:
        bad += 1
        print(f"[SYNTAX] {f.relative_to(root)}")
        for line, t, txt in errs[:5]:
            print(f"    стр.{line}: {t}: {txt!r}")

print(f"\nПроверено файлов: {len(files)}; с синтаксическими ошибками: {bad}")
sys.exit(1 if bad else 0)
