#!/usr/bin/env python3
"""Генерация атласа листвы для ColoringBook.

ЗАЧЕМ. Прежний атлас 256×256 состоял из четырёх фигур в СПЛОШНОМ БЕЛОМ цвете:
квадрат, спица и два скруглённых ромба. Проверено по извлечённому файлу: среди
непрозрачных точек ровно один цвет (255,255,255) в каждой ячейке. То есть текстура
задавала только силуэт, и силуэт листа был ромбом — отсюда «зелёные квадраты» на
экране, сколько бы труда ни было вложено в скелет дерева.

Здесь рисуются настоящие силуэты (дуб, берёза, клён, ива, лещина), хвойные мотивы
(одиночная хвоинка, лапа пихты, пучок сосны), травинка и лепесток, и у каждого —
центральная жилка с боковыми. Жилки идут В ЦВЕТЕ (тёмное на белом): материал
умножает текстуру на цвет вершины, поэтому тёмное в текстуре становится тёмной
зеленью, а сезонная окраска продолжает работать как раньше.

Сетка 4×4 по 256 точек при атласе 1024×1024. Размер выбран по замеру экранного
покрытия: карточка листа занимает 119 точек экрана на дистанции 5 единиц и 59 на
десяти, то есть 256-точечная ячейка читается почти один к одному.

Рисуется с четырёхкратным разрешением и уменьшается — так края получают сглаживание
без ручного размытия.
"""
import math
from PIL import Image, ImageDraw

ATLAS = 1024
GRID = 4
CELL = ATLAS // GRID          # 256
SS = 4                        # суперсэмплинг
C = CELL * SS

WHITE = (255, 255, 255, 255)
# Жилки и затенения — оттенки серого: материал умножает их на цвет вершины.
VEIN = (176, 176, 176, 255)
VEIN_FINE = (205, 205, 205, 255)
EDGE = (150, 150, 150, 255)


def blank():
    return Image.new("RGBA", (C, C), (255, 255, 255, 0))


def to_px(x, y):
    """Нормализованные координаты листа -> точки ячейки.
    x в [-0.5, 0.5], y в [0, 1]: 0 — черешок снизу, 1 — кончик сверху."""
    return (C * (0.5 + x), C * (1.0 - y))


def leaf_polygon(halfwidth, samples=220, y0=0.03, y1=0.99):
    """Симметричный лист по функции полуширины halfwidth(t), t в [0,1]."""
    left, right = [], []
    for i in range(samples + 1):
        t = i / samples
        y = y0 + (y1 - y0) * t
        w = max(halfwidth(t), 0.0)
        left.append(to_px(-w, y))
        right.append(to_px(w, y))
    return left + right[::-1]


def serrate(halfwidth, teeth, depth):
    """Обёртка: мелкий пилообразный край (берёза, лещина, ива).

    Зубцы вычитаются как доля ПОЛУШИРИНЫ, но малая: при глубине больше ~0.08
    силуэт перестаёт быть листом и начинает читаться как ёлочка — проверено
    на первом варианте атласа."""
    def f(t):
        base = halfwidth(t)
        saw = abs(((t * teeth) % 1.0) - 0.5) * 2.0    # 0..1 треугольная волна
        return base * (1.0 - depth * saw)
    return f


