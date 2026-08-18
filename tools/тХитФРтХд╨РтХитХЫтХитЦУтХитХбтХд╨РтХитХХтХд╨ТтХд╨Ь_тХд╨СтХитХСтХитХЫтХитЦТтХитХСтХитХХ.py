#!/usr/bin/env python3
"""РАВНОВЕСИЕ СКОБОК И ОСИРОТЕВШИЕ ВЕТКИ.

Пробник подменяет LevelView3D и GameBootstrap заглушками, поэтому синтаксические
ошибки внутри них проходят насквозь. При удалении старого генератора это дало
пять ошибок разом: я убрал `if`, оставив `else` без него.

Простой счёт фигурных скобок не годится: они попадаются в строках, в знаках, в
пояснениях и в дословных строках. Здесь разбор ведётся с учётом всего этого.
"""
import sys, os, re

def scan(path):
    s = open(path, encoding="utf-8").read()
    depth = 0; i = 0; n = len(s); line = 1
    state = None
    clean = []          # текст без строк и пояснений — для поиска осиротевших веток
    while i < n:
        c = s[i]
        if c == "\n":
            line += 1
            if state in (None, "//"): clean.append("\n")
            if state == "//": state = None
        if state is None:
            if c == "/" and i+1 < n and s[i+1] == "/": state = "//"; i += 2; continue
            if c == "/" and i+1 < n and s[i+1] == "*": state = "/*"; i += 2; continue
            if c == '"':
                j = i-1; pre = ""
                while j >= 0 and s[j] in "@$": pre = s[j]+pre; j -= 1
                state = '@"' if "@" in pre else '"'
                i += 1; continue
            if c == "'": state = "'"; i += 1; continue
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth < 0:
                    return f"лишняя }} в строке {line}"
            if c != "\n": clean.append(c)
        elif state == "/*":
            if c == "*" and i+1 < n and s[i+1] == "/": state = None; i += 2; continue
        elif state == '"':
            if c == "\\": i += 2; continue
            if c == '"': state = None
        elif state == '@"':
            if c == '"':
                if i+1 < n and s[i+1] == '"': i += 2; continue
                state = None
        elif state == "'":
            if c == "\\": i += 2; continue
            if c == "'": state = None
        i += 1
    if depth: return f"не хватает {depth} закрывающих"

    # ---- ОСИРОТЕВШИЕ ВЕТКИ ----
    #
    # Проверять «перед else стоит }» мало: она стоит и у осиротевшей ветки. Надо
    # найти ПАРНУЮ открывающую скобку и убедиться, что перед ней был if.
    #
    # Ровно эта ошибка вышла при удалении старого генератора: я убрал if, а
    # блок else остался, и сборка дала пять ошибок разом.
    txt = "".join(clean)
    for m in re.finditer(r"\belse\b", txt):
        before = txt[:m.start()].rstrip()
        if not before:
            continue
        if before[-1] == ";":
            continue          # однострочный if — допустим
        if before[-1] != "}":
            ln = txt[:m.start()].count("\n") + 1
            return f"else без блока около строки {ln}"
        # ищем парную открывающую
        d = 0; k = len(before) - 1
        while k >= 0:
            if before[k] == "}": d += 1
            elif before[k] == "{":
                d -= 1
                if d == 0: break
            k -= 1
        if k < 0: continue
        head = before[:k].rstrip()
        # перед блоком должен быть if(...) — то есть закрывающая круглая скобка
        if not head.endswith(")"):
            ln = txt[:m.start()].count("\n") + 1
            return f"else после блока, который начат НЕ с if — строка {ln}"
        # и сама открывающая круглая должна принадлежать if
        d2 = 0; q = len(head) - 1
        while q >= 0:
            if head[q] == ")": d2 += 1
            elif head[q] == "(":
                d2 -= 1
                if d2 == 0: break
            q -= 1
        kw = head[:q].rstrip()
        if not re.search(r"\b(if|else\s+if)$", kw):
            ln = txt[:m.start()].count("\n") + 1
            return f"else после блока, который начат НЕ с if — строка {ln}"
    return None

root = sys.argv[1] + "/scripts"
print("Проверка скобок и веток:")
bad = 0
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.endswith(".cs"): continue
        p = os.path.join(dp, f)
        r = scan(p)
        if r:
            print(f"  {f}: {r}")
            bad += 1
print("готово" if not bad else f"НАЙДЕНО: {bad}")
