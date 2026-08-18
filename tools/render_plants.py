#!/usr/bin/env python3
"""Отрисовка мешей растений без Godot.

ЗАЧЕМ. Правки геометрии растений раз за разом уходили пользователю непроверенными
глазами: движка в песочнице нет, и единственным способом увидеть результат был
прогон на его машине. Числа (высота, радиус кроны, число треугольников) при этом
сходились, а силуэт оставался неверным — веретено вместо конуса числами не ловится.

Здесь меш растения, выгруженный стендом, растеризуется напрямую: перспективная
камера, z-буфер, барицентрическая интерполяция UV и цвета, отсечение по альфе
атласа — тот же порог 0.5, что в foliage.gdshader. Освещение примитивное
(ламберт по нормали грани плюс окружающий свет): цель не красота, а силуэт,
плотность кроны и пропорции.
"""
import sys, pathlib, math
import numpy as np
from PIL import Image

ATLAS = None


def load_mesh(path):
    P, UV, C, F = [], [], [], []
    for line in pathlib.Path(path).read_text(encoding="utf8").splitlines():
        if line.startswith("v "):
            p = line.split()
            P.append([float(p[1]), float(p[2]), float(p[3])])
            UV.append([float(p[4]), float(p[5])])
            C.append([float(p[6]), float(p[7]), float(p[8])])
        elif line.startswith("f "):
            p = line.split()
            F.append([int(p[1]), int(p[2]), int(p[3])])
    return np.array(P, np.float32), np.array(UV, np.float32), np.array(C, np.float32), np.array(F, np.int32)


def render(P, UV, C, F, W=520, H=760, fov=32.0, dist_mul=1.45, bg=(250, 250, 252)):
    """Камера смотрит горизонтально на середину высоты растения."""
    h = float(P[:, 1].max())
    radius = float(np.sqrt(P[:, 0] ** 2 + P[:, 2] ** 2).max())
    centre = np.array([0.0, h * 0.5, 0.0], np.float32)
    # Кадрируем по БОЛЬШЕМУ из габаритов. Раньше бралась только высота, и плоские
    # широкие объекты — куртина травы, группа валунов — упирались в камеру одной
    # гранью: на картинке был серый прямоугольник во весь кадр вместо камней.
    extent = max(h * 0.5, radius * (W / H))
    d = extent / math.tan(math.radians(fov) / 2) * dist_mul
    eye = centre + np.array([0.0, 0.0, d], np.float32)

    V = P - eye                       # камера смотрит в -Z, ось Y вверх
    z = -V[:, 2]
    f = (H * 0.5) / math.tan(math.radians(fov) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        sx = W * 0.5 + V[:, 0] * f / z
        sy = H * 0.5 - (V[:, 1] - 0) * f / z
    sy += (centre[1] - 0) * 0  # центр уже учтён через eye

    img = np.zeros((H, W, 3), np.float32)
    img[:] = np.array(bg, np.float32) / 255.0
    zbuf = np.full((H, W), 1e9, np.float32)

    ah, aw = ATLAS.shape[0], ATLAS.shape[1]
    light = np.array([-0.40, 0.72, 0.57], np.float32)
    light /= np.linalg.norm(light)

    for tri in F:
        i0, i1, i2 = tri
        if z[i0] <= 0.01 or z[i1] <= 0.01 or z[i2] <= 0.01:
            continue
        x0, y0 = sx[i0], sy[i0]
        x1, y1 = sx[i1], sy[i1]
        x2, y2 = sx[i2], sy[i2]
        minx, maxx = int(max(0, math.floor(min(x0, x1, x2)))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        miny, maxy = int(max(0, math.floor(min(y0, y1, y2)))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue

        ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
        px = xs + 0.5
        py = ys + 0.5
        w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
        w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue

        zz = w0 * z[i0] + w1 * z[i1] + w2 * z[i2]
        u = w0 * UV[i0, 0] + w1 * UV[i1, 0] + w2 * UV[i2, 0]
        v = w0 * UV[i0, 1] + w1 * UV[i1, 1] + w2 * UV[i2, 1]
        ax = np.clip((u * aw).astype(np.int32), 0, aw - 1)
        ay = np.clip((v * ah).astype(np.int32), 0, ah - 1)
        texel = ATLAS[ay, ax]                      # RGBA 0..1
        keep = inside & (texel[..., 3] >= 0.5) & (zz < zbuf[miny:maxy + 1, minx:maxx + 1])
        if not keep.any():
            continue

        n = np.cross(P[i1] - P[i0], P[i2] - P[i0])
        nl = np.linalg.norm(n)
        lam = 0.45 if nl < 1e-9 else 0.45 + 0.55 * abs(float(np.dot(n / nl, light)))

        col = (w0[..., None] * C[i0] + w1[..., None] * C[i1] + w2[..., None] * C[i2])
        col = col * texel[..., :3] * lam

        sub = img[miny:maxy + 1, minx:maxx + 1]
        subz = zbuf[miny:maxy + 1, minx:maxx + 1]
        sub[keep] = col[keep]
        subz[keep] = zz[keep]

    return (np.clip(img, 0, 1) * 255).astype(np.uint8), h, radius


def main():
    global ATLAS
    atlas_path = sys.argv[1]
    mesh_dir = pathlib.Path(sys.argv[2])
    out_path = sys.argv[3]
    names = sys.argv[4:]

    a = Image.open(atlas_path).convert("RGBA")
    ATLAS = np.asarray(a).astype(np.float32) / 255.0

    tiles, labels = [], []
    for n in names:
        f = mesh_dir / (n + ".mesh")
        P, UV, C, F = load_mesh(f)
        im, h, r = render(P, UV, C, F)
        tiles.append(im)
        labels.append(f"{n}  h={h:.1f} r/h={r/h:.2f} tris={len(F)}")
        print(f"{n:26} высота {h:6.2f}  радиус/высота {r/h:.2f}  треугольников {len(F)}")

    Hh = max(t.shape[0] for t in tiles)
    Ww = sum(t.shape[1] for t in tiles)
    sheet = Image.new("RGB", (Ww, Hh + 26), (250, 250, 252))
    x = 0
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for t, lab in zip(tiles, labels):
        sheet.paste(Image.fromarray(t), (x, 0))
        d.text((x + 6, Hh + 6), lab, fill=(20, 20, 20))
        x += t.shape[1]
    sheet.save(out_path)
    print("записано:", out_path, sheet.size)


if __name__ == "__main__":
    main()