def draw_veins(d, halfwidth, pairs=6, spread=0.82, y0=0.05, y1=0.97, width=None):
    """Центральная жилка и боковые, уходящие к краю пластинки."""
    w = width or max(2, int(C * 0.012))
    d.line([to_px(0, y0), to_px(0, y1)], fill=VEIN, width=w)
    for i in range(1, pairs + 1):
        t = i / (pairs + 1)
        ys = y0 + (y1 - y0) * t * 0.92
        ye = y0 + (y1 - y0) * min(t * 0.92 + 0.16, 0.98)
        hw = halfwidth(t) * spread
        d.line([to_px(0, ys), to_px(hw, ye)], fill=VEIN_FINE, width=max(1, w // 2))
        d.line([to_px(0, ys), to_px(-hw, ye)], fill=VEIN_FINE, width=max(1, w // 2))


# ---------------------------------------------------------------- силуэты

def env_ovate(t):
    """Яйцевидная пластинка: широкая ниже середины, острый кончик."""
    return 0.42 * math.sin(math.pi * (t ** 0.62)) ** 0.85


def hw_oak(t):
    # Дуб: перистолопастной. Пластинка ШИРЕ ВЫШЕ СЕРЕДИНЫ и сужается к черешку —
    # обратная асимметрия (широкое основание) давала силуэт ёлки, а не дуба.
    env = 0.46 * math.sin(math.pi * (t ** 1.35)) ** 0.62
    # Лопасти округлые: косинус в четвёртой степени даёт плоские вершины
    # и узкие вырезы, как у Quercus robur.
    k = 0.5 + 0.5 * math.cos(2 * math.pi * 4.0 * t)
    lobes = 0.72 + 0.28 * (k ** 0.55)
    return env * lobes


def hw_birch(t):
    return env_ovate(t) * 0.86


def hw_willow(t):
    # Ланцетный: длинный и узкий.
    return 0.17 * math.sin(math.pi * (t ** 0.55)) ** 0.6


def hw_hazel(t):
    # Округло-яйцевидный, шире дуба, с оттянутым кончиком.
    return 0.46 * math.sin(math.pi * (t ** 0.80)) ** 0.75


def maple_polygon(lobes=5, samples=640):
    """Клён: пальчатая пластинка в полярных координатах от основания черешка.

    Первый вариант давал ОТДЕЛЬНЫЕ доли: в вырезах радиус падал почти до нуля,
    и лопасти сходились в точку. Основание вырезов поднято до 0.46 радиуса —
    пластинка становится связной, как у Acer platanoides, а вырезы остаются
    глубокими."""
    pts = []
    span = math.pi * 0.98
    for i in range(samples + 1):
        a = -span / 2 + span * i / samples          # веер вверх
        k = 0.5 + 0.5 * math.cos(lobes * a * (2 * math.pi / (2 * span)) * 2.0)
        r = 0.46 + 0.54 * (k ** 1.35)
        x = r * math.sin(a) * 0.50
        y = 0.05 + r * math.cos(a) * 0.90
        pts.append(to_px(x, y))
    pts.append(to_px(0.0, 0.03))
    return pts


def needle_polygon():
    """Одиночная хвоинка: узкая, заострённая с обоих концов."""
    def hw(t):
        return 0.055 * math.sin(math.pi * t) ** 0.45
    return leaf_polygon(hw, y0=0.02, y1=0.99)


# ---------------------------------------------------------------- ячейки

def cell_solid():
    img = blank()
    ImageDraw.Draw(img).rectangle([0, 0, C - 1, C - 1], fill=WHITE)
    return img


def cell_leaf(halfwidth, pairs=6, petiole=True):
    img = blank()
    d = ImageDraw.Draw(img)
    d.polygon(leaf_polygon(halfwidth), fill=WHITE, outline=EDGE,
              width=max(2, int(C * 0.008)))
    draw_veins(d, halfwidth, pairs=pairs)
    if petiole:
        d.line([to_px(0, 0.0), to_px(0, 0.06)], fill=VEIN,
               width=max(2, int(C * 0.014)))
    return img


def cell_maple():
    img = blank()
    d = ImageDraw.Draw(img)
    poly = maple_polygon()
    d.polygon(poly, fill=WHITE, outline=EDGE, width=max(2, int(C * 0.008)))
    # Пять жилок от основания к вершинам лопастей.
    for i in range(5):
        a = -math.pi * 0.40 + (math.pi * 0.80) * i / 4
        d.line([to_px(0, 0.06), to_px(math.sin(a) * 0.44, 0.06 + math.cos(a) * 0.82)],
               fill=VEIN, width=max(2, int(C * 0.011)))
    d.line([to_px(0, 0.0), to_px(0, 0.07)], fill=VEIN, width=max(2, int(C * 0.014)))
    return img


def cell_needle():
    img = blank()
    d = ImageDraw.Draw(img)
    d.polygon(needle_polygon(), fill=WHITE)
    d.line([to_px(0, 0.05), to_px(0, 0.95)], fill=VEIN_FINE, width=max(1, int(C * 0.006)))
    return img


def cell_fir_spray(count=15):
    """Лапа пихты: ось с хвоинками в обе стороны, гребёнкой."""
    img = blank()
    d = ImageDraw.Draw(img)
    d.line([to_px(0, 0.02), to_px(0, 0.97)], fill=VEIN, width=max(2, int(C * 0.012)))
    for i in range(count):
        t = 0.06 + 0.88 * i / (count - 1)
        # Хвоинки короче к вершине — так лапа читается как лапа, а не как гребень.
        # Длина убывает к вершине, но не линейно: линейное убывание давало ровный
        # треугольник, который читался как гребёнка, а не как лапа.
        ln = 0.38 * (1.0 - 0.45 * t) * (0.88 + 0.12 * ((i % 2) * 2 - 1))
        up = 0.16 * (1.0 - 0.4 * t)
        for s in (-1, 1):
            d.line([to_px(0, t), to_px(s * ln, t + up)], fill=WHITE,
                   width=max(2, int(C * 0.020)))
    return img


def cell_pine_fascicle(count=3):
    """Пучок сосны: две-три длинные хвоинки из одного основания."""
    img = blank()
    d = ImageDraw.Draw(img)
    for i in range(count):
        a = (i - (count - 1) / 2) * 0.20
        tip = to_px(math.sin(a) * 0.30, 0.97)
        d.line([to_px(0, 0.03), tip], fill=WHITE, width=max(3, int(C * 0.030)))
    d.ellipse([to_px(-0.05, 0.10)[0], to_px(0, 0.10)[1],
               to_px(0.05, 0.0)[0], to_px(0, 0.0)[1]], fill=VEIN)
    return img


def cell_grass():
    """Травинка: длинная сужающаяся пластинка с изгибом."""
    img = blank()
    d = ImageDraw.Draw(img)
    pts_l, pts_r = [], []
    for i in range(81):
        t = i / 80
        bend = 0.16 * t * t
        w = 0.075 * (1.0 - t) ** 0.75
        pts_l.append(to_px(bend - w, 0.02 + 0.96 * t))
        pts_r.append(to_px(bend + w, 0.02 + 0.96 * t))
    d.polygon(pts_l + pts_r[::-1], fill=WHITE)
    d.line([to_px(0, 0.03), to_px(0.14, 0.94)], fill=VEIN_FINE, width=max(1, int(C * 0.006)))
    return img


def cell_petal():
    """Лепесток: узкий овал со скруглённым концом."""
    def hw(t):
        return 0.16 * math.sin(math.pi * t) ** 0.5
    img = blank()
    d = ImageDraw.Draw(img)
    d.polygon(leaf_polygon(hw), fill=WHITE, outline=EDGE, width=max(1, int(C * 0.006)))
    d.line([to_px(0, 0.06), to_px(0, 0.94)], fill=VEIN_FINE, width=max(1, int(C * 0.006)))
    return img


# ---------------------------------------------------------------- ПУЧКИ (V130)
#
# ЗАЧЕМ. Замер вскрыл корень: карточка «листа» на уровне имеет 2.33 метра у
# лиственного и 3.75 у сосны — в 19 и 15 раз больше натуры. Так вышло потому, что
# покрытие кроны раз за разом добиралось УВЕЛИЧЕНИЕМ карточек: при фиксированном
# бюджете треугольников площадь иначе не растёт. А в ячейке нарисован ОДИН лист с
# жилками — он и читается как исполинский лопух.
#
# Правильный размен другой и стандартный для игр: карточка изображает не лист, а
# ПУЧОК листьев на веточке. Тогда карточка в полметра — это веточка с десятком
# листьев натуральной величины: крона набирается тем же числом карточек, а густоту
# несёт рисунок, а не размер.


def cluster(halfwidth, count=11, leaf_scale=0.26, serr=None):
    """Пучок: веточка с несколькими листьями натуральной пропорции."""
    img = blank()
    d = ImageDraw.Draw(img)
    hw = serrate(halfwidth, serr[0], serr[1]) if serr else halfwidth

    stem = [to_px(-0.34 + 0.30 * t, 0.05 + 0.88 * t) for t in [i / 24 for i in range(25)]]
    d.line(stem, fill=VEIN, width=max(2, int(C * 0.010)))

    rnd = [(i * 0.6180339887) % 1.0 for i in range(count * 3)]
    for i in range(count):
        t = (i + 0.6) / (count + 0.4)
        bx = -0.34 + 0.30 * t
        by = 0.05 + 0.88 * t
        side = 1 if i % 2 == 0 else -1
        ang = side * (0.55 + 0.55 * rnd[i]) - 0.25
        sc = leaf_scale * (0.80 + 0.40 * rnd[i + count])
        pts = leaf_polygon(hw, samples=90)
        ca, sa = math.cos(ang), math.sin(ang)
        moved = []
        for (px_, py_) in pts:
            nx = (px_ / C - 0.5) * sc
            ny = (1.0 - py_ / C) * sc
            moved.append(to_px(bx + nx * ca - ny * sa, by + nx * sa + ny * ca))
        d.polygon(moved, fill=WHITE, outline=EDGE, width=max(1, int(C * 0.004)))
    return img


def conifer_cluster(rows=11):
    """ХВОЙНАЯ ЛАПА КАК МАССА, А НЕ КАК ПУЧОК ОТДЕЛЬНЫХ ИГЛ.

    Прежняя версия рисовала лапу пятью отдельными линиями на сторону. Ячейка
    выходила непрозрачной на 20%, и это оказалось главной причиной, по которой
    хвойные на уровне не существуют: замер по кадру дал 0.1% площади и две трети
    её в кусках мельче 50 точек экрана. Сколько таких карточек ни накладывай,
    между иглами остаются щели МЕЛЬЧЕ порога закрашиваемости — прогон упаковки:
    40 карточек дают 81% заполненности при 19% площади в мелких дырках, тогда как
    у лиственной ячейки те же 4%.

    Учебники рисунка требуют обратного: у хвойных просветов неба должно быть
    МЕНЬШЕ, чем у лиственных, а массы листвы уложены слоями. Игла как отдельный
    объект уместна в упор, в витрине; на уровне сосна занимает 30-80 точек экрана,
    и там иглы превращаются в пыль.

    Поэтому лапа рисуется ЗАЛИТЫМ клином с гребёнчатым краем: внутри сплошная
    масса, иглы читаются только по силуэту — ровно так их и рисуют от руки.
    """
    img = blank()
    d = ImageDraw.Draw(img)
    ax0, ay0, ax1, ay1 = -0.30, 0.06, 0.26, 0.96
    d.line([to_px(ax0, ay0), to_px(ax1, ay1)], fill=VEIN, width=max(2, int(C * 0.014)))

    teeth = 9
    for i in range(rows):
        t = (i + 0.5) / rows
        bx = ax0 + (ax1 - ax0) * t
        by = ay0 + (ay1 - ay0) * t
        # Лапы укорачиваются к вершине — силуэт получает конусность.
        # ЦЕЛЬ — НЕ ПРОЦЕНТ НЕПРОЗРАЧНОСТИ, А ТОЛЩИНА ДЕТАЛИ.
        #
        # Первый подбор гнался за непрозрачностью 45-55% и дал 50.4% — но лапы при
        # этом слились в сплошную лопату, от хвойного силуэта не осталось ничего.
        # Мера была выбрана неверно: сыпалась старая ячейка не оттого, что мало
        # закрашено, а оттого, что закрашенное — ТОНКОЕ. Замер медианной толщины
        # (двойное расстояние до края внутри маски): у лиственного пучка 20 точек,
        # у старой хвои 4, у лопаты 44.
        #
        # Поэтому подбор шёл по двум величинам сразу: непрозрачность 33-42% при
        # толщине, равной лиственному пучку. Тогда щели между наложенными
        # карточками получаются такими же, как у лиственных, — то есть либо
        # крупными, либо закрытыми, а не сыпью мельче порога закрашиваемости.
        ln = 0.36 * (1.0 - 0.42 * t)
        half = 0.100 * (1.0 - 0.30 * t)      # полутолщина клина у основания
        for s_ in (-1, 1):
            # Наклон лапы вверх у основания, к горизонтали у вершины: так слои
            # ложатся друг на друга, а не расходятся веером из одной точки.
            up = 0.30 - 0.34 * t
            tipx = bx + s_ * ln
            tipy = by + ln * up + 0.02
            # Клин строится как многоугольник: от основания к кончику по одной
            # кромке, обратно по другой. Внешняя кромка зубчатая — это и есть иглы.
            pts = []
            for k in range(teeth + 1):
                u = k / teeth
                px = bx + (tipx - bx) * u
                py = by + (tipy - by) * u + half * (1.0 - u) * 0.35
                # зубец наружу
                jag = 0.020 * (1.0 - u) * (1.0 if k % 2 == 0 else 0.45)
                pts.append((px, py + jag))
            for k in range(teeth, -1, -1):
                u = k / teeth
                px = bx + (tipx - bx) * u
                py = by + (tipy - by) * u - half * (1.0 - u)
                jag = 0.020 * (1.0 - u) * (1.0 if k % 2 == 1 else 0.45)
                pts.append((px, py - jag))
            d.polygon([to_px(x, y) for (x, y) in pts], fill=WHITE,
                      outline=EDGE, width=max(1, int(C * 0.004)))
            # Средняя жилка лапы — читается как ось хвоинок, не разрежая массу.
            d.line([to_px(bx, by), to_px(tipx, tipy)], fill=VEIN_FINE,
                   width=max(1, int(C * 0.006)))
    return img


def bark(seed=7, cracks=13):
    """КОРА: вертикальные трещины и чечевички.

    Ствол до сих пор рисовался сплошным цветом — карточка указывала в непрозрачную
    ячейку атласа. Здесь ячейка получает рисунок: продольные тёмные борозды разной
    глубины и ширины, как у сосны и дуба. Стоимость нулевая — те же треугольники,
    меняются только UV; фактура берётся из текстуры.

    Ячейка НЕПРОЗРАЧНА целиком: альфа-крой на стволе не нужен, а прозрачные точки
    сделали бы в нём дыры.
    """
    img = Image.new("RGBA", (C, C), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    rnd = [(i * 0.6180339887 + seed * 0.1) % 1.0 for i in range(cracks * 6)]
    for i in range(cracks):
        x = (i + 0.5) / cracks + (rnd[i] - 0.5) * 0.05
        w = C * (0.006 + 0.022 * rnd[i + cracks])
        tone = int(150 + 70 * rnd[i + cracks * 2])
        # Борозда идёт не строго вертикально: слегка виляет, как настоящая трещина.
        pts = []
        for k in range(13):
            t = k / 12
            wob = (rnd[(i * 13 + k) % len(rnd)] - 0.5) * 0.035
            pts.append((C * (x + wob), C * t))
        d.line(pts, fill=(tone, tone, tone, 255), width=int(w))
        # Тонкая светлая кромка рядом — так борозда читается как углубление.
        pts2 = [(px + w * 0.9, py) for (px, py) in pts]
        d.line(pts2, fill=(238, 238, 238, 255), width=max(1, int(w * 0.4)))
    # Чечевички: короткие поперечные штрихи, характерны для берёзы и вишни.
    for i in range(cracks * 2):
        x = rnd[i] * C
        y = rnd[(i + 17) % len(rnd)] * C
        ln = C * (0.02 + 0.03 * rnd[(i + 5) % len(rnd)])
        tone = int(120 + 60 * rnd[(i + 9) % len(rnd)])
        d.line([(x, y), (x + ln, y)], fill=(tone, tone, tone, 255),
               width=max(1, int(C * 0.006)))
    return img


# ---------------------------------------------------------------- сборка

# Порядок должен совпадать с FoliageAtlas.cs.
LAYOUT = [
    # (колонка, строка, имя, рисовалка)
    (0, 0, "Solid",        cell_solid),
    (1, 0, "Needle",       cell_needle),
    (2, 0, "FirSpray",     cell_fir_spray),
    (3, 0, "PineFascicle", cell_pine_fascicle),
    (0, 1, "LeafOak",      lambda: cell_leaf(hw_oak, pairs=5)),
    (1, 1, "LeafBirch",    lambda: cell_leaf(serrate(hw_birch, 22, 0.07), pairs=7)),
    (2, 1, "LeafMaple",    cell_maple),
    (3, 1, "LeafWillow",   lambda: cell_leaf(serrate(hw_willow, 30, 0.06), pairs=9)),
    (0, 2, "LeafHazel",    lambda: cell_leaf(serrate(hw_hazel, 20, 0.06), pairs=6)),
    (1, 2, "GrassBlade",   cell_grass),
    (2, 2, "Petal",        cell_petal),
    (3, 2, "Bark",         bark),   # V140: ячейка дубликата дуба отдана коре
    # Строка 3 — ПУЧКИ. Их и рисует уровень; одиночные листья остаются витрине.
    (0, 3, "ClusterOak",   lambda: cluster(hw_oak, count=11, leaf_scale=0.27)),
    (1, 3, "ClusterBirch", lambda: cluster(hw_birch, count=13, leaf_scale=0.24, serr=(22, 0.07))),
    (2, 3, "ClusterMaple", lambda: cluster(hw_hazel, count=9, leaf_scale=0.30)),
    (3, 3, "ClusterConifer", conifer_cluster),
]


def build():
    atlas = Image.new("RGBA", (ATLAS, ATLAS), (255, 255, 255, 0))
    for col, row, name, fn in LAYOUT:
        cell = fn().resize((CELL, CELL), Image.LANCZOS)
        atlas.paste(cell, (col * CELL, row * CELL))
    return atlas


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/foliage_atlas_new.png"
    img = build()
    img.save(out)
    print(f"атлас записан: {out}  {img.size[0]}×{img.size[1]}")
    px = img.load()
    for col, row, name, _ in LAYOUT:
        op = tot = 0
        greys = set()
        for y in range(row * CELL, (row + 1) * CELL, 2):
            for x in range(col * CELL, (col + 1) * CELL, 2):
                r, g, b, a = px[x, y]
                tot += 1
                if a >= 128:
                    op += 1
                    greys.add(r)
        print(f"  {name:14} непрозрачных {op / tot * 100:5.1f}%  оттенков {len(greys)}")
