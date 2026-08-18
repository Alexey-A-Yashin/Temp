#!/usr/bin/env python3
"""Разбор обхода уровня (клавиша T).

Файл содержит десятки видов из точек игровых маршрутов (с V112 биомная «ромашка»
заменена на прогулку и сплав) — по четыре азимута с каждой. Скрипт сводит их и САМ
называет проблемы, а не печатает таблицы, которые надо толковать.

Правила выводов заданы явно, чтобы их можно было оспорить:
  • вид «невидим», если ни один его экземпляр в кадре не крупнее 10 точек экрана;
  • точка «пустая», если суммарно видно меньше 15 растений крупнее 10 точек;
  • «нет подлеска» — если в точке нет ни одного куста и ни одной куртины крупнее
    10 точек, а деревья при этом есть;
  • «дорого впустую» — треугольники, потраченные на виды мельче 2 точек.

ОТДЕЛЬНО — ПРОВЕРКА САМОГО ИНСТРУМЕНТА (V147). Всё перечисленное выше отвечает на
вопрос «что ДОЛЖНО попасть в кадр»: счёт идёт по пирамиде видимости и полосам LOD.
Что при этом реально включено на отрисовку, не проверялось ничем — и однажды разошлось
полностью: 494 куртины в кадре по телеметрии при пустой земле на снимке, потому что
корзины покрытий гасились вокруг настоящей камеры игрока. Поле "drawn" в каждом виде
даёт фактические суммы NFull/NLod1/NImp, и расхождение теперь называется первой же
строкой отчёта — как дефект инструмента, а не уровня.
"""
import json, sys, pathlib
from collections import defaultdict

BIG = ("gt50", "10_50")          # то, что реально различимо
TREE = {"Pine", "Fir", "Deciduous"}
UNDER = {"Bush", "GrassTuft", "Flower", "Stone", "Moss", "Reed"}


def visible_big(k):
    return sum(k["screen_px"][b] for b in BIG)


def report_drawn(d):
    """Сверка «должно попасть в кадр» с «включено на отрисовку».

    Единственная проверка в этом скрипте, которая говорит о ДОСТОВЕРНОСТИ остальных.
    Если вид числится в кадре, а корзины по нему пусты, то и снимок будет пуст, и
    все выводы о плотности, размере и покрытии по этому обходу недействительны.
    """
    faults = []
    if not any("drawn" in k for v in d["views"] for k in v["kinds"].values()):
        print("ВНИМАНИЕ: в файле нет поля drawn — обход снят сборкой до V147, "
              "сверить телеметрию со снимками нечем")
        return faults
    bad = defaultdict(lambda: [0, 0])       # вид -> [видов с расхождением, экземпляров]
    for view in d["views"]:
        for name, k in view["kinds"].items():
            dr = k.get("drawn")
            if dr is None or k["visible"] == 0:
                continue
            if dr["full"] + dr["lod1"] + dr["imp"] == 0:
                bad[name][0] += 1
                bad[name][1] += k["visible"]
    for name, (nviews, ninst) in sorted(bad.items(), key=lambda x: -x[1][1]):
        faults.append(
            f"ИНСТРУМЕНТ: {name} — в {nviews} видах телеметрия насчитала {ninst} "
            f"экземпляров в кадре, а на отрисовку не включено НИ ОДНОГО. "
            f"Снимки этих поз пусты не потому, что пуст уровень.")
    return faults


def report_pool(d):
    """Чем засажен уровень: возраст, качество, вид, рост в метрах."""
    faults = []
    pool = d.get("plants")
    if not pool:
        print("ВНИМАНИЕ: в файле нет блока plants — обход снят сборкой до V147, "
              "возраст и качество растений на уровне неизвестны")
        return faults
    lo, hi = pool.get("age_range", [-1, -1])
    print(f"Пул растений: {'игровой' if pool.get('game_pool') else 'ВИТРИНЫ'}, "
          f"возраст {lo}–{hi}, качество {pool.get('q_target')}, "
          f"листва {pool.get('foliage_detail')}, "
          f"импосторов выпечено {pool.get('baked_impostors')}")
    if not pool.get("game_pool"):
        faults.append(
            "ПУЛ: уровень засажен каталогом ВИТРИНЫ — у всех вариантов один возраст "
            "и одно качество, выставленные в её интерфейсе (см. PlantCatalog.IsGamePool)")

    print("\nРост в игре — в метрах, прототип уже домножен на масштаб экземпляра.")
    print(f"{'вид':<11}{'в':>3}{'возр':>6}{'кач':>5}  {'порода':<18}"
          f"{'экз.':>8}{'мин':>9}{'ср':>8}{'макс':>8}")
    print("-" * 78)
    for kind, variants in pool.get("kinds", {}).items():
        for v in variants:
            h = v["h_m"]
            flag = "" if v.get("mesh_ready", True) else "  меш не собран"
            print(f"{kind:<11}{v['v']:>3}{v['age']:>6}{v['quality']:>5}"
                  f"  {v['species']:<18}{v['instances']:>8}"
                  f"{h['min']:>9.2f}{h['avg']:>8.2f}{h['max']:>8.2f}{flag}")
            if v["instances"] > 0 and not v.get("mesh_ready", True):
                faults.append(
                    f"ПУЛ: {kind} вариант {v['v']} стоит на уровне ({v['instances']} экз.), "
                    f"но его меш ещё не собран")
            if v["instances"] > 0 and lo >= 0 and not (lo <= v["age"] <= hi):
                faults.append(
                    f"ПУЛ: {kind} вариант {v['v']} собран возрастом {v['age']} "
                    f"при игровом диапазоне {lo}–{hi}")
    print()
    return faults


