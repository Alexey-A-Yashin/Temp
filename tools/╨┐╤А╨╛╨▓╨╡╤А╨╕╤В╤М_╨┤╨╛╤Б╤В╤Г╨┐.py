#!/usr/bin/env python3
"""ОБРАЩЕНИЯ К ЗАКРЫТЫМ ЧЛЕНАМ.

Пробник подменяет LevelView3D и GameBootstrap заглушками, поэтому обращение к
private-члену другого класса проходит насквозь. Так вышло в V334: обход брал
FarBackground.OuterExtentWorldStatic, а она была private.

Прежние проверки этого не ловят: они сверяют СУЩЕСТВОВАНИЕ члена, а не право
к нему обращаться.
"""
import re, os, sys

root = sys.argv[1] + "/scripts"

# у кого что закрыто
private = {}
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.endswith(".cs"): continue
        p = os.path.join(dp, f)
        s = open(p, encoding="utf-8", errors="replace").read()
        m = re.search(r'^\s*(?:public|internal)\s+(?:static\s+|sealed\s+|partial\s+|abstract\s+)*'
                      r'(?:class|struct|record)\s+(\w+)', s, re.M)
        if not m: continue
        cls = m.group(1)
        names = set()
        # Имя ищется в САМОЙ строке с private, без требования, чтобы следом шёл
        # знак: у свойств с длинной подписью `=>` переносится на следующую
        # строку, и прежний разбор их пропускал — из-за чего проверка молчала
        # на настоящей ошибке.
        for line in s.split("\n"):
            t = line.strip()
            if not t.startswith("private "): continue
            # отбрасываем возвращаемый тип и всё до имени
            mm = re.match(r'private\s+(?:static\s+|readonly\s+|const\s+|new\s+)*'
                          r'[\w<>?\[\],\.\s]*?(\w+)\s*(?:=>|=|\{|;|\(|$)', t)
            if mm: names.add(mm.group(1))
        private[cls] = names

print("Проверка обращений к закрытым членам:")
bad = 0
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.endswith(".cs"): continue
        p = os.path.join(dp, f)
        s = open(p, encoding="utf-8", errors="replace").read()
        own = re.search(r'^\s*(?:public|internal)\s+(?:static\s+|sealed\s+|partial\s+)*'
                        r'(?:class|struct|record)\s+(\w+)', s, re.M)
        ownName = own.group(1) if own else ""
        # ПОРЯДОК ВАЖЕН: сперва строки, потом комментарии.
        #
        # Обратный порядок съедал код: в строках попадается "res://..." и
        # "https://...", и срез по `//` уничтожал остаток строки вместе с
        # обращениями. Из-за этого проверка молчала на настоящей ошибке.
        code = re.sub(r'"[^"\n]*"', '""', s)
        code = re.sub(r'//.*', '', code)
        for cls, names in private.items():
            if cls == ownName: continue           # свои закрытые члены доступны
            for mm in re.finditer(rf'\b{cls}\.(\w+)', code):
                if mm.group(1) in names:
                    print(f"  {f}: {cls}.{mm.group(1)} — ЗАКРЫТ в {cls}")
                    bad += 1
print("готово" if not bad else f"НАЙДЕНО: {bad}")
