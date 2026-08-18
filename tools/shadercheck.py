#!/usr/bin/env python3
"""Проверка .gdshader: скобки, объявления, известные ловушки Godot 4 mobile.

Не компилятор GLSL — движка тут нет. Ловит то, что ловится статически:
несбалансированные скобки, пропущенные точки с запятой в объявлениях uniform,
обращения к недоступным в Forward Mobile встроенным переменным, а также запись
видовых координат в VERTEX без skip_vertex_transform.
"""
import re, sys, pathlib

# Недоступно в Forward Mobile (см. ограничения проекта).
FORBIDDEN = [
    ("hint_normal_roughness_texture", "недоступно вне Forward+"),
    ("DEPTH_TEXTURE", "чтение depth ломает sub-passes в mobile"),
    ("SCREEN_TEXTURE", "чтение screen ломает sub-passes в mobile"),
]

def check(path: pathlib.Path) -> list[str]:
    src = path.read_text(encoding="utf8")
    # Убираем комментарии, чтобы не считать скобки в тексте.
    body = re.sub(r"//[^\n]*", "", src)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    errs = []

    for ch_open, ch_close in [("{", "}"), ("(", ")"), ("[", "]")]:
        if body.count(ch_open) != body.count(ch_close):
            errs.append(f"скобки {ch_open}{ch_close}: "
                        f"{body.count(ch_open)} против {body.count(ch_close)}")

    if not re.search(r"^\s*shader_type\s+\w+\s*;", body, re.M):
        errs.append("нет объявления shader_type")

    for line in body.splitlines():
        s = line.strip()
        if s.startswith("uniform ") and not s.endswith(";"):
            errs.append(f"uniform без точки с запятой: {s[:60]}")
        if s.startswith("varying ") and not s.endswith(";"):
            errs.append(f"varying без точки с запятой: {s[:60]}")

    for token, why in FORBIDDEN:
        if token in body:
            errs.append(f"{token}: {why}")

    # Запись видовой координаты в VERTEX требует skip_vertex_transform.
    writes_view = re.search(r"VERTEX\s*=\s*\(\s*(VIEW_MATRIX|MODELVIEW_MATRIX)", body)
    has_skip = "skip_vertex_transform" in body
    if writes_view and not has_skip:
        errs.append("VERTEX получает видовую координату, но нет skip_vertex_transform "
                    "— движок применит преобразование повторно")

    # varying целого типа обязан быть flat.
    for m in re.finditer(r"^\s*varying\s+(?!flat)(\w+)\s+\w+\s*;", body, re.M):
        if m.group(1) in ("int", "uint", "ivec2", "ivec3", "ivec4"):
            errs.append(f"целочисленный varying без flat: {m.group(0).strip()}")

    return errs

root = pathlib.Path(sys.argv[1])
bad = 0
for f in sorted(root.rglob("*.gdshader")):
    errs = check(f)
    status = "ок" if not errs else "ОШИБКИ"
    print(f"{f.name:28} {status}")
    for e in errs:
        bad += 1
        print(f"    {e}")
print(f"\nПроверено шейдеров: {len(list(root.rglob('*.gdshader')))}, замечаний: {bad}")
sys.exit(1 if bad else 0)
