#!/usr/bin/env python3
"""МЁРТВЫЙ КОД: объявлено, но нигде не используется.

Заведено после того, как обнаружилось, что LayeredHeight — старая шумовая
функция, выведенная из рельефа ещё в V283, — прожила мёртвой ЧЕТЫРЕ МЕСЯЦА и
успела испортить отчёт о рельефе: он считался по ней и врал четыре сборки
подряд.

Ищет: открытые методы и постоянные, которые объявлены и ни разу не вызваны.
"""
import re, os, sys

root = sys.argv[1] + "/scripts"
files = []
for dp, _, fs in os.walk(root):
    for f in fs:
        if f.endswith(".cs"): files.append(os.path.join(dp, f))

# весь код без комментариев и строк
whole = []
for p in files:
    s = open(p, encoding="utf-8", errors="replace").read()
    # ---- СТРОКИ НЕ ВЫЧИЩАЮТСЯ ----
    #
    # Прежде здесь строки заменялись пустыми — и обращения ВНУТРИ них терялись.
    # А в C# со вставками ($"...{RunMode.Describe()}...") вызов живёт именно там.
    #
    # Из-за этого проверка объявила мёртвыми Describe и BakedImpostorCount, я их
    # удалил, и сборка сломалась.
    #
    # Теперь убираются только комментарии.
    s = re.sub(r'^\s*//.*$', '', s, flags=re.M)
    whole.append((p, s))

print("Проверка мёртвого кода:")
dead = 0
for p, s in whole:
    # объявления: public/internal static методы и постоянные
    for m in re.finditer(r'(?:public|internal)\s+(?:static\s+)?(?:readonly\s+)?(?:const\s+)?'
                         r'[\w<>?\[\],\.]+\s+(\w+)\s*(?:\(|=|=>|;)', s):
        name = m.group(1)
        if len(name) < 4: continue
        # сколько раз встречается ВО ВСЁМ проекте, кроме своего объявления
        total = sum(len(re.findall(rf'\b{name}\b', s2)) for _, s2 in whole)
        own = len(re.findall(rf'\b{name}\b', s))
        # объявление считается один раз; ищем ХОТЬ ОДНО использование
        if total <= 1:
            print(f"  {os.path.basename(p)}: {name} — объявлено, НЕ ИСПОЛЬЗУЕТСЯ")
            dead += 1
print("готово" if not dead else f"НАЙДЕНО МЁРТВОГО: {dead}")
