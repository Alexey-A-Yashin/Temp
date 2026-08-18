#!/usr/bin/env python3
"""Чтение двоичной выгрузки сеток рельефа и её разбор.

Формат пишет TerrainReport.WriteRaw:
    "CBTR", версия int32, число колец int32
    на кольцо: номер int32, сторона int32, шаг float32, смещение float32,
               сторона² высот float32, столько же стока float32,
               и (со второй версии) сторона² байтов покрова,
               и (с четвёртой) сторона² по три байта цвета

В третьей версии из покрова убран Marsh, номера сдвинулись — см. _use_version.

Все величины в мировых единицах: чтобы получить метры, умножаем на десять.
"""
import struct
import sys

import numpy as np

METRES_PER_UNIT = 10.0


def read(path):
    """Список колец: (номер, сторона, шаг, смещение, высоты, сток)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"CBTR":
        raise ValueError("не тот файл: нет метки CBTR")
    ver, rings = struct.unpack_from("<ii", data, 4)
    _use_version(ver)
    # с четвёртой версии за покровом идёт цвет вершины по три байта
    pos = 12
    out = []
    for _ in range(rings):
        ring, side = struct.unpack_from("<ii", data, pos)
        cell, lift = struct.unpack_from("<ff", data, pos + 8)
        pos += 16
        n = side * side
        h = np.frombuffer(data, dtype="<f4", count=n, offset=pos).reshape(side, side)
        pos += n * 4
        flow = np.frombuffer(data, dtype="<f4", count=n, offset=pos).reshape(side, side)
        pos += n * 4
        if ver >= 2:
            biome = np.frombuffer(data, dtype=np.uint8, count=n, offset=pos).reshape(side, side)
            pos += n
        else:
            biome = np.zeros((side, side), np.uint8)
        # Цвет вершины: с четвёртой версии. Покров и цвет перестали совпадать,
        # когда камень и осыпь стали краситься по породе места.
        if ver >= 4:
            col = np.frombuffer(data, dtype=np.uint8, count=n * 3,
                                offset=pos).reshape(side, side, 3)
            pos += n * 3
        else:
            col = np.zeros((side, side, 3), np.uint8)
        out.append((ring, side, cell, lift, h.copy(), flow.copy(), biome.copy(),
                    col.copy()))
    return out


def slopes(h, cell):
    gy, gx = np.gradient(h, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


# Нумерация зависит от версии файла: в третьей из покрова убран Marsh, и всё,
# что стояло после него, сдвинулось на единицу. Читать старую выгрузку новым
# списком нельзя — лес прочитается как луг.
BIOME_NAMES_V2 = ["Water", "Marsh", "Grassland", "Forest", "Shrubland",
                  "Alpine", "Scree", "Rock", "Snow"]
BIOME_NAMES_V3 = ["Water", "Grassland", "Forest", "Shrubland",
                  "Alpine", "Scree", "Rock", "Snow"]

_RGB = {
    "Water":     [0.16, 0.34, 0.62],
    "Marsh":     [0.36, 0.44, 0.30],
    "Grassland": [0.47, 0.58, 0.32],
    "Forest":    [0.24, 0.40, 0.24],
    "Shrubland": [0.40, 0.47, 0.30],
    "Alpine":    [0.55, 0.58, 0.42],
    "Scree":     [0.58, 0.56, 0.50],
    "Rock":      [0.46, 0.45, 0.44],
    "Snow":      [0.93, 0.95, 0.97],
}

# По умолчанию — нынешний формат; read() переопределяет по версии файла.
BIOME_NAMES = BIOME_NAMES_V3
BIOME_RGB = np.array([_RGB[n] for n in BIOME_NAMES])


def _use_version(ver):
    """Выставить нумерацию покрова под версию прочитанного файла."""
    global BIOME_NAMES, BIOME_RGB
    BIOME_NAMES = BIOME_NAMES_V2 if ver < 3 else BIOME_NAMES_V3
    BIOME_RGB = np.array([_RGB[n] for n in BIOME_NAMES])


def biome_shade(h, cell, biome, path):
    """Рельеф в цветах покрова — так же, как его видит игрок."""
    from PIL import Image
    gy, gx = np.gradient(h, cell)
    n = np.dstack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    L = np.array([0.42, 0.5, 0.76])
    L /= np.linalg.norm(L)
    sh = np.clip((n * L).sum(2), 0, 1)
    col = BIOME_RGB[np.clip(biome, 0, len(BIOME_RGB) - 1)]
    col = col * (0.30 + 0.82 * sh)[..., None]
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8)[::-1]).save(path)


def summary(rings):
    print("%-6s %8s %9s %9s %8s %8s %8s %8s" % (
        "кольцо", "ячейка,м", "перепад,м", "уклон", "<12°", "<20°", "<30°", "сток p99"))
    for ring, side, cell, lift, h, flow, biome, col in rings:
        a = slopes(h, cell)
        hm = (h - lift) * METRES_PER_UNIT
        print("%-6d %8.0f %9.0f %8.1f° %7.1f%% %7.1f%% %7.1f%% %8.0f" % (
            ring, cell * METRES_PER_UNIT, hm.max() - hm.min(), a.mean(),
            (a < 12).mean() * 100, (a < 20).mean() * 100, (a < 30).mean() * 100,
            np.percentile(flow, 99)))


def shade(h, cell, path, flow=None):
    """Затенённый рельеф; если передан сток, поверх рисуются водотоки."""
    from PIL import Image
    gy, gx = np.gradient(h, cell)
    n = np.dstack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    L = np.array([0.42, 0.5, 0.76])
    L /= np.linalg.norm(L)
    sh = np.clip((n * L).sum(2), 0, 1)
    t = np.clip((h - h.min()) / max(h.max() - h.min(), 1e-6), 0, 1)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    col = np.zeros(h.shape + (3,))
    col[..., 0] = 0.33 + 0.16 * t
    col[..., 1] = 0.46 - 0.04 * t
    col[..., 2] = 0.29 + 0.10 * t
    rock = np.clip((slope - 30) / 16, 0, 1)
    col = col * (1 - rock[..., None]) + np.array([0.50, 0.49, 0.47]) * rock[..., None]
    snow = np.clip((t - 0.68) / 0.18, 0, 1) * np.clip(1 - (slope - 40) / 25, 0, 1)
    col = col * (1 - snow[..., None]) + np.array([0.95, 0.96, 0.98]) * snow[..., None]
    col *= (0.28 + 0.85 * sh)[..., None]
    if flow is not None:
        water = np.clip((np.log1p(flow) - np.log1p(np.percentile(flow, 99))) / 2.0, 0, 1)
        col = col * (1 - water[..., None]) + np.array([0.25, 0.45, 0.75]) * water[..., None]
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8)[::-1]).save(path)


if __name__ == "__main__":
    rings = read(sys.argv[1])
    summary(rings)
    print()
    total = np.zeros(len(BIOME_NAMES), int)
    for ring, side, cell, lift, h, flow, biome, col in rings:
        shade(h, cell, f"/home/claude/work/ring{ring}.png", flow)
        biome_shade(h, cell, biome, f"/home/claude/work/biome{ring}.png")
        total += np.bincount(biome.ravel(), minlength=len(BIOME_NAMES))
    print("покров по всем кольцам:")
    for i, nm in enumerate(BIOME_NAMES):
        if total[i]:
            print("  %-10s %5.1f%%" % (nm, total[i] * 100 / total.sum()))
    print("\nкартинки колец сохранены (рельеф и покров)")