def main():
    d = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf8"))
    print(f"Сборка: {d.get('stamp')}   {d.get('time')}")
    v, b = d["viewport"], d["bands"]
    print(f"Окно {v['w']}×{v['h']}, поле зрения {v['fov']}°")
    print(f"Полосы: полный меш до {b['full_exit']}, импостор от {b['impostor_enter']}, "
          f"покрытия скрыты за {b['cover_hide']}")
    print(f"Видов снято: {d['views_count']}")
    tool_faults = report_pool(d) + report_drawn(d)
    # Проверка самой выборки: точки не должны липнуть к краю и друг к другу.
    pts = {}
    for v in d["views"]:
        pts[v["label"].split(",")[0]] = (v["camera"]["x"], v["camera"]["z"])
    xs = [p[0] for p in pts.values()]
    zs = [p[1] for p in pts.values()]
    print(f"Точек: {len(pts)}, разброс X {min(xs):.0f}..{max(xs):.0f}, "
          f"Z {min(zs):.0f}..{max(zs):.0f}")
    # ЧЕГО ТЕЛЕМЕТРИЯ НЕ ВИДИТ. Перекрытие рельефом здесь не улавливается ни одним
    # числом: подсчёт идёт по пирамиде видимости, а не по тому, что реально дошло до
    # пикселя. Точка внутри горы даёт такие же тысячи экземпляров, как открытый
    # склон. Единственный способ это заметить — снимок; для того он и снимается.
    # Здесь остаётся проверка выборки: не слиплись ли точки и не жмутся ли к краю.
    lim = max(max(abs(x) for x in xs), max(abs(z) for z in zs))
    edge = [n for n, (x, z) in pts.items() if max(abs(x), abs(z)) > lim * 0.97]
    if len(edge) > len(pts) * 0.4:
        print(f"ВНИМАНИЕ: {len(edge)} из {len(pts)} точек прижаты к краю выборки — "
              f"проверьте отбор, а не уровень")
    print()

    # --- сводка по точкам (усреднение по азимутам) ---
    by_point = defaultdict(list)
    for view in d["views"]:
        # Подпись вида «луг 2, азимут 90°»: точка — всё до запятой, номер отбрасываем,
        # чтобы три точки одного биома сводились вместе.
        pt = view["label"].split(",")[0].rsplit(" ", 1)[0]
        by_point[pt].append(view)

    print(f"{'точка':<14}{'деревьев':>10}{'подлеска':>10}{'тр-ков':>11}   замечание")
    print("-" * 78)
    problems = []
    for point, views in by_point.items():
        trees = sum(visible_big(k) for w in views for n, k in w["kinds"].items() if n in TREE) / len(views)
        under = sum(visible_big(k) for w in views for n, k in w["kinds"].items() if n in UNDER) / len(views)
        tris = sum(w["vegetation_tris"] for w in views) / len(views)
        note = []
        if trees + under < 15:
            note.append("пусто")
            problems.append(f"{point}: в кадре меньше 15 различимых растений")
        if trees >= 5 and under < 3:
            note.append("нет подлеска")
            problems.append(f"{point}: деревья есть ({trees:.0f}), подлеска нет ({under:.1f})")
        if tris > 400_000:
            note.append("выше бюджета")
        print(f"{point:<14}{trees:>10.0f}{under:>10.1f}{tris:>11,.0f}   {', '.join(note)}")

    # --- сводка по видам по всему обходу ---
    print(f"\n{'вид':<12}{'в кадре':>9}{'>10px':>8}{'<2px':>8}{'тр-ков':>11}   вердикт")
    print("-" * 78)
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for w in d["views"]:
        for n, k in w["kinds"].items():
            a = agg[n]
            a[0] += k["visible"]
            a[1] += visible_big(k)
            a[2] += k["screen_px"]["lt2"]
            a[3] += k["tris"]
    for n, (vis, big, tiny, tris) in sorted(agg.items(), key=lambda x: -x[1][3]):
        verdict = ""
        if vis > 0 and big == 0:
            verdict = "НЕ ВИДЕН НИ РАЗУ"
            problems.append(f"{n}: {vis} экземпляров за весь обход, ни один не крупнее 10 точек")
        elif vis > 0 and tiny > vis * 0.9:
            verdict = "почти весь мельче 2 точек"
        print(f"{n:<12}{vis:>9}{big:>8}{tiny:>8}{tris:>11,}   {verdict}")

    # Дефекты инструмента идут ПЕРВЫМИ и отдельным блоком: пока они есть, остальные
    # выводы обсуждать бессмысленно — они сделаны по недостоверному кадру.
    print("\n" + "=" * 78)
    if tool_faults:
        print("СНАЧАЛА — ДЕФЕКТЫ ИЗМЕРЕНИЯ (выводы об уровне недостоверны):")
        for p in dict.fromkeys(tool_faults):
            print("  •", p)
        print("-" * 78)
    if problems:
        print("НАЙДЕННЫЕ ПРОБЛЕМЫ:")
        for p in dict.fromkeys(problems):
            print("  •", p)
    elif not tool_faults:
        print("Правила разбора не нашли проблем. Смотреть глазами.")


if __name__ == "__main__":
    main()
